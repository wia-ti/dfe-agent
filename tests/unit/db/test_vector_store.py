"""Testes unitarios para VectorStore (DAO vetorial com sqlite-vec)."""
from __future__ import annotations

import sqlite3
import struct
from datetime import datetime
from pathlib import Path

import pytest

from src.db.schema_sql import SCHEMA_SQL
from src.db.sqlite_storage import DocumentRecord, SqliteStorage
from src.db.vector_store import ChunkRecord, ScoredChunk, VectorStore


def _init_store(tmp_path: Path, dim: int = 4) -> VectorStore:
    """Inicializa o schema minimo necessario para os testes de search.

    Cria AMBOS os schemas (relacional + vetorial) porque ``VectorStore.search``
    faz LEFT JOIN com ``documents`` para enriquecer cada chunk com
    ``document_id`` e ``published_at``.
    """
    db_path = tmp_path / "v.db"
    SqliteStorage(db_path).init_schema()
    store = VectorStore(db_path, dim=dim)
    store.init_schema()
    return store


def _init_full_storage(tmp_path: Path, dim: int = 4) -> tuple[VectorStore, SqliteStorage]:
    """Inicializa tanto o storage relacional quanto o vetorial no mesmo DB.

    Espelha o que o projeto faz em producao (SqliteStorage + VectorStore
    sobre o mesmo arquivo ``storage/dfe.db``).
    """
    db_path = tmp_path / "v.db"
    storage = SqliteStorage(db_path)
    storage.init_schema()
    store = VectorStore(db_path, dim=dim)
    store.init_schema()
    return store, storage


def _chunk(
    document_id: int,
    chunk_index: int,
    text: str,
    embedding: list[float],
    source_url: str = "https://nfe.fazenda.gov.br/docs/nt.pdf",
    doc_title: str = "Nota Tecnica",
) -> ChunkRecord:
    return ChunkRecord(
        document_id=document_id,
        chunk_index=chunk_index,
        text=text,
        embedding=embedding,
        source_url=source_url,
        doc_title=doc_title,
    )


def _insert_doc(
    storage: SqliteStorage,
    url: str,
    title: str,
    published_at: datetime | None,
) -> int:
    rec = DocumentRecord(
        url=url,
        source_domain="nfe.fazenda.gov.br",
        doc_type="nfe",
        title=title,
        published_at=published_at,
        status="ingerido",
    )
    return storage.upsert_document(rec)


def test_init_schema_creates_vec_chunks_table(tmp_path: Path) -> None:
    store = _init_store(tmp_path, dim=4)

    conn = sqlite3.connect(store._db_path)  # noqa: SLF001 - intencional no teste
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE name='vec_chunks'"
        ).fetchall()
    finally:
        conn.close()

    assert rows == [("vec_chunks",)]


def test_insert_single_chunk_and_search_returns_it(tmp_path: Path) -> None:
    store = _init_store(tmp_path, dim=4)
    store.insert_chunks(
        [_chunk(document_id=1, chunk_index=0, text="hello", embedding=[1, 0, 0, 0])]
    )

    results = store.search([1, 0, 0, 0], top_k=1)

    assert len(results) == 1
    assert isinstance(results[0], ScoredChunk)
    assert results[0].text == "hello"
    assert results[0].score >= 0.99


def test_insert_three_orthogonal_chunks_and_search_finds_closest(
    tmp_path: Path,
) -> None:
    store = _init_store(tmp_path, dim=4)
    chunks = [
        _chunk(document_id=1, chunk_index=0, text="A", embedding=[1, 0, 0, 0]),
        _chunk(document_id=2, chunk_index=0, text="B", embedding=[0, 1, 0, 0]),
        _chunk(document_id=3, chunk_index=0, text="C", embedding=[0, 0, 1, 0]),
    ]
    store.insert_chunks(chunks)

    results = store.search([1, 0, 0, 0], top_k=1)

    assert len(results) == 1
    assert results[0].text == "A"
    assert results[0].score >= 0.99


def test_search_top_k_limits_results(tmp_path: Path) -> None:
    store = _init_store(tmp_path, dim=4)
    chunks = [
        _chunk(document_id=1, chunk_index=0, text="A", embedding=[1, 0, 0, 0]),
        _chunk(document_id=2, chunk_index=0, text="B", embedding=[0, 1, 0, 0]),
        _chunk(document_id=3, chunk_index=0, text="C", embedding=[0, 0, 1, 0]),
    ]
    store.insert_chunks(chunks)

    results = store.search([1, 0, 0, 0], top_k=2)

    assert len(results) <= 2


def test_search_empty_table_returns_empty_list(tmp_path: Path) -> None:
    store = _init_store(tmp_path, dim=4)

    results = store.search([1, 0, 0, 0], top_k=5)

    assert results == []


def test_search_orders_by_score_descending(tmp_path: Path) -> None:
    store = _init_store(tmp_path, dim=4)
    chunks = [
        _chunk(document_id=1, chunk_index=0, text="ortho", embedding=[0, 1, 0, 0]),
        _chunk(document_id=2, chunk_index=0, text="close", embedding=[1, 0.1, 0, 0]),
        _chunk(document_id=3, chunk_index=0, text="exact", embedding=[1, 0, 0, 0]),
    ]
    store.insert_chunks(chunks)

    results = store.search([1, 0, 0, 0], top_k=2)

    assert len(results) == 2
    assert results[0].score >= results[1].score
    assert results[0].text == "exact"
    assert results[1].text == "close"


def test_chunk_record_round_trip_preserves_metadata(tmp_path: Path) -> None:
    store = _init_store(tmp_path, dim=4)
    chunk = _chunk(
        document_id=42,
        chunk_index=7,
        text="conteudo da NT 2019.001",
        embedding=[0.5, 0.5, 0.5, 0.5],
        source_url="https://www.nfe.fazenda.gov.br/portal/nota.aspx",
        doc_title="Nota Tecnica 2019.001",
    )
    store.insert_chunks([chunk])

    results = store.search([0.5, 0.5, 0.5, 0.5], top_k=1)

    assert len(results) == 1
    assert results[0].text == chunk.text
    assert results[0].source_url == chunk.source_url
    assert results[0].doc_title == chunk.doc_title


def test_search_returns_scored_chunk_dataclass(tmp_path: Path) -> None:
    store = _init_store(tmp_path, dim=4)
    store.insert_chunks(
        [_chunk(document_id=1, chunk_index=0, text="x", embedding=[1, 0, 0, 0])]
    )

    results = store.search([1, 0, 0, 0], top_k=1)

    assert results[0].text == "x"
    assert results[0].source_url == "https://nfe.fazenda.gov.br/docs/nt.pdf"
    assert results[0].doc_title == "Nota Tecnica"
    assert isinstance(results[0].score, float)
    assert -1.0 <= results[0].score <= 1.5


def test_init_rejects_non_positive_dim(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="dim deve ser positivo"):
        VectorStore(tmp_path / "v.db", dim=0)
    with pytest.raises(ValueError, match="dim deve ser positivo"):
        VectorStore(tmp_path / "v.db", dim=-3)


def test_insert_empty_list_is_noop(tmp_path: Path) -> None:
    store = _init_store(tmp_path, dim=4)

    store.insert_chunks([])

    assert store.search([1, 0, 0, 0], top_k=5) == []


# --- Enriquecimento com metadados do documento (JOIN com documents) ---


def test_search_enriches_scored_chunk_with_document_id_and_published_at(tmp_path: Path) -> None:
    """Quando o documento existe em ``documents``, o ScoredChunk retornado
    inclui ``document_id`` e ``published_at`` vindos do JOIN."""
    store, storage = _init_full_storage(tmp_path, dim=4)
    pub = datetime(2026, 8, 4)
    doc_id = _insert_doc(
        storage,
        url="https://nfe.fazenda.gov.br/nt.pdf",
        title="NT 2025.002 v.1.51",
        published_at=pub,
    )
    store.insert_chunks(
        [_chunk(document_id=doc_id, chunk_index=0, text="x", embedding=[1, 0, 0, 0])]
    )

    results = store.search([1, 0, 0, 0], top_k=1)

    assert len(results) == 1
    assert results[0].document_id == doc_id
    assert results[0].published_at == pub


def test_search_falls_back_to_fetched_at_when_published_at_is_null(tmp_path: Path) -> None:
    """Se o documento existe mas ``published_at`` e NULL, usa ``fetched_at``
    como fallback (garante que o boost temporal tenha referencia)."""
    store, storage = _init_full_storage(tmp_path, dim=4)
    doc_id = _insert_doc(
        storage,
        url="https://nfe.fazenda.gov.br/nt.pdf",
        title="NT sem data",
        published_at=None,  # nao foi possivel extrair do titulo
    )
    fetched_doc = storage.get_by_url("https://nfe.fazenda.gov.br/nt.pdf")
    assert fetched_doc is not None
    store.insert_chunks(
        [_chunk(document_id=doc_id, chunk_index=0, text="x", embedding=[1, 0, 0, 0])]
    )

    results = store.search([1, 0, 0, 0], top_k=1)

    assert len(results) == 1
    assert results[0].document_id == doc_id
    # published_at e None no banco -> deve cair para fetched_at
    assert results[0].published_at is not None
    assert results[0].published_at == fetched_doc.fetched_at


def test_search_orphan_chunk_keeps_document_id_but_published_at_none(tmp_path: Path) -> None:
    """Chunk orfao (vec_chunks.document_id sem par em documents): o search nao
    quebra; ``document_id`` permanece com o valor original do chunk e
    ``published_at`` fica None (COALESCE null, null = null)."""
    store = _init_store(tmp_path, dim=4)
    store.insert_chunks(
        [_chunk(document_id=999, chunk_index=0, text="x", embedding=[1, 0, 0, 0])]
    )

    results = store.search([1, 0, 0, 0], top_k=1)

    assert len(results) == 1
    assert results[0].document_id == 999  # preservado de vec_chunks
    assert results[0].published_at is None  # orfao -> sem metadado


# --- document_ids filter (Sprint 2 / Fase 12.2) --------------------------


def test_search_filtra_por_document_ids(tmp_path: Path) -> None:
    """Quando ``document_ids`` e informado, a busca fica restrita a esses docs."""
    store = _init_store(tmp_path, dim=4)
    store.insert_chunks(
        [
            _chunk(document_id=1, chunk_index=0, text="doc1 chunk", embedding=[1.0, 0.0, 0.0, 0.0]),
            _chunk(document_id=2, chunk_index=0, text="doc2 chunk", embedding=[0.9, 0.1, 0.0, 0.0]),
            _chunk(document_id=3, chunk_index=0, text="doc3 chunk", embedding=[0.95, 0.05, 0.0, 0.0]),
        ]
    )

    results = store.search([1.0, 0.0, 0.0, 0.0], top_k=5, document_ids=[2])
    assert len(results) == 1
    assert results[0].document_id == 2


def test_search_sem_document_ids_retorna_todos(tmp_path: Path) -> None:
    store = _init_store(tmp_path, dim=4)
    store.insert_chunks(
        [
            _chunk(document_id=1, chunk_index=0, text="a", embedding=[1, 0, 0, 0]),
            _chunk(document_id=2, chunk_index=0, text="b", embedding=[0, 1, 0, 0]),
        ]
    )

    results = store.search([1, 0, 0, 0], top_k=5)
    assert {r.document_id for r in results} == {1, 2}


def test_search_com_document_ids_vazio_retorna_vazio(tmp_path: Path) -> None:
    """Lista vazia = sem restricao = retorna todos (consistente com None)."""
    store = _init_store(tmp_path, dim=4)
    store.insert_chunks(
        [_chunk(document_id=1, chunk_index=0, text="a", embedding=[1, 0, 0, 0])]
    )

    results = store.search([1, 0, 0, 0], top_k=5, document_ids=[])
    assert len(results) == 1


def test_search_com_document_ids_desconhecidos_retorna_vazio(tmp_path: Path) -> None:
    store = _init_store(tmp_path, dim=4)
    store.insert_chunks(
        [_chunk(document_id=1, chunk_index=0, text="a", embedding=[1, 0, 0, 0])]
    )

    results = store.search([1, 0, 0, 0], top_k=5, document_ids=[999])
    assert results == []
