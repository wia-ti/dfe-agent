from __future__ import annotations

import math
from datetime import datetime, timezone

from src.db.doc_summaries import DocSummaryStore
from src.db.fts_store import FtsHit, FtsStore
from src.db.vector_store import ScoredChunk, VectorStore
from src.indexer.embeddings import EmbeddingProvider
from src.query.constants import (
    DEFAULT_TOP_K,
    HIERARCHICAL_TOP_DOCS,
    HYBRID_RRF_K,
    MAX_CANDIDATES_PER_QUERY,
    MIN_RELEVANCE_SCORE,
    RECENCY_HALF_LIFE_DAYS,
    RECENCY_WEIGHT,
    RERANK_CANDIDATES_MULTIPLIER,
    RERANK_DEFAULT,
)
from src.query.embedding_cache import QueryEmbeddingCache
from src.query.reranker import CrossEncoderReranker
from src.utils.logger import get_logger


_logger = get_logger(__name__)


def _now_naive_utc() -> datetime:
    """Retorna datetime naive em UTC (compat com Python 3.12+)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _recency_score(published_at: datetime | None, now: datetime, half_life_days: float) -> float:
    """Calcula score de recencia via decaimento exponencial.

    Retorna 1.0 se a publicacao for AGORA (delta=0).
    Retorna 0.5 se a publicacao for ha ``half_life_days`` dias.
    Tende a 0.0 conforme a publicacao fica muito antiga.
    Se ``published_at`` for None, retorna 0.5 (neutro — nao premia nem penaliza).
    """
    if published_at is None:
        return 0.5
    delta_days = (now - published_at).total_seconds() / 86400.0
    if delta_days < 0:
        delta_days = 0.0  # publicacao no futuro (clock skew) — tratar como atual
    return math.exp(-delta_days / half_life_days)


def _rrf_fuse(
    sem: list[ScoredChunk],
    bm25: list[FtsHit],
    k: int,
) -> dict[int, ScoredChunk]:
    """Reciprocal Rank Fusion entre semantico e BM25 usando ``document_id`` como chave.

    Score final = sum_fontes 1 / (k + rank_d + 1). Documentos presentes em
    ambas as listas recebem boost de intersecao.

    Para documentos so em BM25 (sem published_at / metadata rica), os
    campos ``published_at``, ``section_*`` ficam com defaults; o URL/titulo
    vem do ``FtsHit``.

    Args:
        sem: Resultados do VectorStore ja filtrados por ``min_score``.
        bm25: Resultados do FtsStore ja ordenados por BM25.
        k: Constante de smoothing (paper original usa 60).

    Returns:
        Mapa ``document_id -> ScoredChunk`` com o score RRF ja aplicado.
    """
    fused: dict[int, ScoredChunk] = {}

    for rank, hit in enumerate(sem):
        score = 1.0 / (k + rank + 1)
        existing = fused.get(hit.document_id)
        if existing is None:
            fused[hit.document_id] = ScoredChunk(
                text=hit.text,
                source_url=hit.source_url,
                doc_title=hit.doc_title,
                score=score,
                document_id=hit.document_id,
                published_at=hit.published_at,
                section_path=hit.section_path,
                section_level=hit.section_level,
            )
        else:
            existing.score += score

    for rank, hit in enumerate(bm25):
        score = 1.0 / (k + rank + 1)
        existing = fused.get(hit.document_id)
        if existing is None:
            fused[hit.document_id] = ScoredChunk(
                text=hit.text,
                source_url=hit.source_url,
                doc_title=hit.doc_title,
                score=score,
                document_id=hit.document_id,
                published_at=None,
                section_path=hit.section_path,
                section_level=hit.section_level,
            )
        else:
            # Boost de intersecao: doc ja no ranking semantico ganha
            # RRF adicional do BM25. Quando for o unico hit, mantemos
            # metadados do vetorial (tem published_at etc).
            existing.score += score

    return fused


class QueryEngine:
    """Camada de busca: semantica + BM25 + boost temporal + dedup por documento.

    Sem ``fts_store`` (Sprint 1 / Fase 6.1): apenas semantica + boost + dedup.
    Com ``fts_store`` (Sprint 2 / Fase 11): hybrid via Reciprocal Rank Fusion
    (RRF) entre os rankings semantico e BM25; boost temporal ainda aplicado
    apos o RRF.
    Com ``summary_store`` (Sprint 2 / Fase 12): two-stage retrieval
    ``[embedding -> summary top-K -> chunks filtered]``. Note que
    ``search_hierarchical`` e acessado apenas via metodo explicito
    (``search`` nao muda o default) — o caller precisa opt-in.

    Score final de cada hit:

        score_final = (1 - recency_weight) * score_rrf
                    + recency_weight * recencia(published_at)
    """

    def __init__(
        self,
        vector_store: VectorStore,
        embedder: EmbeddingProvider,
        fts_store: FtsStore | None = None,
        summary_store: DocSummaryStore | None = None,
        embedding_cache: QueryEmbeddingCache | None = None,
        reranker: CrossEncoderReranker | None = None,
        enable_rerank: bool = RERANK_DEFAULT,
        top_k: int = DEFAULT_TOP_K,
        min_score: float = MIN_RELEVANCE_SCORE,
        recency_weight: float = RECENCY_WEIGHT,
        recency_half_life_days: float = RECENCY_HALF_LIFE_DAYS,
        rrf_k: int = HYBRID_RRF_K,
        hierarchical_top_docs: int = HIERARCHICAL_TOP_DOCS,
        max_candidates: int = MAX_CANDIDATES_PER_QUERY,
    ) -> None:
        self._vector_store: VectorStore = vector_store
        self._embedder: EmbeddingProvider = embedder
        self._fts_store: FtsStore | None = fts_store
        self._summary_store: DocSummaryStore | None = summary_store
        self._embedding_cache: QueryEmbeddingCache | None = embedding_cache
        self._reranker: CrossEncoderReranker | None = reranker
        self._enable_rerank: bool = enable_rerank
        self._top_k: int = top_k
        self._min_score: float = min_score
        self._recency_weight: float = recency_weight
        self._recency_half_life_days: float = recency_half_life_days
        self._rrf_k: int = rrf_k
        self._hierarchical_top_docs: int = hierarchical_top_docs
        self._max_candidates: int = max_candidates

    def search(self, question: str) -> list[ScoredChunk]:
        """Atalho: usa search_hybrid se fts_store foi configurado; senao
        delega para o caminho pre-Sprint-2 (apenas semantico).
        NUNCA chama search_hierarchical automaticamente (opt-in).

        Fase 15: aplica re-rank cross-encoder quando ``enable_rerank=True``.
        Erros do reranker (rede off / modelo inexistente) sao
        silenciosamente absorvidos pelo fallback gracas.
        """
        if self._fts_store is None:
            hits = self._search_semantic_only(question)
        else:
            hits = self.search_hybrid(question)
        return self._apply_rerank(question, hits)

    def _apply_rerank(
        self, question: str, hits: list[ScoredChunk]
    ) -> list[ScoredChunk]:
        """Aplica cross-encoder opt-in (Fase 15); retorna ranking original em fallback."""
        if not self._enable_rerank or self._reranker is None or not hits:
            return hits
        top_k: int = self._top_k
        pool_size: int = min(
            len(hits), top_k * RERANK_CANDIDATES_MULTIPLIER
        )
        try:
            reranked: list[ScoredChunk] = self._reranker.rerank(
                question, hits[:pool_size], top_k=top_k
            )
            return reranked
        except Exception as exc:  # noqa: BLE001 — fallback gracas
            _logger.warning("query_engine rerank fallback: %s", exc)
            return hits[:top_k]

    def search_hierarchical(self, question: str) -> list[ScoredChunk]:
        """Two-stage retrieval (Fase 12.2):

        1. Embedding da pergunta.
        2. ``summary_store.find_similar_summaries``: top-N documentos via
           cosseno sobre embeddings de summaries persistidos pelo
           RagIndexer (Fase 12.1).
        3. ``vector_store.search(query_embedding, document_ids=top_N)``:
           ANN filtrado aos docs selecionados.
        4. Boost temporal + top-K.

        Sem ``summary_store`` (ou corpus vazio): degenera para
        ``_search_semantic_only`` — sem restricao de document_ids.

        NUNCA levanta excecao. Retorna [] quando algo falha.
        """
        try:
            query_embedding: list[float] = self._embed_query_cached(question)

            document_ids: list[int] | None = self._safe_hierarchical_top_docs(
                query_embedding
            )

            if document_ids is None:
                # Sem filtro coarse: caminho normal.
                return self._search_semantic_only_with_embedding(query_embedding)

            sem_hits: list[ScoredChunk] = self._vector_store.search(
                query_embedding,
                top_k=self._max_candidates,
                document_ids=document_ids,
            )
            sem_filtered: list[ScoredChunk] = [
                c for c in sem_hits if c.score >= self._min_score
            ]
            # Dedup ja nao precisa ser aplicado agressivamente: o filtro coarse
            # ja colapsa para N docs; basta manter o melhor chunk por doc.
            best_by_doc: dict[int, ScoredChunk] = {}
            for c in sem_filtered:
                cur = best_by_doc.get(c.document_id)
                if cur is None or c.score > cur.score:
                    best_by_doc[c.document_id] = c

            boosted = list(best_by_doc.values())
            return self._apply_recency_and_topk(  # type: ignore[arg-type]
                {c.document_id: c for c in boosted}
            )
        except Exception as exc:  # noqa: BLE001
            _logger.warning("query_engine hierarchical fallback: %s", exc)
            return []

    def _safe_hierarchical_top_docs(
        self, query_embedding: list[float]
    ) -> list[int] | None:
        """Invoca ``summary_store.find_similar_summaries`` retornando IDs.

        Retorna ``None`` quando o corpus esta vazio (degeneracao para
        busca sem restricao). Tolera erros silenciosos (documenta como
        fallback para busca normal).
        """
        if self._summary_store is None:
            return None
        try:
            scored = self._summary_store.find_similar_summaries(
                query_embedding, top_k=self._hierarchical_top_docs
            )
        except Exception as exc:  # noqa: BLE001
            _logger.warning("query_engine summary_store fallback: %s", exc)
            return None
        if not scored:
            return None
        return [s.document_id for s in scored]

    def _search_semantic_only_with_embedding(
        self, query_embedding: list[float]
    ) -> list[ScoredChunk]:
        """Caminho pre-Sprint-2 usando embedding pre-computado."""
        try:
            sem_candidates = self._vector_store.search(
                query_embedding, top_k=self._max_candidates
            )
            sem_filtered = [
                c for c in sem_candidates if c.score >= self._min_score
            ]
            now = _now_naive_utc()
            boosted: list[ScoredChunk] = []
            for c in sem_filtered:
                rec = _recency_score(
                    c.published_at, now, self._recency_half_life_days
                )
                final = (
                    (1.0 - self._recency_weight) * c.score
                    + self._recency_weight * rec
                )
                boosted.append(
                    ScoredChunk(
                        text=c.text,
                        source_url=c.source_url,
                        doc_title=c.doc_title,
                        score=final,
                        document_id=c.document_id,
                        published_at=c.published_at,
                        section_path=c.section_path,
                        section_level=c.section_level,
                    )
                )
            best_by_doc: dict[int, ScoredChunk] = {}
            for c in boosted:
                cur = best_by_doc.get(c.document_id)
                if cur is None or c.score > cur.score:
                    best_by_doc[c.document_id] = c
            ranked = sorted(
                best_by_doc.values(), key=lambda c: c.score, reverse=True
            )
            return ranked[: self._top_k]
        except Exception as exc:  # noqa: BLE001
            _logger.warning("query_engine semantic_only fallback: %s", exc)
            return []

    def search_hybrid(self, question: str) -> list[ScoredChunk]:
        """Busca hibrida via RRF entre vetorial (cosine) e FTS5 (BM25).

        Algoritmo:
            1. Embedding da pergunta.
            2. Top-N semantico via ``vector_store.search``.
            3. Top-N textual via ``fts_store.search_fts`` (silencioso se
               indisponivel — FTS5 indisponivel nao derruba a busca).
            4. Filtra semantico por ``min_score``.
            5. RRF combina os dois rankings por ``document_id``.
            6. Boost temporal aplicado por hit (preserva published_at do
               semantico quando existir; neutro p/ docs so em BM25).
            7. Top-K.

        NUNCA levanta excecao: se qualquer etapa falhar (incluindo FTS5
        indisponivel ou query invalida), degrada para o ranking
        disponivel.
        """
        try:
            sem_candidates: list[ScoredChunk] = self._search_semantic_raw(question)
            sem_filtered: list[ScoredChunk] = [
                c for c in sem_candidates if c.score >= self._min_score
            ]

            bm25_hits: list[FtsHit] = self._safe_fts_search(question)

            fused: dict[int, ScoredChunk] = _rrf_fuse(
                sem_filtered, bm25_hits, k=self._rrf_k
            )

            return self._apply_recency_and_topk(fused)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("query_engine hybrid fallback: %s", exc)
            return []

    def _search_semantic_only(self, question: str) -> list[ScoredChunk]:
        """Caminho pre-Sprint-2: so semantica + dedup + boost temporal."""
        try:
            query_embedding: list[float] = self._embed_query_cached(question)
            return self._search_semantic_only_with_embedding(query_embedding)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("query_engine search_semantic_only fallback: %s", exc)
            return []

    def _embed_query_cached(self, question: str) -> list[float]:
        """Wrapper sobre embedder.embed que respeita o cache (Fase 13)."""
        return self._embedder.embed_query_cached(question, self._embedding_cache)

    def _search_semantic_raw(self, question: str) -> list[ScoredChunk]:
        """Embedding + vector_store.search cru (sem filtro / boost)."""
        query_embedding: list[float] = self._embed_query_cached(question)
        return self._vector_store.search(
            query_embedding, top_k=self._max_candidates
        )

    def _safe_fts_search(self, question: str) -> list[FtsHit]:
        """Encapsula ``fts_store.search_fts`` com tolerancia a falha."""
        if self._fts_store is None:
            return []
        try:
            return self._fts_store.search_fts(
                question, top_k=self._max_candidates
            )
        except Exception as exc:  # noqa: BLE001
            _logger.warning("query_engine fts_search fallback: %s", exc)
            return []

    def _apply_recency_and_topk(
        self, fused: dict[int, ScoredChunk]
    ) -> list[ScoredChunk]:
        """Aplica boost temporal e ordena, retornando top-K."""
        now = _now_naive_utc()
        boosted: list[ScoredChunk] = []
        for hit in fused.values():
            rec = _recency_score(
                hit.published_at, now, self._recency_half_life_days
            )
            final = (
                (1.0 - self._recency_weight) * hit.score
                + self._recency_weight * rec
            )
            boosted.append(
                ScoredChunk(
                    text=hit.text,
                    source_url=hit.source_url,
                    doc_title=hit.doc_title,
                    score=final,
                    document_id=hit.document_id,
                    published_at=hit.published_at,
                    section_path=hit.section_path,
                    section_level=hit.section_level,
                )
            )
        ranked = sorted(boosted, key=lambda c: c.score, reverse=True)
        return ranked[: self._top_k]

    @property
    def min_score(self) -> float:
        return self._min_score

    @property
    def top_k(self) -> int:
        return self._top_k

    @property
    def hierarchical_top_docs(self) -> int:
        return self._hierarchical_top_docs
