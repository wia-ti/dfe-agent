"""Provedor de embeddings multilíngues via sentence-transformers.

Carrega o modelo sob demanda (lazy load) para nao bloquear a instanciacao.
O modelo padrao ``paraphrase-multilingual-MiniLM-L12-v2`` suporta
portugues e ~500MB; e cacheado pelo HuggingFace Hub em
``~/.cache/huggingface/`` (Windows: ``%USERPROFILE%\\.cache\\huggingface\\``).

Sprint 3 / Iter 2 — robustez de load:
    - Aceita ``low_cpu_mem_usage=True`` (mitiga ``OSError 1455`` em Windows
      com pouca memoria virtual: o checkpoint nao e materializado ate uso).
    - Aceita ``dtype="float16"`` para reduzir o footprint em ~50% (com
      pequena perda de precisao para a maioria dos casos).
    - ``reset()`` limpa o modelo cached (util entre chamadas em subprocessos
      com pouca RAM).

Coexistencia com Task 5.2:
    Este modulo e independente de ``src.indexer.rag_indexer``. O
    ``RagIndexer`` aceita qualquer objeto com metodo ``embed`` (duck typing),
    entao testes da Task 5.2 nao dependem deste modulo estar disponivel.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from sentence_transformers import SentenceTransformer

from src.utils.logger import get_logger


if TYPE_CHECKING:
    from src.query.embedding_cache import QueryEmbeddingCache


_logger = get_logger(__name__)


# Modelo padrao: 384 dimensoes, multilingue (inclui portugues), ~470MB.
# Para testes offline ou modelos menores, instancie com
# ``EmbeddingProvider("all-MiniLM-L6-v2")`` (~80MB, ingles-only).
#
# Override por variavel de ambiente ``DFE_EMBEDDING_MODEL`` para permitir
# que testes (e operadores) troquem o modelo sem alterar codigo.
DEFAULT_MODEL_NAME: str = os.environ.get(
    "DFE_EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"
)

# Modelo fallback conhecido quando o primario falha com ``OSError 1455``
# (page file do Windows insuficiente). Perde semantica em PT-BR mas
# cabe em qualquer maquina (~80 MB vs ~470 MB).
FALLBACK_MODEL_NAME: str = "all-MiniLM-L6-v2"

# Dtype dos pesos do modelo (PLAN_SPRINT5 F.1).
# Override por env ``DFE_EMBEDDING_DTYPE``: ``"float32"`` (padrao) ou
# ``"float16"`` (reduz ~50% o footprint em RAM/pagefile em Windows com
# pouca memoria virtual; perda minima de precisao).
DEFAULT_EMBEDDING_DTYPE: str = os.environ.get("DFE_EMBEDDING_DTYPE", "float32")


class EmbeddingProvider:
    """Provedor de embeddings multilíngues via sentence-transformers.

    O modelo NAO e carregado em ``__init__``; o download + load ocorre
    apenas na primeira chamada de ``embed()`` ou ``dim``. Isso permite
    instanciar a classe em ambientes onde o modelo nao esta disponivel
    (ex: testes rapidos, ambientes offline).

    Args:
        model_name: Identificador HuggingFace do modelo (default via
            env ``DFE_EMBEDDING_MODEL``).
        low_cpu_mem_usage: Quando True, o checkpoint safetensors nao e
            materializado em memoria ate o primeiro uso. Mitiga o
            ``OSError 1455`` em Windows.
        dtype: Precisao numerica dos pesos (``"float32"`` padrao via
            env ``DFE_EMBEDDING_DTYPE``; ``"float16"`` reduz memoria
            ~50% com perda minima de precisao).
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        low_cpu_mem_usage: bool = True,
        dtype: str = DEFAULT_EMBEDDING_DTYPE,
    ) -> None:
        # Lazy load: nao carrega o modelo na instanciação.
        self._model_name: str = model_name
        self._model: SentenceTransformer | None = None
        self._low_cpu_mem_usage: bool = low_cpu_mem_usage
        self._dtype: str = dtype

    def _load(self) -> SentenceTransformer:
        """Carrega o modelo (uma unica vez) e retorna a instancia cached.

        Envolvido em ``try/except (OSError, RuntimeError)`` para
        diagnosticar falhas comuns (ex.: ``OSError 1455`` em Windows
        com page file insuficiente) com mensagem acionavel apontando
        para workarounds conhecidos: ``DFE_EMBEDDING_DTYPE=float16``
        ou ``DFE_EMBEDDING_MODEL=all-MiniLM-L6-v2``.

        PLAN_SPRINT5 F.1: evita que o agente LLM receba um stack trace
        opaco e improvise (anti-pattern observado em
        ``scripts/answer_nf_e_10_2026.py``, descartado em F.2).
        """
        if self._model is None:
            kwargs: dict[str, Any] = {"device": "cpu"}
            # low_cpu_mem_usage precisa ser passado via HuggingFace
            # transformers; sentence-transformers expoe via config_kwargs
            if self._low_cpu_mem_usage:
                kwargs["model_kwargs"] = {"low_cpu_mem_usage": True}
            # torch_dtype controla a precisao numerica dos pesos carregados.
            if self._dtype and self._dtype != "float32":
                kwargs.setdefault("model_kwargs", {})["torch_dtype"] = self._dtype
            try:
                self._model = SentenceTransformer(self._model_name, **kwargs)
            except OSError as exc:
                # OSError 1455 = "page file too small" no Windows e a
                # causa mais comum de falha de load em CI/maquinas
                # pequenas. Captura estreita: NAO engole OSError generico
                # (ex.: file not found, permission denied) - queremos que
                # esses continuem subindo para o caller.
                if exc.errno == 1455 or "page file" in str(exc).lower():
                    _logger.error(
                        "Falha de load do embedding %s (OSError errno=%s). "
                        "Dtype=%s, low_cpu_mem_usage=%s. "
                        "Workarounds: DFE_EMBEDDING_DTYPE=float16 ou "
                        "DFE_EMBEDDING_MODEL=%s.",
                        self._model_name,
                        exc.errno,
                        self._dtype,
                        self._low_cpu_mem_usage,
                        FALLBACK_MODEL_NAME,
                    )
                    raise RuntimeError(
                        f"Falha ao carregar modelo de embedding "
                        f"{self._model_name!r} (OSError errno={exc.errno}: "
                        f"page file insuficiente). Workarounds: "
                        f"1) DFE_EMBEDDING_DTYPE=float16 "
                        f"(reduz ~50% footprint) OU "
                        f"2) DFE_EMBEDDING_MODEL={FALLBACK_MODEL_NAME} "
                        f"(modelo menor ~80 MB, perde semantica em PT-BR). "
                        f"Origem do erro: {exc}"
                    ) from exc
                raise
            except RuntimeError as exc:
                # RuntimeError do sentence-transformers/transformers
                # tambem sinaliza memoria insuficiente ou config invalida.
                msg: str = str(exc).lower()
                if "out of memory" in msg or "memory" in msg or "paging" in msg:
                    _logger.error(
                        "Falha de load do embedding %s (RuntimeError). "
                        "Dtype=%s, low_cpu_mem_usage=%s. "
                        "Workarounds: DFE_EMBEDDING_DTYPE=float16 ou "
                        "DFE_EMBEDDING_MODEL=%s.",
                        self._model_name,
                        self._dtype,
                        self._low_cpu_mem_usage,
                        FALLBACK_MODEL_NAME,
                    )
                    raise RuntimeError(
                        f"Falha ao carregar modelo de embedding "
                        f"{self._model_name!r} (sem memoria). "
                        f"Workarounds: 1) DFE_EMBEDDING_DTYPE=float16 "
                        f"OU 2) DFE_EMBEDDING_MODEL={FALLBACK_MODEL_NAME}. "
                        f"Origem: {exc}"
                    ) from exc
                raise
        return self._model

    def reset(self) -> None:
        """Limpa o modelo cached. Proxima chamada de ``embed``/``dim``
        faz reload. Util entre subprocessos com pouca RAM."""
        self._model = None

    @property
    def model_loaded(self) -> bool:
        """True se o modelo ja foi carregado (lazy)."""
        return self._model is not None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dim(self) -> int:
        """Dimensao do embedding retornado por ``embed()``.

        Dispara o load do modelo na primeira chamada.
        """
        model: SentenceTransformer = self._load()
        # sentence-transformers >= 3.0 renomeou ``get_sentence_embedding_dimension``
        # para ``get_embedding_dimension``. Tenta o novo e cai no antigo
        # para compatibilidade com versoes mais antigas (< 3.0).
        get_dim: Any = getattr(model, "get_embedding_dimension", None)
        if get_dim is None:
            get_dim = model.get_sentence_embedding_dimension
        return get_dim()

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Gera embeddings para a lista de textos.

        Args:
            texts: Lista de strings a serem embedadas.

        Returns:
            Lista de vetores (lista de floats), um por texto de entrada.
            Cada vetor tem ``self.dim`` dimensoes e norma L2 > 0.

        Raises:
            RuntimeError: Se o modelo nao puder ser carregado (rede
                indisponivel, modelo inexistente, etc.).
        """
        model: SentenceTransformer = self._load()
        # Gate Bug D Sprint 17: normalize_embeddings=True para casar com Node
        # (packages/dfe-agent/src/query/embedder.ts:66 usa normalize: true).
        # Sem normalize, a base em ~/.dfe-agent/dfe.db tinha norm ~2.6-3.3 e o
        # Node norm = 1.0, gerando L2 distance > 1.0 sempre e score < 0.5
        # (MIN_RELEVANCE_SCORE gate hasSufficientEvidence). Fix: normalizar
        # no Py para que L2 entre vetores normalizados = sqrt(2 * (1 - cos))
        # seja monotonicamente relacionado a cosine similarity (ranking correto).
        vectors = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True).tolist()
        return vectors

    def embed_query_cached(
        self,
        query: str,
        cache: "QueryEmbeddingCache | None" = None,
    ) -> list[float]:
        """Embed de uma unica query com cache opcional (Sprint 2 / Fase 13).

        Fluxo:
            1. Se ``cache`` fornecido: tenta ``cache.get(query)``; em hit
               devolve direto sem chamar o modelo.
            2. Em miss (ou sem cache): chama ``embed([query])[0]``; se
               ``cache`` foi fornecido, persiste via ``cache.put``.

        Args:
            query: Texto da pergunta do usuario.
            cache: Quando informado, usado como fast-path de cache.

        Returns:
            Vetor de dimensao ``self.dim``.
        """
        if cache is not None:
            try:
                cached = cache.get(query)
            except RuntimeError as exc:
                _logger.warning("embeddings cache get falhou: %s", exc)
                cached = None  # cache corrompido -> recalcula
            if cached is not None:
                return cached
        vec: list[float] = self.embed([query])[0]
        if cache is not None:
            try:
                cache.put(query, vec)
            except Exception as exc:  # noqa: BLE001 — defensivo
                _logger.warning("embeddings cache put falhou: %s", exc)
                pass
        return vec

    def __repr__(self) -> str:
        status: str = "loaded" if self.model_loaded else "not loaded"
        return (
            f"EmbeddingProvider(model_name={self._model_name!r}, "
            f"status={status!r}, dtype={self._dtype!r})"
        )