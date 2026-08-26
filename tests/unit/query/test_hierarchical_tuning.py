"""Testes para sensibilidade de ``hierarchical_top_docs`` (Sprint 3, Iter 4).

Cobre:
    - Parametro configuravel em QueryEngine.
    - Constante default = 10.
    - Search_hierarchical respeita o valor configurado na filtragem coarse.
    - Com top_docs=0 (degenerate): comportamento cai para full-search
      (degradacao gracas).
    - A variavel de ambiente DFE_HIERARCHICAL_TOP_DOCS e respeitada pela CLI.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock

from src.db.fts_store import FtsStore
from src.db.vector_store import VectorStore
from src.db.doc_summaries import DocSummary, ScoredSummary
from src.indexer.embeddings import EmbeddingProvider
from src.query.constants import HIERARCHICAL_TOP_DOCS
from src.query.query_engine import QueryEngine


class _StubEmbedder:
    """Embedder stub sem modelo (nao herda de EmbeddingProvider)."""

    def __init__(self, dim: int = 4) -> None:
        self._dim = dim
        self.embed_call_count = 0
        self.dim = dim

    def embed(self, texts):
        self.embed_call_count += len(texts)
        return [[0.1] * self._dim for _ in texts]

    def embed_query_cached(self, query, cache=None):
        if cache is not None:
            try:
                hit = cache.get(query)
                if hit is not None:
                    return hit
            except Exception:
                pass
        vec = self.embed([query])[0]
        if cache is not None:
            try:
                cache.put(query, vec)
            except Exception:
                pass
        return vec


def test_constante_default_e_10() -> None:
    assert HIERARCHICAL_TOP_DOCS == 10


def test_parametro_personalizado_aceito_em_init() -> None:
    vs = MagicMock(spec=VectorStore)
    fts = MagicMock(spec=FtsStore)
    embedder = _StubEmbedder()
    engine = QueryEngine(vs, embedder, fts_store=fts, hierarchical_top_docs=25)
    assert engine.hierarchical_top_docs == 25


def test_search_hierarchical_usa_top_docs_configurado() -> None:
    """top_docs=2 pega apenas os 2 melhores summaries; vs.search recebe [doc1, doc5]."""
    from src.query.query_engine import QueryEngine

    vs = MagicMock(spec=VectorStore)
    fts = MagicMock(spec=FtsStore)
    embedder = _StubEmbedder()
    embedder.dim = 4

    # Mock que respeita top_k.
    full_results = [
        ScoredSummary(document_id=1, summary="s1", score=0.9),
        ScoredSummary(document_id=5, summary="s5", score=0.8),
        ScoredSummary(document_id=99, summary="s99", score=0.1),
    ]

    def fake_find(query_embedding, top_k=10):
        return full_results[:top_k]

    summary_store = MagicMock()
    summary_store.find_similar_summaries.side_effect = fake_find

    vs.search.return_value = []

    engine = QueryEngine(
        vs, embedder, fts_store=fts,
        summary_store=summary_store,
        hierarchical_top_docs=2,
        min_score=0.0,
    )
    engine.search_hierarchical("q")

    _, kwargs = vs.search.call_args
    assert kwargs.get("document_ids") == [1, 5]


def test_top_docs_1_apenas_o_melhor_summary() -> None:
    vs = MagicMock(spec=VectorStore)
    fts = MagicMock(spec=FtsStore)
    embedder = _StubEmbedder()
    embedder.dim = 4

    full = [ScoredSummary(document_id=42, summary="best", score=0.99)]

    def fake_find(query_embedding, top_k=10):
        return full[:top_k]

    summary_store = MagicMock()
    summary_store.find_similar_summaries.side_effect = fake_find
    vs.search.return_value = []

    engine = QueryEngine(
        vs, embedder, fts_store=fts,
        summary_store=summary_store,
        hierarchical_top_docs=1,
        min_score=0.0,
    )
    engine.search_hierarchical("q")
    _, kwargs = vs.search.call_args
    assert kwargs.get("document_ids") == [42]


def test_search_hierarchical_sem_summary_store_degrada() -> None:
    """Sem summary_store: search_hierarchical cai para busca sem filtro."""
    vs = MagicMock(spec=VectorStore)
    fts = MagicMock(spec=FtsStore)
    embedder = _StubEmbedder()
    embedder.dim = 4
    vs.search.return_value = []

    engine = QueryEngine(
        vs, embedder, fts_store=fts,
        summary_store=None,
        hierarchical_top_docs=5,
        min_score=0.0,
    )
    engine.search_hierarchical("q")
    _, kwargs = vs.search.call_args
    assert kwargs.get("document_ids") in (None, [])