"""Testes para Sprint 2, Fase 11.2: QueryEngine.search_hybrid + RRF.

Cobre:
    - ``search_hybrid`` combina ranking semantico + BM25 via RRF.
    - Chunk achado por BM25 mas nao por semantica aparece no resultado.
    - Chunk achado por semantica mas nao por BM25 aparece no resultado.
    - Chunk achado pelos dois tem score RRF maior (boost de intersecao).
    - ``search()`` quando ``fts_store`` nao e fornecido delega para
      ``search_hybrid`` com apenas a lista semantica (degradacao graca).
    - ``search()`` quando ``fts_store=None`` mantem comportamento
      pre-Sprint-2 (sem RRF).
    - Parametro ``rrf_k`` configuravel.
    - ``search_hybrid`` respeita ``top_k`` no resultado final.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from src.db.fts_store import FtsHit, FtsStore
from src.db.vector_store import ScoredChunk, VectorStore
from src.indexer.embeddings import EmbeddingProvider
from src.query.query_engine import QueryEngine

# ruff: noqa: E402  -- tempo de import nao importa, mas mantemos ordem alfabetica


def _scored(
    text: str,
    score: float,
    document_id: int,
    published_at: datetime | None = None,
) -> ScoredChunk:
    return ScoredChunk(
        text=text,
        source_url=f"https://nfe.fazenda.gov.br/{text}",
        doc_title=text,
        score=score,
        document_id=document_id,
        published_at=published_at,
    )


def _fts_hit(doc_id: int, text: str, chunk_idx: int = 0) -> FtsHit:
    return FtsHit(
        document_id=doc_id,
        chunk_index=chunk_idx,
        text=text,
        source_url=f"https://nfe.fazenda.gov.br/d{doc_id}",
        doc_title=f"T{doc_id}",
        bm25_score=-1.5,
    )


# --- search_hybrid --------------------------------------------------------


def test_search_hybrid_retorna_intersecao_e_uniao() -> None:
    """Semantic: doc 1. BM25: doc 2. Hybrid: ambos, doc 1 com score maior (R=2)."""
    vs = MagicMock(spec=VectorStore)
    fts = MagicMock(spec=FtsStore)
    embedder = MagicMock(spec=EmbeddingProvider)
    embedder.embed.return_value = [[0.1, 0.2]]
    vs.search.return_value = [_scored("semantic-1", 0.9, document_id=1)]
    fts.search_fts.return_value = [_fts_hit(doc_id=2, text="bm25-2")]

    engine = QueryEngine(vs, embedder, fts_store=fts, top_k=5, min_score=0.0)
    results = engine.search("pergunta")

    urls: set[int] = {r.document_id for r in results}
    assert 1 in urls and 2 in urls  # ambos aparecem


def test_search_hybrid_boost_para_chunk_em_ambas_as_listas() -> None:
    """Mesmo chunk nos dois rankings: score RRF e maior que o de um so."""
    vs = MagicMock(spec=VectorStore)
    fts = MagicMock(spec=FtsStore)
    embedder = MagicMock(spec=EmbeddingProvider)
    embedder.embed.return_value = [[0.1, 0.2]]
    # Semantic: ranking = [doc1, doc2]
    vs.search.return_value = [
        _scored("s1", 0.95, document_id=1),
        _scored("s2", 0.8, document_id=2),
    ]
    # BM25: ranking = [doc1, doc3]
    fts.search_fts.return_value = [
        _fts_hit(doc_id=1, text="b1"),
        _fts_hit(doc_id=3, text="b3"),
    ]

    engine = QueryEngine(vs, embedder, fts_store=fts, rrf_k=60, min_score=0.0)
    results = engine.search("q")

    by_doc = {r.document_id: r.score for r in results}
    # doc1 aparece nas duas listas (rank 1) → score mais alto
    assert by_doc[1] > by_doc[2]
    assert by_doc[1] > by_doc[3]


def test_search_hybrid_score_e_limitado_pelo_rrf_k() -> None:
    """Com recency_weight=0, score final = score RRF, que e bounded por ``2/(k+1)``."""
    vs = MagicMock(spec=VectorStore)
    fts = MagicMock(spec=FtsStore)
    embedder = MagicMock(spec=EmbeddingProvider)
    embedder.embed.return_value = [[0.1, 0.2]]
    vs.search.return_value = [_scored("both", 0.9, document_id=1)]
    fts.search_fts.return_value = [_fts_hit(doc_id=1, text="both")]

    engine = QueryEngine(
        vs, embedder, fts_store=fts, rrf_k=60,
        min_score=0.0, recency_weight=0.0,
    )
    results = engine.search("q")

    # Sem recency boost, score = RRF simples = 2 / (60 + 1) para um hit nas duas listas.
    max_expected = 2.0 / (60 + 1)
    assert abs(results[0].score - max_expected) < 1e-9


def test_search_hybrid_respeita_top_k() -> None:
    vs = MagicMock(spec=VectorStore)
    fts = MagicMock(spec=FtsStore)
    embedder = MagicMock(spec=EmbeddingProvider)
    embedder.embed.return_value = [[0.1, 0.2]]
    vs.search.return_value = [_scored(f"s{i}", 0.9, document_id=i) for i in range(10)]
    fts.search_fts.return_value = [_fts_hit(doc_id=i, text=f"b{i}") for i in range(10)]

    engine = QueryEngine(vs, embedder, fts_store=fts, top_k=3, min_score=0.0)
    results = engine.search("q")

    assert len(results) == 3


# --- Fallback graceful ---------------------------------------------------


def test_search_sem_fts_store_delega_para_search_puro() -> None:
    """Sem fts_store, ``search`` mantem comportamento pre-Sprint-2."""
    vs = MagicMock(spec=VectorStore)
    embedder = MagicMock(spec=EmbeddingProvider)
    embedder.embed.return_value = [[0.1, 0.2]]
    vs.search.return_value = [_scored("s", 0.9, document_id=1)]

    engine = QueryEngine(vs, embedder, min_score=0.0)
    results = engine.search("q")

    assert len(results) == 1
    assert results[0].text == "s"


def test_search_com_fts_store_vazio_degrada_para_semantico() -> None:
    """FTS5 retorna [] mas semantico tem hits: resultado vem do semantico."""
    vs = MagicMock(spec=VectorStore)
    fts = MagicMock(spec=FtsStore)
    embedder = MagicMock(spec=EmbeddingProvider)
    embedder.embed.return_value = [[0.1, 0.2]]
    vs.search.return_value = [_scored("s", 0.9, document_id=1)]
    fts.search_fts.return_value = []

    engine = QueryEngine(vs, embedder, fts_store=fts, min_score=0.0)
    results = engine.search("q")

    assert len(results) >= 1
    assert results[0].text == "s"


def test_search_semantico_vazio_com_fts_retorna_fts() -> None:
    """Sem semantico mas com FTS: resultado vem so do BM25 (degradacao graca)."""
    vs = MagicMock(spec=VectorStore)
    fts = MagicMock(spec=FtsStore)
    embedder = MagicMock(spec=EmbeddingProvider)
    embedder.embed.return_value = [[0.1, 0.2]]
    vs.search.return_value = []
    fts.search_fts.return_value = [_fts_hit(doc_id=99, text="from_fts")]

    engine = QueryEngine(vs, embedder, fts_store=fts, top_k=5, min_score=0.0)
    results = engine.search("q")

    assert len(results) == 1
    assert results[0].document_id == 99
    assert results[0].text == "from_fts"


def test_search_hybrid_com_erro_no_fts_degrada_para_semantico() -> None:
    """FTS5 com erro (query invalida) nao derruba a busca semantica."""
    vs = MagicMock(spec=VectorStore)
    fts = MagicMock(spec=FtsStore)
    embedder = MagicMock(spec=EmbeddingProvider)
    embedder.embed.return_value = [[0.1, 0.2]]
    vs.search.return_value = [_scored("sem", 0.9, document_id=1)]
    fts.search_fts.side_effect = RuntimeError("fts offline")

    engine = QueryEngine(vs, embedder, fts_store=fts, min_score=0.0)
    results = engine.search("q")

    assert len(results) == 1
    assert results[0].document_id == 1


# --- Fase 13: Cache de embeddings de query --------------------------------


class _StubEmbedder(EmbeddingProvider):
    """Embedder stub que implementa ``embed`` e ``embed_query_cached`` sem modelo.

    Sobrescreve o lazy-load para retornar um vetor fixo, evitando o
    download do sentence-transformer nos testes. ``embed_query_cached``
    aqui reimplementa a logica de cache para que o teste possa observar
    o efeito (a versao real faz exatamente o mesmo).
    """

    def __init__(self, dim: int = 4) -> None:  # type: ignore[no-untyped-def]
        # NAO chama super().__init__ para evitar inicializacao do modelo.
        self._model_name: str = "stub"
        self._model = None  # type: ignore[assignment]
        from src.indexer.embeddings import EmbeddingProvider as _EP

        # dim armazenada em property via _model.get_sentence_embedding_dimension()
        # Como nao temos modelo, armazenamos direto:
        object.__setattr__(self, "_dim_stub", dim)
        self.embed_call_count: int = 0
        self.embed_query_cached_call_count: int = 0

    @property
    def dim(self) -> int:  # type: ignore[override]
        return object.__getattribute__(self, "_dim_stub")

    def _load(self):  # type: ignore[override]
        raise RuntimeError("Stub nao carrega modelo real")

    def embed(self, texts: list[str]) -> list[list[float]]:  # type: ignore[override]
        self.embed_call_count += len(texts)
        return [[0.1] * self.dim for _ in texts]

    def embed_query_cached(  # type: ignore[override]
        self, query: str, cache
    ):
        self.embed_query_cached_call_count += 1
        if cache is not None:
            cached = cache.get(query)
            if cached is not None:
                return cached
        vec = self.embed([query])[0]
        if cache is not None:
            cache.put(query, vec)
        return vec


def test_query_engine_com_cache_hit_nao_chama_embed(tmp_path: Path) -> None:
    """2a chamada com mesma pergunta e cache: a funcao ``embed`` NAO e chamada."""
    from src.query.embedding_cache import QueryEmbeddingCache
    from src.query.query_engine import QueryEngine

    vs = MagicMock(spec=VectorStore)
    fts = MagicMock(spec=FtsStore)
    embedder = _StubEmbedder(dim=4)
    vs.search.return_value = []
    fts.search_fts.return_value = []

    cache_path = tmp_path / "cache.db"
    cache = QueryEmbeddingCache(cache_path, dim=4)
    cache.init_schema()

    engine = QueryEngine(vs, embedder, fts_store=fts, embedding_cache=cache)
    engine.search("pergunta exemplo")  # miss -> embed 1 vez
    assert embedder.embed_call_count == 1
    engine.search("pergunta exemplo")  # hit -> embed 0 vezes
    assert embedder.embed_call_count == 1
    assert cache.stats()["total_hits"] >= 1


def test_query_engine_sem_cache_chama_embed_a_cada_vez() -> None:
    """Sem cache: cada search chama embed para a query."""
    from src.query.query_engine import QueryEngine

    vs = MagicMock(spec=VectorStore)
    fts = MagicMock(spec=FtsStore)
    embedder = _StubEmbedder(dim=4)
    vs.search.return_value = []
    fts.search_fts.return_value = []

    engine = QueryEngine(vs, embedder, fts_store=fts, embedding_cache=None)
    engine.search("q1")
    engine.search("q2")
    assert embedder.embed_call_count == 2


# --- Fase 12: Busca hierárquica (two-stage) -----------------------------

class _StubSummaryStore:
    """Stub minimo de DocSummaryStore para testar search_hierarchical."""

    def __init__(self, hits: list[tuple[int, float]]) -> None:
        # hits = list of (document_id, similarity_score)
        self._hits = hits

    def find_similar_summaries(
        self, query_embedding: list[float], top_k: int = 10
    ) -> list:
        from src.db.doc_summaries import ScoredSummary
        return [
            ScoredSummary(document_id=doc_id, summary=f"s{doc_id}", score=score)
            for doc_id, score in self._hits[:top_k]
        ]


def test_search_hierarchical_filtra_por_summary_e_depois_chunks() -> None:
    """First stage: ranking de summaries -> document_ids. Second stage: vec_chunks filtrados."""
    from src.db.vector_store import ScoredChunk, VectorStore
    from src.query.query_engine import QueryEngine

    vs = MagicMock(spec=VectorStore)
    fts = MagicMock(spec=FtsStore)
    embedder = MagicMock(spec=EmbeddingProvider)
    embedder.embed.return_value = [[0.1, 0.2]]
    embedder.dim = 2

    # Summary: doc 5, 7 sao os mais similares.
    summary_store = _StubSummaryStore([(5, 0.9), (7, 0.8), (1, 0.5)])
    vs.search.return_value = [
        ScoredChunk(
            text="chunk de 5", source_url="u5", doc_title="T5", score=0.95,
            document_id=5,
        ),
    ]
    fts.search_fts.return_value = []

    engine = QueryEngine(
        vs, embedder, fts_store=fts,
        summary_store=summary_store,  # type: ignore[arg-type]
        hierarchical_top_docs=2,
        min_score=0.0,
    )
    results = engine.search_hierarchical("q")

    # First stage pegou top-2 document_ids = [5, 7]
    _, kwargs = vs.search.call_args
    assert kwargs.get("document_ids") == [5, 7]


def test_search_hierarchical_quando_sem_summaries_delega_para_semantico() -> None:
    """Sem summaries: degenera para o ranking semantic puro."""
    from src.query.query_engine import QueryEngine

    vs = MagicMock(spec=VectorStore)
    fts = MagicMock(spec=FtsStore)
    embedder = MagicMock(spec=EmbeddingProvider)
    embedder.embed.return_value = [[0.1, 0.2]]
    embedder.dim = 2

    summary_store = _StubSummaryStore([])  # corpus vazio
    vs.search.return_value = [
        _scored("sem", 0.9, document_id=42),
    ]
    fts.search_fts.return_value = []

    engine = QueryEngine(
        vs, embedder, fts_store=fts,
        summary_store=summary_store,  # type: ignore[arg-type]
        min_score=0.0,
    )
    results = engine.search_hierarchical("q")

    assert len(results) >= 1
    # First stage vazio -> vector search sem filter (document_ids=None/[])
    args, kwargs = vs.search.call_args
    assert kwargs.get("document_ids") in (None, [])


def test_search_hierarchical_respeita_top_k() -> None:
    from src.query.query_engine import QueryEngine

    vs = MagicMock(spec=VectorStore)
    fts = MagicMock(spec=FtsStore)
    embedder = MagicMock(spec=EmbeddingProvider)
    embedder.embed.return_value = [[0.1, 0.2]]
    embedder.dim = 2
    summary_store = _StubSummaryStore(
        [(d, 1.0 - d * 0.05) for d in range(1, 11)]
    )
    vs.search.return_value = [
        _scored(f"chunk-{d}", 0.9, document_id=d) for d in range(10)
    ]
    fts.search_fts.return_value = []
    engine = QueryEngine(
        vs, embedder, fts_store=fts,
        summary_store=summary_store,  # type: ignore[arg-type]
        top_k=3, min_score=0.0,
    )
    results = engine.search_hierarchical("q")
    assert len(results) <= 3


# --- Boost temporal mantido ----------------------------------------------


def test_hybrid_mantem_boost_temporal_e_dedup() -> None:
    """Ranqueamento final do hybrid respeita dedup + boost temporal."""
    vs = MagicMock(spec=VectorStore)
    fts = MagicMock(spec=FtsStore)
    embedder = MagicMock(spec=EmbeddingProvider)
    embedder.embed.return_value = [[0.1, 0.2]]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    old = now.replace(year=now.year - 2)
    vs.search.return_value = [
        _scored("novo-A", 0.7, document_id=1, published_at=now),
        _scored("novo-A-dup", 0.65, document_id=1, published_at=now),
        _scored("antigo-B", 0.9, document_id=2, published_at=old),
    ]
    fts.search_fts.return_value = []

    engine = QueryEngine(
        vs, embedder, fts_store=fts, top_k=5, min_score=0.0, recency_weight=0.5
    )
    results = engine.search("q")

    # doc1 = novo + dedup, doc2 = antigo. Recencia pesa 0.5.
    by_doc = {r.document_id: r for r in results}
    assert 1 in by_doc and 2 in by_doc
    # doc1 (novo, dedup) deve ter score final maior que doc2 (antigo).
    assert by_doc[1].score > by_doc[2].score
