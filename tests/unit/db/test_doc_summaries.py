"""Testes para Sprint 2, Fase 12.1: ``DocSummaryStore`` + persistencia via RagIndexer.

Cobre:
    - ``init_schema`` cria a tabela ``doc_summaries`` com PK em ``document_id``.
    - ``upsert_summary`` persiste (id, summary, embedding, created_at).
    - ``upsert_summary`` idempotente: regravar substitui (PK = document_id).
    - ``upsert_summary`` rejeita summary vazio e embedding dim errada.
    - ``has_summary`` retorna True apos upsert, False antes.
    - ``list_summaries`` retorna todos.
    - ``find_similar_summaries`` ordena por cosseno decrescente.
    - RagIndexer: apos ``ingest_one``, ``has_summary`` e True e
      o summary contem trecho real do texto.
    - Re-ingerir com mesmo doc: nao duplica row em doc_summaries.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from src.db.sqlite_storage import DocumentRecord, SqliteStorage
from src.db.vector_store import VectorStore
from src.indexer.rag_indexer import RagIndexer


# --- helpers --------------------------------------------------------------


def _bootstrap_full(tmp_path: Path) -> Path:
    """Inicializa schema relacional + vetorial e devolve ``db_path``."""
    db_path = tmp_path / "rag.db"
    SqliteStorage(db_path).init_schema()
    VectorStore(db_path, dim=4).init_schema()
    return db_path


def _embedder_stub(dim: int = 4) -> MagicMock:
    """Mock de EmbeddingProvider que devolve vetor constante por chunk."""
    embedder = MagicMock()
    embedder.dim = dim
    embedder.embed.side_effect = lambda texts: [[0.1] * dim for _ in texts]
    return embedder


# --- DocSummaryStore direto ----------------------------------------------


def test_doc_summaries_existe_apos_init_schema(tmp_path: Path) -> None:
    from src.db.doc_summaries import DocSummaryStore

    db_path = _bootstrap_full(tmp_path)
    DocSummaryStore(db_path, dim=4).init_schema()

    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "doc_summaries" in tables


def test_upsert_summary_persiste_e_list_retorna(tmp_path: Path) -> None:
    from src.db.doc_summaries import DocSummaryStore

    db_path = _bootstrap_full(tmp_path)
    store = DocSummaryStore(db_path, dim=4)
    store.init_schema()

    embedding = [0.1, 0.2, 0.3, 0.4]
    store.upsert_summary(
        document_id=1,
        summary="Sumario curto da NT.",
        embedding=embedding,
        now=datetime(2026, 1, 1),
    )

    rows = store.list_summaries()
    assert len(rows) == 1
    assert rows[0].document_id == 1
    assert rows[0].summary == "Sumario curto da NT."
    # Embedding passa por struct.pack (float32), perda de precisao normal.
    assert len(rows[0].embedding) == len(embedding)
    for actual, expected in zip(rows[0].embedding, embedding):
        assert abs(actual - expected) < 1e-5


def test_upsert_summary_idempotente(tmp_path: Path) -> None:
    from src.db.doc_summaries import DocSummaryStore

    db_path = _bootstrap_full(tmp_path)
    store = DocSummaryStore(db_path, dim=4)
    store.init_schema()

    emb = [0.5] * 4
    store.upsert_summary(document_id=7, summary="v1", embedding=emb)
    store.upsert_summary(document_id=7, summary="v2", embedding=emb)

    rows = store.list_summaries()
    assert len(rows) == 1
    assert rows[0].summary == "v2"


def test_upsert_summary_rejeita_summary_vazio(tmp_path: Path) -> None:
    from src.db.doc_summaries import DocSummaryStore
    import pytest

    db_path = _bootstrap_full(tmp_path)
    store = DocSummaryStore(db_path, dim=4)
    store.init_schema()

    with pytest.raises(ValueError):
        store.upsert_summary(
            document_id=1, summary="", embedding=[0.1, 0.2, 0.3, 0.4]
        )


def test_upsert_summary_rejeita_embedding_dim_errada(tmp_path: Path) -> None:
    from src.db.doc_summaries import DocSummaryStore
    import pytest

    db_path = _bootstrap_full(tmp_path)
    store = DocSummaryStore(db_path, dim=4)
    store.init_schema()

    with pytest.raises(ValueError):
        store.upsert_summary(
            document_id=1, summary="ok", embedding=[0.1]  # dim=1, esperado 4
        )


def test_has_summary(tmp_path: Path) -> None:
    from src.db.doc_summaries import DocSummaryStore

    db_path = _bootstrap_full(tmp_path)
    store = DocSummaryStore(db_path, dim=4)
    store.init_schema()

    assert not store.has_summary(99)
    store.upsert_summary(document_id=99, summary="ok", embedding=[0.1] * 4)
    assert store.has_summary(99)


def test_find_similar_summaries_ordena_por_cosseno(tmp_path: Path) -> None:
    from src.db.doc_summaries import DocSummaryStore

    db_path = _bootstrap_full(tmp_path)
    store = DocSummaryStore(db_path, dim=4)
    store.init_schema()

    # Embeddings ortogonais para checar ranking previsivel.
    store.upsert_summary(document_id=1, summary="docA", embedding=[1.0, 0.0, 0.0, 0.0])
    store.upsert_summary(document_id=2, summary="docB", embedding=[0.0, 1.0, 0.0, 0.0])
    store.upsert_summary(document_id=3, summary="docC", embedding=[0.9, 0.1, 0.0, 0.0])

    ranking = store.find_similar_summaries([1.0, 0.0, 0.0, 0.0], top_k=10)
    assert [r.document_id for r in ranking] == [1, 3, 2]
    # docC tem cosseno maior que docB (compartilha direcao do query).
    assert ranking[0].score > ranking[2].score


def test_find_similar_summaries_corpus_vazio(tmp_path: Path) -> None:
    from src.db.doc_summaries import DocSummaryStore

    db_path = _bootstrap_full(tmp_path)
    store = DocSummaryStore(db_path, dim=4)
    store.init_schema()

    assert store.find_similar_summaries([0.1, 0.2, 0.3, 0.4]) == []


# --- RagIndexer persistencia ---------------------------------------------


def test_rag_indexer_persiste_summary_no_ingest(tmp_path: Path) -> None:
    from src.db.doc_summaries import DocSummaryStore

    db_path = _bootstrap_full(tmp_path)
    storage = SqliteStorage(db_path)
    vs = VectorStore(db_path, dim=4)

    embedder = _embedder_stub()
    text = (
        "Esta NT altera as regras de cancelamento da NF-e. "
        "A nova regra atinge tambem CT-e e MDF-e. "
        "Empresas tem 90 dias para se adequar. "
        "Detalhes operacionais estao na secao 3."
    )
    parser = lambda p: text

    indexer = RagIndexer(storage, vs, embedder, parser=parser)
    doc_file = tmp_path / "nt.txt"
    doc_file.write_text("")
    rec = DocumentRecord(
        url="https://nfe.fazenda.gov.br/x",
        source_domain="nfe.fazenda.gov.br",
        doc_type="nota_tecnica",
        title="X",
        file_path=doc_file,
    )
    doc_id = storage.upsert_document(rec)

    indexer.ingest_one(doc_id)

    summary_store = DocSummaryStore(db_path, dim=4)
    assert summary_store.has_summary(doc_id)
    summary = summary_store.list_summaries()[0]
    # Summary vem de "primeira + mais longas", entao deve mencionar regras.
    assert "cancelamento" in summary.summary.lower() or "atinge" in summary.summary.lower()


def test_rag_indexer_idempotente_em_doc_summaries(tmp_path: Path) -> None:
    """Re-ingerir mesmo doc NAO duplica doc_summaries (INSERT OR REPLACE)."""
    from src.db.doc_summaries import DocSummaryStore

    db_path = _bootstrap_full(tmp_path)
    storage = SqliteStorage(db_path)
    vs = VectorStore(db_path, dim=4)
    embedder = _embedder_stub()
    text = (
        "Texto com regras da NT para cancelar documentos fiscais eletronicos "
        "abrangendo NF-e, CT-e e MDF-e em situacoes especificas de erro."
    )
    parser = lambda p: text

    indexer = RagIndexer(storage, vs, embedder, parser=parser)
    doc_file = tmp_path / "nt.txt"
    doc_file.write_text("")
    rec = DocumentRecord(
        url="https://nfe.fazenda.gov.br/y",
        source_domain="nfe.fazenda.gov.br",
        doc_type="nota_tecnica",
        title="Y",
        file_path=doc_file,
    )
    doc_id = storage.upsert_document(rec)

    # Re-ingerir (content_hash igual, idempotente) NAO duplica.
    indexer.ingest_one(doc_id)
    indexer.ingest_one(doc_id)

    summary_store = DocSummaryStore(db_path, dim=4)
    summaries = summary_store.list_summaries()
    ids_with_id: list[int] = [s.document_id for s in summaries]
    assert ids_with_id.count(doc_id) == 1
