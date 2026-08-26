"""Testes adicionais de logging em fallback paths do ``QueryEngine`` (PLAN_SPRINT4 E.2).

Garante que cada ``except Exception`` no ``query_engine.py`` registra
warning via ``logger.warning(...)`` antes do retorno de fallback.

Cobertura minima exigida: 95% em ``src/query/query_engine.py``.

Nota: o logger factory ``src.utils.logger.get_logger`` configura
``propagate=False`` (anti-duplicacao com handlers do host). Portanto
capturamos via handler customizado anexado diretamente ao logger,
nao via ``caplog`` (que atua no root).
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

from src.db.vector_store import ScoredChunk, VectorStore
from src.indexer.embeddings import EmbeddingProvider
from src.query.query_engine import QueryEngine


class _RecordingHandler(logging.Handler):
    """Handler que registra todas as mensagens em uma lista."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _scored(text: str, score: float, document_id: int = 0) -> ScoredChunk:
    return ScoredChunk(
        text=text,
        source_url=f"https://nfe.fazenda.gov.br/{text}",
        doc_title=text,
        score=score,
        document_id=document_id,
    )


def test_search_logs_warning_on_embedding_failure() -> None:
    """Quando ``embedder.embed`` levanta ``RuntimeError``, loga warning."""
    vector_store = MagicMock(spec=VectorStore)
    embedder = MagicMock(spec=EmbeddingProvider)
    embedder.embed_query_cached.side_effect = RuntimeError("model not loaded")

    engine = QueryEngine(vector_store, embedder)

    qe_logger = logging.getLogger("src.query.query_engine")
    handler = _RecordingHandler()
    qe_logger.addHandler(handler)
    try:
        result: list[ScoredChunk] = engine.search("qualquer pergunta")
    finally:
        qe_logger.removeHandler(handler)

    assert result == []
    messages: list[str] = [r.getMessage() for r in handler.records]
    assert any("model not loaded" in m for m in messages), (
        f"Esperado warning com substring 'model not loaded'. "
        f"Messages: {messages}"
    )


def test_search_logs_warning_on_vector_store_failure() -> None:
    """Quando ``vector_store.search`` levanta, loga warning e retorna []."""
    vector_store = MagicMock(spec=VectorStore)
    vector_store.search.side_effect = RuntimeError("db corrompido")
    embedder = MagicMock(spec=EmbeddingProvider)
    embedder.embed.return_value = [[0.1, 0.2, 0.3, 0.4]]

    engine = QueryEngine(vector_store, embedder)

    qe_logger = logging.getLogger("src.query.query_engine")
    handler = _RecordingHandler()
    qe_logger.addHandler(handler)
    try:
        result: list[ScoredChunk] = engine.search("pergunta")
    finally:
        qe_logger.removeHandler(handler)

    assert result == []
    messages: list[str] = [r.getMessage() for r in handler.records]
    assert any("db corrompido" in m for m in messages), (
        f"Esperado warning com substring 'db corrompido'. "
        f"Messages: {messages}"
    )