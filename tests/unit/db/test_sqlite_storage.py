"""Testes unitarios do DAO relacional em src.db.sqlite_storage.

Cobre:
    - init_schema() cria a tabela `documents` e os indices.
    - upsert_document() insere novo registro e atualiza existente (idempotente por url).
    - get_by_url() / get_by_hash() retornam registros equivalentes ou None.
    - list_pending() filtra apenas status='nao_ingerido'.
    - mark_ingested() muda status e preenche ingested_at.
    - mark_failed() muda status sem tocar em ingested_at.

Criterio de conclusao (PLAN.md linhas 58-60):
    - [x] init_schema cria tabela documents
    - [x] upsert_document retorna id>=1; get_by_url retorna registro equivalente; missing -> None
    - [x] mark_ingested(id) + list_pending() nao contem o id; status='ingerido', ingested_at nao-nulo
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from src.db.sqlite_storage import DocumentRecord, SqliteStorage


def test_init_schema_creates_documents_table(tmp_path: Path) -> None:
    db_path = tmp_path / "t.db"
    storage = SqliteStorage(db_path)

    storage.init_schema()

    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='documents'"
        )
        assert cursor.fetchone() == ("documents",)


def test_init_schema_creates_status_index(tmp_path: Path) -> None:
    db_path = tmp_path / "t.db"
    storage = SqliteStorage(db_path)

    storage.init_schema()

    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_documents_status'"
        )
        assert cursor.fetchone() is not None


def test_upsert_document_inserts_new_record_returns_id(tmp_path: Path) -> None:
    storage = SqliteStorage(tmp_path / "t.db")
    storage.init_schema()

    record = DocumentRecord(
        url="https://nfe.fazenda.gov.br/docs/nt.pdf",
        source_domain="nfe.fazenda.gov.br",
        doc_type="nota_tecnica",
        title="Nota Tecnica 2019.001",
    )

    new_id = storage.upsert_document(record)

    assert new_id >= 1
    assert isinstance(new_id, int)


def test_upsert_document_updates_existing_by_url(tmp_path: Path) -> None:
    storage = SqliteStorage(tmp_path / "t.db")
    storage.init_schema()

    first = DocumentRecord(
        url="https://nfe.fazenda.gov.br/docs/nt.pdf",
        source_domain="nfe.fazenda.gov.br",
        doc_type="nota_tecnica",
        title="Titulo Antigo",
    )
    first_id = storage.upsert_document(first)

    second = DocumentRecord(
        url="https://nfe.fazenda.gov.br/docs/nt.pdf",
        source_domain="nfe.fazenda.gov.br",
        doc_type="nota_tecnica",
        title="Titulo Atualizado",
        content_hash="abc123",
    )
    second_id = storage.upsert_document(second)

    assert second_id == first_id

    fetched = storage.get_by_url("https://nfe.fazenda.gov.br/docs/nt.pdf")
    assert fetched is not None
    assert fetched.title == "Titulo Atualizado"
    assert fetched.content_hash == "abc123"


def test_get_by_url_returns_record_when_exists(tmp_path: Path) -> None:
    storage = SqliteStorage(tmp_path / "t.db")
    storage.init_schema()

    record = DocumentRecord(
        url="https://nfe.fazenda.gov.br/docs/nt.pdf",
        source_domain="nfe.fazenda.gov.br",
        doc_type="nota_tecnica",
        title="Nota Tecnica 2019.001",
        content_hash="deadbeef",
    )
    new_id = storage.upsert_document(record)

    fetched = storage.get_by_url("https://nfe.fazenda.gov.br/docs/nt.pdf")

    assert fetched is not None
    assert fetched.id == new_id
    assert fetched.url == record.url
    assert fetched.source_domain == record.source_domain
    assert fetched.doc_type == record.doc_type
    assert fetched.title == record.title
    assert fetched.content_hash == record.content_hash
    assert fetched.status == "nao_ingerido"
    assert isinstance(fetched.fetched_at, datetime)


def test_get_by_url_returns_none_when_missing(tmp_path: Path) -> None:
    storage = SqliteStorage(tmp_path / "t.db")
    storage.init_schema()

    result = storage.get_by_url("https://inexistente.example.com/x")

    assert result is None


def test_get_by_hash_returns_record_when_exists(tmp_path: Path) -> None:
    storage = SqliteStorage(tmp_path / "t.db")
    storage.init_schema()

    record = DocumentRecord(
        url="https://nfe.fazenda.gov.br/docs/nt.pdf",
        source_domain="nfe.fazenda.gov.br",
        doc_type="nota_tecnica",
        title="Nota Tecnica 2019.001",
        content_hash="cafe0123",
    )
    storage.upsert_document(record)

    fetched = storage.get_by_hash("cafe0123")

    assert fetched is not None
    assert fetched.content_hash == "cafe0123"
    assert fetched.url == record.url


def test_get_by_hash_returns_none_when_missing(tmp_path: Path) -> None:
    storage = SqliteStorage(tmp_path / "t.db")
    storage.init_schema()

    result = storage.get_by_hash("hash-que-nao-existe")

    assert result is None


def test_list_pending_returns_only_nao_ingerido(tmp_path: Path) -> None:
    storage = SqliteStorage(tmp_path / "t.db")
    storage.init_schema()

    a = storage.upsert_document(
        DocumentRecord(
            url="https://nfe.fazenda.gov.br/a",
            source_domain="nfe.fazenda.gov.br",
            doc_type="nota_tecnica",
            title="A",
        )
    )
    b = storage.upsert_document(
        DocumentRecord(
            url="https://nfe.fazenda.gov.br/b",
            source_domain="nfe.fazenda.gov.br",
            doc_type="nota_tecnica",
            title="B",
        )
    )
    storage.upsert_document(
        DocumentRecord(
            url="https://nfe.fazenda.gov.br/c",
            source_domain="nfe.fazenda.gov.br",
            doc_type="nota_tecnica",
            title="C",
        )
    )

    storage.mark_ingested(b)

    pending = storage.list_pending()
    pending_ids = {doc.id for doc in pending}

    assert a in pending_ids
    assert b not in pending_ids
    assert len(pending) == 2


def test_mark_ingested_updates_status_and_ingested_at(tmp_path: Path) -> None:
    db_path = tmp_path / "t.db"
    storage = SqliteStorage(db_path)
    storage.init_schema()

    new_id = storage.upsert_document(
        DocumentRecord(
            url="https://nfe.fazenda.gov.br/x",
            source_domain="nfe.fazenda.gov.br",
            doc_type="nota_tecnica",
            title="X",
        )
    )

    storage.mark_ingested(new_id)

    pending_ids = {doc.id for doc in storage.list_pending()}
    assert new_id not in pending_ids

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT status, ingested_at FROM documents WHERE id=?", (new_id,)
        ).fetchone()
        assert row is not None
        status, ingested_at = row
        assert status == "ingerido"
        assert ingested_at is not None


def test_mark_failed_updates_status_without_setting_ingested_at(tmp_path: Path) -> None:
    db_path = tmp_path / "t.db"
    storage = SqliteStorage(db_path)
    storage.init_schema()

    new_id = storage.upsert_document(
        DocumentRecord(
            url="https://nfe.fazenda.gov.br/y",
            source_domain="nfe.fazenda.gov.br",
            doc_type="nota_tecnica",
            title="Y",
        )
    )

    storage.mark_failed(new_id)

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT status, ingested_at FROM documents WHERE id=?", (new_id,)
        ).fetchone()
        assert row is not None
        status, ingested_at = row
        assert status == "falhou"
        assert ingested_at is None


def test_upsert_and_get_round_trip_with_file_path(tmp_path: Path) -> None:
    """Cobre _path_to_str (branch nao-None) e _str_to_path desserializando um Path."""
    storage = SqliteStorage(tmp_path / "t.db")
    storage.init_schema()

    target_path = Path("C:/data/nfe/nt-2019-001.pdf")
    storage.upsert_document(
        DocumentRecord(
            url="https://nfe.fazenda.gov.br/docs/nt.pdf",
            source_domain="nfe.fazenda.gov.br",
            doc_type="nota_tecnica",
            title="NT 2019.001",
            file_path=target_path,
        )
    )

    fetched = storage.get_by_url("https://nfe.fazenda.gov.br/docs/nt.pdf")

    assert fetched is not None
    assert fetched.file_path == target_path
