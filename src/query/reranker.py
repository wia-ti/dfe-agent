"""Re-ranker cross-encoder opt-in (Sprint 2, Fase 15).

Quando habilitado (via ``enable_rerank=True`` no QueryEngine), recebe
o top-N candidatos do ANN/busca semantica, pontua cada um contra a
pergunta usando um cross-encoder e retorna o top-K re-ordenado.

Por que opt-in:
    - Cross-encoder adiciona latencia em CPU lenta (ate 200ms por query
      em CPU comum para top-10) e e custoso para grandes `N`.
    - Benchmark Fase 16 mede recall@5 antes/depois; so habilite se
      MRR/citation_rate melhorarem de forma mensuravel.
    - Em ausencia do modelo (rede off / modelo inexistente), fallback
      gracas para o ranking original sem rerank.
"""
from __future__ import annotations

from typing import Callable, Iterable, Protocol

from src.db.vector_store import ScoredChunk
from src.utils.logger import get_logger


_logger = get_logger(__name__)


class CrossEncoderLike(Protocol):
    """Protocol duck-typed — qualquer objeto ``predict(list[str]) -> list[float]``."""

    def predict(self, pairs: list[list[str]]) -> list[float]:  # type: ignore[no-untyped-def]
        ...


class CrossEncoderReranker:
    """Reranker via cross-encoder HuggingFace.

    Lazy load do modelo na primeira chamada (download + load).
    Em caso de erro de rede / modelo inexistente, levanta ``RuntimeError``
    e :class:`QueryEngine` cai para o ranking original.
    """

    DEFAULT_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        predict_fn: Callable[[list[list[str]]], list[float]] | None = None,
    ) -> None:
        """Args:
        model_name: Nome HuggingFace do cross-encoder.
        predict_fn: Para testes — substitui a chamada real ao modelo.
            Assina ``(pairs) -> list[float]`` onde cada par e
            ``[query, candidate]``."""
        self._model_name: str = model_name
        self._predict_fn: Callable[[list[list[str]]], list[float]] | None = predict_fn
        self._model: object | None = None

    def _load(self) -> CrossEncoderLike:
        if self._model is None and self._predict_fn is None:
            # Lazy import: sentence_transformers CrossEncoder so quando
            # rerank for explicitamente habilitado.
            from sentence_transformers import CrossEncoder  # type: ignore

            self._model = CrossEncoder(self._model_name)
        return self._model  # type: ignore[return-value]

    def rerank(
        self,
        question: str,
        chunks: list[ScoredChunk],
        top_k: int,
    ) -> list[ScoredChunk]:
        """Re-ordena ``chunks`` retornando top-K com score rerank.

        Args:
            question: Pergunta original.
            chunks: Candidatos ja ranqueados (top-N da busca inicial).
            top_k: Quantos devolver no final.

        Returns:
            Lista de ScoredChunk com ``score`` substituído pela
            pontuacao do cross-encoder (logit). Em caso de erro
            documentado, levanta ``RuntimeError`` para o caller
            (QueryEngine) fazer fallback gracioso.
        """
        if not chunks:
            return []
        pairs: list[list[str]] = [[question, c.text] for c in chunks]
        try:
            if self._predict_fn is not None:
                scores: list[float] = list(self._predict_fn(pairs))
            else:
                model: CrossEncoderLike = self._load()
                scores = list(model.predict(pairs))
        except Exception as exc:  # noqa: BLE001
            _logger.warning("reranker cross-encoder falhou: %s", exc)
            raise RuntimeError(
                f"cross-encoder indisponivel: {exc}"
            ) from exc

        if len(scores) != len(chunks):
            raise RuntimeError(
                f"cross-encoder devolveu {len(scores)} scores para "
                f"{len(chunks)} chunks"
            )

        scored: list[tuple[float, ScoredChunk]] = sorted(
            zip(scores, chunks), key=lambda x: x[0], reverse=True
        )
        out: list[ScoredChunk] = []
        for s, c in scored[:top_k]:
            out.append(
                ScoredChunk(
                    text=c.text,
                    source_url=c.source_url,
                    doc_title=c.doc_title,
                    score=float(s),
                    document_id=c.document_id,
                    published_at=c.published_at,
                    section_path=c.section_path,
                    section_level=c.section_level,
                    kind=c.kind,
                    parent_text=c.parent_text,
                )
            )
        return out


__all__ = ["CrossEncoderLike", "CrossEncoderReranker"]
