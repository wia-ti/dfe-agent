from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from src.db.vector_store import ScoredChunk, VectorStore
from src.indexer.embeddings import EmbeddingProvider
from src.query.constants import (
    DEFAULT_TOP_K,
    MAX_CANDIDATES_PER_QUERY,
    MIN_RELEVANCE_SCORE,
    RECENCY_HALF_LIFE_DAYS,
    RECENCY_WEIGHT,
)
from src.query.query_engine import QueryEngine, _recency_score


def _scored(
    text: str,
    score: float,
    document_id: int = 0,
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


def test_query_engine_filters_below_min_score():
    """Chunks com score abaixo de min_score sao descartados."""
    vector_store = MagicMock(spec=VectorStore)
    embedder = MagicMock(spec=EmbeddingProvider)
    embedder.embed.return_value = [[0.1, 0.2, 0.3, 0.4]]
    vector_store.search.return_value = [
        _scored("relevante", 0.95, document_id=1),
        _scored("parcial", 0.7, document_id=2),
        _scored("irrelevante", 0.3, document_id=3),
    ]

    engine = QueryEngine(vector_store, embedder, min_score=0.5)
    results = engine.search("pergunta relevante")

    assert len(results) == 2
    assert all(r.score >= 0.5 for r in results)
    assert results[0].text == "relevante"
    assert results[1].text == "parcial"


def test_query_engine_returns_empty_when_vector_store_empty():
    """Quando vector_store retorna [], QueryEngine retorna []."""
    vector_store = MagicMock(spec=VectorStore)
    embedder = MagicMock(spec=EmbeddingProvider)
    embedder.embed.return_value = [[0.1, 0.2]]
    vector_store.search.return_value = []

    engine = QueryEngine(vector_store, embedder)
    results = engine.search("foo")

    assert results == []


def test_query_engine_calls_embedder_exactly_once_with_single_text():
    """QueryEngine.search('foo') chama embedder.embed exatamente uma vez com ['foo']."""
    vector_store = MagicMock(spec=VectorStore)
    embedder = MagicMock(spec=EmbeddingProvider)
    embedder.embed.return_value = [[0.1, 0.2]]
    vector_store.search.return_value = []

    engine = QueryEngine(vector_store, embedder)
    engine.search("foo")

    # Fase 13: agora via embed_query_cached. Verifica que wrapped foi
    # chamado com 'foo' (cache=None -> cai para embed direto).
    embedder.embed_query_cached.assert_called_once_with("foo", None)


def test_query_engine_uses_max_candidates_as_default():
    """Quando top_k nao e passado, vector_store recebe max_candidates (30) para
    permitir dedup por documento + boost temporal."""
    vector_store = MagicMock(spec=VectorStore)
    embedder = MagicMock(spec=EmbeddingProvider)
    embedder.embed.return_value = [[0.1, 0.2]]
    vector_store.search.return_value = []

    engine = QueryEngine(vector_store, embedder)
    engine.search("foo")

    args, kwargs = vector_store.search.call_args
    assert kwargs.get("top_k") == MAX_CANDIDATES_PER_QUERY or (
        len(args) > 1 and args[1] == MAX_CANDIDATES_PER_QUERY
    )


def test_query_engine_default_constants():
    """DEFAULT_TOP_K, MIN_RELEVANCE_SCORE, RECENCY_* tem os valores esperados."""
    assert MIN_RELEVANCE_SCORE == 0.5
    assert DEFAULT_TOP_K == 5
    assert 0.0 <= RECENCY_WEIGHT <= 1.0
    assert RECENCY_HALF_LIFE_DAYS > 0


def test_query_engine_custom_top_k_passed_through():
    """top_k customizado e respeitado no resultado final (apos dedup por doc)."""
    vector_store = MagicMock(spec=VectorStore)
    embedder = MagicMock(spec=EmbeddingProvider)
    embedder.embed.return_value = [[0.1, 0.2]]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    vector_store.search.return_value = [
        _scored(f"d{i}", 0.7, document_id=i, published_at=now) for i in range(10)
    ]

    engine = QueryEngine(vector_store, embedder, top_k=3)
    results = engine.search("foo")

    assert len(results) == 3


def test_query_engine_returns_empty_on_exception():
    """Quando embedder.embed levanta excecao, QueryEngine retorna [] graciosamente."""
    vector_store = MagicMock(spec=VectorStore)
    embedder = MagicMock(spec=EmbeddingProvider)
    embedder.embed.side_effect = RuntimeError("model offline")

    engine = QueryEngine(vector_store, embedder)
    results = engine.search("foo")

    assert results == []


def test_query_engine_exposes_min_score_and_top_k_properties():
    """Properties min_score e top_k retornam os valores configurados."""
    vector_store = MagicMock(spec=VectorStore)
    embedder = MagicMock(spec=EmbeddingProvider)

    engine = QueryEngine(vector_store, embedder, top_k=7, min_score=0.8)

    assert engine.min_score == 0.8
    assert engine.top_k == 7


# --- Boost temporal ---


def test_recency_score_returns_1_for_just_published() -> None:
    """Chunk com published_at == now tem recencia maxima (1.0)."""
    now = datetime(2026, 1, 1, 12, 0, 0)
    score = _recency_score(now, now, half_life_days=180.0)
    assert score == 1.0


def test_recency_score_at_half_life_is_exp_minus_one() -> None:
    """Chunk com idade = half_life tem recencia = exp(-1) ~= 0.368.

    Nota: decaimento exponencial significa que em t=half_life o valor e exp(-1),
    NAO 0.5. (Half-life no sentido de radioatividade, onde a quantidade cai pela
    metade, exige o fator ln(2) que multiplica o expoente — optamos pelo
    modelo exponencial puro por ser mais estavel numericamente.)
    """
    now = datetime(2026, 1, 1)
    pub = datetime(2025, 7, 5)  # 180 dias antes (== half_life)
    score = _recency_score(pub, now, half_life_days=180.0)
    assert 0.35 < score < 0.40


def test_recency_score_halves_between_two_and_three_half_lives() -> None:
    """Entre 1 e 2 half-lives o score cai pela metade (dec. exponencial)."""
    now = datetime(2026, 1, 1)
    pub1 = datetime(2025, 7, 5)  # 180 dias (= 1 half_life)
    pub2 = datetime(2024, 7, 8)  # 542 dias (~ 3 half_lives)
    s1 = _recency_score(pub1, now, half_life_days=180.0)
    s2 = _recency_score(pub2, now, half_life_days=180.0)
    # s2 ~= exp(-3) ~= 0.05; s1 ~= exp(-1) ~= 0.37
    assert s2 < 0.10
    assert s1 / s2 > 5  # s1 e muito maior que s2


def test_recency_score_returns_neutral_when_published_at_is_none() -> None:
    """Sem data de publicacao, score de recencia e neutro (0.5)."""
    score = _recency_score(None, datetime(2026, 1, 1), half_life_days=180.0)
    assert score == 0.5


def test_recency_score_handles_future_publication_as_now() -> None:
    """published_at no futuro (clock skew) e tratado como atual (score=1.0)."""
    now = datetime(2026, 1, 1)
    future = datetime(2027, 1, 1)
    score = _recency_score(future, now, half_life_days=180.0)
    assert score == 1.0


def test_query_engine_prefers_recent_chunk_with_equal_semantic_score() -> None:
    """Dois chunks com MESMA score semantica: o mais recente ganha."""
    vector_store = MagicMock(spec=VectorStore)
    embedder = MagicMock(spec=EmbeddingProvider)
    embedder.embed.return_value = [[0.1, 0.2]]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    old = now - timedelta(days=730)  # 2 anos atras
    vector_store.search.return_value = [
        _scored("antigo", 0.8, document_id=1, published_at=old),
        _scored("recente", 0.8, document_id=2, published_at=now),
    ]

    engine = QueryEngine(
        vector_store, embedder, top_k=2, min_score=0.5, recency_weight=0.5
    )
    results = engine.search("foo")

    assert len(results) == 2
    assert results[0].text == "recente"
    assert results[1].text == "antigo"


def test_query_engine_zero_recency_weight_uses_only_semantic() -> None:
    """Com recency_weight=0, ranking e puramente semantico (sem boost)."""
    vector_store = MagicMock(spec=VectorStore)
    embedder = MagicMock(spec=EmbeddingProvider)
    embedder.embed.return_value = [[0.1, 0.2]]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    old = now - timedelta(days=730)
    vector_store.search.return_value = [
        _scored("antigo", 0.9, document_id=1, published_at=old),
        _scored("recente", 0.7, document_id=2, published_at=now),
    ]

    engine = QueryEngine(
        vector_store, embedder, top_k=2, min_score=0.5, recency_weight=0.0
    )
    results = engine.search("foo")

    assert results[0].text == "antigo"  # score maior vence
    assert results[1].text == "recente"


# --- Dedup por document_id ---


def test_query_engine_dedup_collapses_chunks_from_same_document() -> None:
    """Multiplos chunks do mesmo document_id sao colapsados em 1."""
    vector_store = MagicMock(spec=VectorStore)
    embedder = MagicMock(spec=EmbeddingProvider)
    embedder.embed.return_value = [[0.1, 0.2]]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    vector_store.search.return_value = [
        _scored("chunk-A1", 0.9, document_id=1, published_at=now),
        _scored("chunk-A2", 0.85, document_id=1, published_at=now),
        _scored("chunk-A3", 0.8, document_id=1, published_at=now),
        _scored("chunk-B1", 0.7, document_id=2, published_at=now),
        _scored("chunk-B2", 0.65, document_id=2, published_at=now),
    ]

    engine = QueryEngine(vector_store, embedder, top_k=5, min_score=0.5)
    results = engine.search("foo")

    assert len(results) == 2  # 1 por document_id
    assert results[0].document_id == 1
    assert results[1].document_id == 2


def test_query_engine_dedup_keeps_highest_score_per_document() -> None:
    """Dentro de cada document_id, mantem-se o chunk com maior score_final."""
    vector_store = MagicMock(spec=VectorStore)
    embedder = MagicMock(spec=EmbeddingProvider)
    embedder.embed.return_value = [[0.1, 0.2]]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    vector_store.search.return_value = [
        _scored("low", 0.6, document_id=1, published_at=now),
        _scored("high", 0.95, document_id=1, published_at=now),
        _scored("medium", 0.7, document_id=1, published_at=now),
    ]

    engine = QueryEngine(vector_store, embedder, top_k=5, min_score=0.5)
    results = engine.search("foo")

    assert len(results) == 1
    assert results[0].text == "high"


def test_query_engine_dedup_then_limits_to_top_k() -> None:
    """Apos dedup, retorna no maximo top_k documentos."""
    vector_store = MagicMock(spec=VectorStore)
    embedder = MagicMock(spec=EmbeddingProvider)
    embedder.embed.return_value = [[0.1, 0.2]]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    vector_store.search.return_value = [
        _scored(f"c{i}", 0.9 - i * 0.01, document_id=i, published_at=now)
        for i in range(20)
    ]

    engine = QueryEngine(vector_store, embedder, top_k=3, min_score=0.5)
    results = engine.search("foo")

    assert len(results) == 3
    assert [r.document_id for r in results] == [0, 1, 2]