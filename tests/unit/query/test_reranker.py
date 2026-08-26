"""Testes para ``src.query.reranker.CrossEncoderReranker`` (Sprint 2, Fase 15).

Cobre:
    - `rerank` ordena por score do cross-encoder desc.
    - 2 chunks, um claramente mais relevante: rerank devolve o relevante em 1o.
    - `predict_fn` invalido (dim errada): levanta RuntimeError documentado.
    - ``top_k`` e respeitado.
    - Lista vazia: devolve ``[]`` sem chamar predict_fn.
"""
from __future__ import annotations

import pytest

from src.db.vector_store import ScoredChunk
from src.query.reranker import CrossEncoderReranker


def _scored(text: str, score: float, doc_id: int = 1) -> ScoredChunk:
    return ScoredChunk(text=text, source_url="u", doc_title="d", score=score, document_id=doc_id)


def test_reranker_ordena_por_score_do_predict_fn() -> None:
    scores_by_text: dict[str, float] = {
        "relevante": 2.5,
        "menos_relevante": 0.1,
        "medio": 1.0,
    }
    reranker = CrossEncoderReranker(
        predict_fn=lambda pairs: [scores_by_text.get(p[1], 0.0) for p in pairs]
    )
    chunks = [
        _scored("menos_relevante", 0.99),
        _scored("relevante", 0.95),
        _scored("medio", 0.90),
    ]
    out = reranker.rerank("q", chunks, top_k=3)
    texts = [c.text for c in out]
    assert texts == ["relevante", "medio", "menos_relevante"]


def test_reranker_respeita_top_k() -> None:
    reranker = CrossEncoderReranker(
        predict_fn=lambda pairs: [float(i) for i, _ in enumerate(pairs)]
    )
    chunks = [_scored(f"c{i}", 0.5, doc_id=i) for i in range(10)]
    out = reranker.rerank("q", chunks, top_k=3)
    assert len(out) == 3


def test_reranker_lista_vazia_devolve_sem_chamar_predict() -> None:
    called: list[int] = []

    def predict(pairs: list[list[str]]) -> list[float]:
        called.append(len(pairs))
        return []

    reranker = CrossEncoderReranker(predict_fn=predict)
    out = reranker.rerank("q", [], top_k=5)
    assert out == []
    assert called == []  # NUNCA chamado


def test_reranker_predict_retorna_dim_errada_levanta_runtime_error() -> None:
    reranker = CrossEncoderReranker(
        predict_fn=lambda pairs: [0.0]  # so 1 score para 3 chunks
    )
    with pytest.raises(RuntimeError, match="cross-encoder"):
        reranker.rerank("q", [_scored("a", 0.5), _scored("b", 0.5), _scored("c", 0.5)], top_k=3)


def test_reranker_predict_levanta_excecao_e_propagada_com_runtime_error() -> None:
    def predict(pairs: list[list[str]]) -> list[float]:
        raise OSError("rede offline")

    reranker = CrossEncoderReranker(predict_fn=predict)
    with pytest.raises(RuntimeError, match="rede offline"):
        reranker.rerank("q", [_scored("a", 0.5)], top_k=1)


def test_reranker_preserva_metadata_dos_chunks() -> None:
    """O rerank NAO perde source_url / doc_title / kind."""
    reranker = CrossEncoderReranker(
        predict_fn=lambda pairs: [float(len(pairs) - i) for i, _ in enumerate(pairs)]
    )
    parent_chunk = ScoredChunk(
        text="PARENT", source_url="u1", doc_title="t1",
        score=0.9, document_id=1, kind="parent",
    )
    detail_chunk = ScoredChunk(
        text="DETAIL", source_url="u1", doc_title="t1",
        score=0.95, document_id=1, kind="detail",
        parent_text="PARENT",
    )
    out = reranker.rerank("q", [detail_chunk, parent_chunk], top_k=2)
    assert out[0].source_url == "u1"
    assert out[0].doc_title == "t1"
    assert out[0].parent_text == "PARENT"
    assert out[0].kind == "detail"
