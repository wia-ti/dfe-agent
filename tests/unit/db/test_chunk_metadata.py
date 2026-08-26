"""Testes para Sprint 2, Fase 10.1: sidecar ``chunk_metadata`` (migration 0003).

Cobre:
    - ``chunk_metadata`` e criada com a PK composta ``(document_id,
      chunk_index)`` e com colunas estruturais.
    - Idempotencia: rodar init_schema/migrate duas vezes nao duplica.
    - Inserir chunks via ``VectorStore.insert_chunks`` com
      ``section_path``/``section_level`` resulta em linhas correspondentes
      em ``chunk_metadata``.
    - ``search`` faz LEFT JOIN com ``chunk_metadata`` e preenche
      ``section_path``/``section_level`` no ``ScoredChunk``.
    - Chunks pre-existentes (sem entrada em ``chunk_metadata``) retornam
      ``section_path=""`` e ``section_level=0`` (compat v2).
    - ``ScoredChunk`` e ``ChunkRecord`` aceitam os novos campos via default.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import sqlite_vec

from src.db.sqlite_storage import SqliteStorage
from src.db.vector_store import ChunkRecord, ScoredChunk, VectorStore


def _setup_db(tmp_path: Path) -> Path:
    """Inicializa schema v2 + vetorial em tmp_path; retorna ``db_path``."""
    db_path = tmp_path / "rag.db"
    storage = SqliteStorage(db_path)
    storage.init_schema()
    vs = VectorStore(db_path, dim=4)
    vs.init_schema()
    return db_path


# --- migration 0003 --------------------------------------------------------


def test_chunk_metadata_existe_apos_init_schema(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)

    with sqlite3.connect(db_path) as conn:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='chunk_metadata'"
        ).fetchall()
    assert ("chunk_metadata",) in rows


def test_chunk_metadata_possui_colunas_esperadas(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    with sqlite3.connect(db_path) as conn:
        cols: dict[str, str] = {
            row[1]: row[2]
            for row in conn.execute("PRAGMA table_info(chunk_metadata)").fetchall()
        }
    assert "document_id" in cols
    assert "chunk_index" in cols
    assert "section_path" in cols
    assert "section_level" in cols


def test_migrate_0003_e_idempotente(tmp_path: Path) -> None:
    db_path = tmp_path / "rag.db"
    s = SqliteStorage(db_path)
    s.init_schema()
    s.init_schema()  # segunda passagem
    from src.db.migrations import CURRENT_VERSION
    storage_version = s.current_schema_version()
    assert storage_version == CURRENT_VERSION


# --- ChunkRecord / ScoredChunk defaults -----------------------------------


def test_chunk_record_aceita_section_path_e_level() -> None:
    rec = ChunkRecord(
        document_id=1,
        chunk_index=0,
        text="t",
        embedding=[0.0, 0.0, 0.0, 0.0],
        source_url="https://nfe.fazenda.gov.br/x",
        doc_title="t",
        section_path="1.1 OBJETIVO",
        section_level=2,
    )
    assert rec.section_path == "1.1 OBJETIVO"
    assert rec.section_level == 2


def test_chunk_record_sem_section_usa_defaults_vazios() -> None:
    rec = ChunkRecord(
        document_id=1,
        chunk_index=0,
        text="t",
        embedding=[0.0, 0.0, 0.0, 0.0],
        source_url="https://nfe.fazenda.gov.br/x",
        doc_title="t",
    )
    assert rec.section_path == ""
    assert rec.section_level == 0


# --- insert_chunks propaga para chunk_metadata ----------------------------


def test_insert_chunks_persiste_section_path_no_sidecar(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    vs = VectorStore(db_path, dim=4)

    vs.insert_chunks(
        [
            ChunkRecord(
                document_id=1,
                chunk_index=0,
                text="§ 1 OBJETIVO: conteudo da secao 1",
                embedding=[1.0, 0.0, 0.0, 0.0],
                source_url="https://nfe.fazenda.gov.br/x",
                doc_title="X",
                section_path="1 OBJETIVO",
                section_level=1,
            ),
            ChunkRecord(
                document_id=1,
                chunk_index=1,
                text="§ 2 FUNDAMENTACAO: base legal XYZ",
                embedding=[0.0, 1.0, 0.0, 0.0],
                source_url="https://nfe.fazenda.gov.br/x",
                doc_title="X",
                section_path="2 FUNDAMENTACAO",
                section_level=1,
            ),
        ]
    )

    with sqlite3.connect(db_path) as conn:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        rows = conn.execute(
            "SELECT document_id, chunk_index, section_path, section_level "
            "FROM chunk_metadata ORDER BY chunk_index"
        ).fetchall()
    assert len(rows) == 2
    assert rows[0] == (1, 0, "1 OBJETIVO", 1)
    assert rows[1] == (1, 1, "2 FUNDAMENTACAO", 1)


def test_insert_chunks_persiste_section_vazio_para_flat(
    tmp_path: Path,
) -> None:
    """Chunks sem section info ainda sao registrados no sidecar (com path vazio)."""
    db_path = _setup_db(tmp_path)
    vs = VectorStore(db_path, dim=4)

    vs.insert_chunks(
        [
            ChunkRecord(
                document_id=2,
                chunk_index=0,
                text="chunk plano sem section",
                embedding=[0.5, 0.5, 0.0, 0.0],
                source_url="https://nfe.fazenda.gov.br/y",
                doc_title="Y",
            ),
        ]
    )

    with sqlite3.connect(db_path) as conn:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        row = conn.execute(
            "SELECT section_path, section_level FROM chunk_metadata "
            "WHERE document_id=2"
        ).fetchone()
    assert row == ("", 0)


# --- search devolve section_path via LEFT JOIN ----------------------------


def test_search_retorna_section_path_quando_existe(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    vs = VectorStore(db_path, dim=4)

    vs.insert_chunks(
        [
            ChunkRecord(
                document_id=1,
                chunk_index=0,
                text="§ 1.1 SUB: conteudo do nivel 2",
                embedding=[1.0, 0.0, 0.0, 0.0],
                source_url="https://nfe.fazenda.gov.br/x",
                doc_title="X",
                section_path="1.1 SUB",
                section_level=2,
            ),
        ]
    )

    hits = vs.search([1.0, 0.0, 0.0, 0.0], top_k=5)
    assert len(hits) == 1
    assert hits[0].section_path == "1.1 SUB"
    assert hits[0].section_level == 2


def test_search_com_chunk_legado_sem_section_path_retorna_vazio(
    tmp_path: Path,
) -> None:
    """Chunks pre-Fase-10 (sem entrada em chunk_metadata) recebem "" no join."""
    db_path = _setup_db(tmp_path)
    vs = VectorStore(db_path, dim=4)

    # Insere via vec_chunks direto, simulando um chunk legado.
    with sqlite3.connect(db_path) as conn:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.execute(
            "INSERT INTO vec_chunks(embedding, document_id, chunk_index, "
            "text, source_url, doc_title) VALUES (?, ?, ?, ?, ?, ?)",
            (
                b"\x00\x00\x80\x3f" + b"\x00\x00\x00\x00" * 3,
                99,
                0,
                "legado",
                "https://nfe.fazenda.gov.br/legado",
                "Legado",
            ),
        )
        conn.commit()

    hits = vs.search([1.0, 0.0, 0.0, 0.0], top_k=5)
    legacy_hits = [h for h in hits if h.document_id == 99]
    assert len(legacy_hits) == 1
    assert legacy_hits[0].section_path == ""
    assert legacy_hits[0].section_level == 0


# --- ScoredChunk defaults -------------------------------------------------


def test_scored_chunk_aceita_section_path_e_level() -> None:
    sc = ScoredChunk(
        text="t",
        source_url="u",
        doc_title="d",
        score=0.9,
        document_id=1,
        section_path="1.1 SUB",
        section_level=2,
    )
    assert sc.section_path == "1.1 SUB"
    assert sc.section_level == 2


def test_scored_chunk_section_default_vazio() -> None:
    sc = ScoredChunk(text="t", source_url="u", doc_title="d", score=0.9)
    assert sc.section_path == ""
    assert sc.section_level == 0
