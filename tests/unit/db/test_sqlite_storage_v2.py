"""Testes unitarios para Sprint 2, Fase 9.1: schema v2 + metadados estruturados.

Cobre:
    - Schema v2 inclui colunas novas (``nt_number``, ``version``,
      ``replaces_doc_id``, ``language``) e indices
      (``idx_documents_nt_number``, ``idx_documents_doc_type``,
      ``idx_documents_published_at``).
    - ``init_schema()`` em DB fresh aplica baseline + migrations pendentes.
    - Migration 0002 e idempotente (segundo apply_pending em DB ja em v2
      e no-op).
    - DB v1 legado (sem colunas v2) e migrado transparentemente sem
      perda de dados.
    - ``upsert_document`` round-trip preserva os campos v2.
    - ``get_by_nt_number`` retorna o doc mais recente com o NT indicado.
    - ``list_by_doc_type`` filtra por tipo.
    - ``list_replaced_by`` retorna sucessores de um doc.
    - ``DocumentRecord`` ja nasce com campos v2=None (compat com construtor v1).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from src.db.sqlite_storage import DocumentRecord, SqliteStorage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_doc(
    storage: SqliteStorage,
    url: str,
    doc_type: str = "nota_tecnica",
    title: str = "doc",
    nt_number: str | None = None,
    published_at: object | None = None,
    replaces_doc_id: int | None = None,
    version: str | None = None,
) -> int:
    """Insere um DocumentRecord programaticamente para testes de filtro."""
    record = DocumentRecord(
        url=url,
        source_domain="nfe.fazenda.gov.br",
        doc_type=doc_type,
        title=title,
        nt_number=nt_number,
        published_at=published_at,
        replaces_doc_id=replaces_doc_id,
        version=version,
    )
    return storage.upsert_document(record)


def _v1_database(db_path: Path) -> None:
    """Cria um banco pre-Fase-9 (apenas colunas v1, sem v2).

    Simula um DB criado antes da Sprint 2: usado para validar o caminho
    de upgrade via migration 0002.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                source_domain TEXT NOT NULL,
                doc_type TEXT NOT NULL,
                title TEXT NOT NULL,
                file_path TEXT,
                content_hash TEXT,
                published_at TEXT,
                fetched_at TEXT NOT NULL,
                ingested_at TEXT,
                status TEXT NOT NULL
            );
            CREATE INDEX idx_documents_status ON documents(status);
            """
        )
        conn.execute(
            "INSERT INTO documents(url, source_domain, doc_type, title, "
            "fetched_at, status) VALUES (?, ?, ?, ?, ?, ?)",
            (
                "https://nfe.fazenda.gov.br/legacy",
                "nfe.fazenda.gov.br",
                "nota_tecnica",
                "Legacy NT",
                "2024-01-01T00:00:00",
                "ingerido",
            ),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema v2 columns
# ---------------------------------------------------------------------------


def test_init_schema_creates_v2_columns(tmp_path: Path) -> None:
    storage = SqliteStorage(tmp_path / "t.db")
    storage.init_schema()

    with sqlite3.connect(tmp_path / "t.db") as conn:
        cols: set[str] = {
            row[1] for row in conn.execute("PRAGMA table_info(documents)").fetchall()
        }
    assert "nt_number" in cols
    assert "version" in cols
    assert "replaces_doc_id" in cols
    assert "language" in cols


def test_init_schema_creates_v2_indexes(tmp_path: Path) -> None:
    storage = SqliteStorage(tmp_path / "t.db")
    storage.init_schema()

    with sqlite3.connect(tmp_path / "t.db") as conn:
        idx: set[str] = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
    assert "idx_documents_nt_number" in idx
    assert "idx_documents_doc_type" in idx
    assert "idx_documents_published_at" in idx


def test_init_schema_sets_user_version_to_current(tmp_path: Path) -> None:
    storage = SqliteStorage(tmp_path / "t.db")
    storage.init_schema()
    # CURRENT_VERSION em src.db.migrations (Sprint 2+: inclui migration 0003
    # para ``chunk_metadata``). Verifica a constante indiretamente para
    # nao acoplar o teste ao numero magico.
    from src.db.migrations import CURRENT_VERSION
    assert storage.current_schema_version() == CURRENT_VERSION


# ---------------------------------------------------------------------------
# DocumentRecord defaults
# ---------------------------------------------------------------------------


def test_document_record_v2_fields_default_to_none() -> None:
    rec = DocumentRecord(
        url="u",
        source_domain="d",
        doc_type="t",
        title="t",
    )
    assert rec.nt_number is None
    assert rec.version is None
    assert rec.replaces_doc_id is None
    assert rec.language is None


# ---------------------------------------------------------------------------
# Round-trip dos campos v2
# ---------------------------------------------------------------------------


def test_upsert_and_get_round_trip_preserves_v2_fields(tmp_path: Path) -> None:
    storage = SqliteStorage(tmp_path / "t.db")
    storage.init_schema()

    rec = DocumentRecord(
        url="https://nfe.fazenda.gov.br/nt-2019-001",
        source_domain="nfe.fazenda.gov.br",
        doc_type="nota_tecnica",
        title="NT 2019.001",
        nt_number="2019.001",
        version="3.2",
        language="pt-BR",
    )
    storage.upsert_document(rec)

    fetched = storage.get_by_url("https://nfe.fazenda.gov.br/nt-2019-001")
    assert fetched is not None
    assert fetched.nt_number == "2019.001"
    assert fetched.version == "3.2"
    assert fetched.language == "pt-BR"
    assert fetched.replaces_doc_id is None


def test_upsert_updates_v2_fields_on_conflict(tmp_path: Path) -> None:
    """ON CONFLICT(url) DO UPDATE sobrescreve tambem os campos v2."""
    storage = SqliteStorage(tmp_path / "t.db")
    storage.init_schema()

    storage.upsert_document(
        DocumentRecord(
            url="https://nfe.fazenda.gov.br/x",
            source_domain="nfe.fazenda.gov.br",
            doc_type="nota_tecnica",
            title="X",
            nt_number="2018.000",
        )
    )
    storage.upsert_document(
        DocumentRecord(
            url="https://nfe.fazenda.gov.br/x",
            source_domain="nfe.fazenda.gov.br",
            doc_type="nota_tecnica",
            title="X v2",
            nt_number="2019.001",
            version="2.0",
        )
    )

    fetched = storage.get_by_url("https://nfe.fazenda.gov.br/x")
    assert fetched is not None
    assert fetched.title == "X v2"
    assert fetched.nt_number == "2019.001"
    assert fetched.version == "2.0"


# ---------------------------------------------------------------------------
# get_by_nt_number
# ---------------------------------------------------------------------------


def test_get_by_nt_number_returns_record_when_exists(tmp_path: Path) -> None:
    storage = SqliteStorage(tmp_path / "t.db")
    storage.init_schema()
    _seed_doc(
        storage,
        "https://nfe.fazenda.gov.br/a",
        nt_number="2019.001",
    )

    found = storage.get_by_nt_number("2019.001")
    assert found is not None
    assert found.nt_number == "2019.001"


def test_get_by_nt_number_returns_none_when_missing(tmp_path: Path) -> None:
    storage = SqliteStorage(tmp_path / "t.db")
    storage.init_schema()
    assert storage.get_by_nt_number("9999.999") is None


def test_get_by_nt_number_prefers_latest_revision(tmp_path: Path) -> None:
    """Multiplas revisoes do mesmo NT: retorna a de maior id (mais recente)."""
    storage = SqliteStorage(tmp_path / "t.db")
    storage.init_schema()
    id_v1 = _seed_doc(
        storage,
        "https://nfe.fazenda.gov.br/v1",
        nt_number="2019.001",
        title="v1",
    )
    id_v3 = _seed_doc(
        storage,
        "https://nfe.fazenda.gov.br/v3",
        nt_number="2019.001",
        title="v3",
    )

    found = storage.get_by_nt_number("2019.001")
    assert found is not None
    assert found.id == id_v3
    assert id_v3 > id_v1


# ---------------------------------------------------------------------------
# list_by_doc_type
# ---------------------------------------------------------------------------


def test_list_by_doc_type_filters_by_type(tmp_path: Path) -> None:
    storage = SqliteStorage(tmp_path / "t.db")
    storage.init_schema()
    _seed_doc(storage, "https://nfe.fazenda.gov.br/n1", doc_type="nota_tecnica")
    _seed_doc(storage, "https://nfe.fazenda.gov.br/c1", doc_type="convenio")
    _seed_doc(storage, "https://nfe.fazenda.gov.br/n2", doc_type="nota_tecnica")

    only_nts = storage.list_by_doc_type("nota_tecnica")
    assert {doc.url for doc in only_nts} == {
        "https://nfe.fazenda.gov.br/n1",
        "https://nfe.fazenda.gov.br/n2",
    }
    assert storage.list_by_doc_type("convenio") != []
    assert storage.list_by_doc_type("inexistente") == []


# ---------------------------------------------------------------------------
# list_replaced_by
# ---------------------------------------------------------------------------


def test_list_replaced_by_returns_successors(tmp_path: Path) -> None:
    storage = SqliteStorage(tmp_path / "t.db")
    storage.init_schema()
    base_id = _seed_doc(
        storage,
        "https://nfe.fazenda.gov.br/old",
        title="Old",
    )
    _seed_doc(
        storage,
        "https://nfe.fazenda.gov.br/new1",
        title="New 1",
        replaces_doc_id=base_id,
    )
    _seed_doc(
        storage,
        "https://nfe.fazenda.gov.br/new2",
        title="New 2",
        replaces_doc_id=base_id,
    )
    _seed_doc(
        storage,
        "https://nfe.fazenda.gov.br/unrelated",
        title="Unrelated",
    )

    successors = storage.list_replaced_by(base_id)
    urls = {doc.url for doc in successors}
    assert urls == {
        "https://nfe.fazenda.gov.br/new1",
        "https://nfe.fazenda.gov.br/new2",
    }
    assert storage.list_replaced_by(99999) == []


# ---------------------------------------------------------------------------
# Migracao: v1 legada -> v2
# ---------------------------------------------------------------------------


def test_init_schema_upgrades_legacy_v1_database(tmp_path: Path) -> None:
    """DB pre-Fase-9 recebe as colunas v2 via migration sem perder dados."""
    db_path = tmp_path / "legacy.db"
    _v1_database(db_path)

    storage = SqliteStorage(db_path)
    storage.init_schema()

    # Colunas v2 presentes.
    with sqlite3.connect(db_path) as conn:
        cols: set[str] = {
            row[1]
            for row in conn.execute("PRAGMA table_info(documents)").fetchall()
        }
    assert "nt_number" in cols
    assert "version" in cols
    assert "replaces_doc_id" in cols
    assert "language" in cols

    # Dados legados preservados.
    legacy = storage.get_by_url("https://nfe.fazenda.gov.br/legacy")
    assert legacy is not None
    assert legacy.title == "Legacy NT"
    assert legacy.status == "ingerido"
    assert legacy.nt_number is None

    # Schema versionado em CURRENT_VERSION (v3+ com chunk_metadata).
    from src.db.migrations import CURRENT_VERSION
    assert storage.current_schema_version() == CURRENT_VERSION


def test_init_schema_is_idempotent_on_fresh_database(tmp_path: Path) -> None:
    """Rodar init_schema() duas vezes nao duplica indices nem colunas."""
    db_path = tmp_path / "t.db"
    storage = SqliteStorage(db_path)
    storage.init_schema()
    storage.init_schema()  # segunda passagem

    with sqlite3.connect(db_path) as conn:
        n_idx: int = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='index' "
            "AND name='idx_documents_nt_number'"
        ).fetchone()[0]
    assert n_idx == 1
    from src.db.migrations import CURRENT_VERSION
    assert storage.current_schema_version() == CURRENT_VERSION


def test_migrate_after_init_is_noop(tmp_path: Path) -> None:
    from src.db.migrations import CURRENT_VERSION
    storage = SqliteStorage(tmp_path / "t.db")
    storage.init_schema()
    new_version = storage.migrate()
    assert new_version == CURRENT_VERSION


def test_desserializacao_aceita_banco_sem_colunas_v2(tmp_path: Path) -> None:
    """Cobertura defensiva: _row_to_record tolera tabela sem colunas v2.

    Este cenario e altamente improvavel em producao (init_schema sempre
    roda antes de qualquer leitura), mas protege o codigo contra
    corrupcao acidental do schema.
    """
    db_path = tmp_path / "no_v2.db"
    _v1_database(db_path)  # sem colunas v2

    storage = SqliteStorage(db_path)
    legacy = storage.get_by_url("https://nfe.fazenda.gov.br/legacy")
    assert legacy is not None
    assert legacy.nt_number is None
    assert legacy.version is None
    assert legacy.replaces_doc_id is None
    assert legacy.language is None
