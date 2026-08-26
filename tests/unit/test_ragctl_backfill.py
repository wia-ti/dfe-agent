"""Testes para ``src.ragctl.cmd_backfill_summaries`` (Sprint 3, Iter 1).

Cobre:
    - Lista os documentos que nao tem entry em ``doc_summaries``.
    - Reseta status para ``nao_ingerido`` apenas para esses docs.
    - Em base sem docs faltantes: no-op.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import sqlite_vec

from src.db.sqlite_storage import DocumentRecord, SqliteStorage
from src.ragctl import cmd_backfill_summaries


def _bootstrap_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "f.db"
    SqliteStorage(db_path).init_schema()
    return db_path


def test_backfill_em_base_vazia_nao_faz_nada(tmp_path: Path) -> None:
    db_path = _bootstrap_db(tmp_path)
    args = type("Args", (), {"db_path": db_path})()
    rc = cmd_backfill_summaries(args)
    assert rc == 0


def test_backfill_reseta_status_apenas_docs_sem_summary(tmp_path: Path) -> None:
    db_path = _bootstrap_db(tmp_path)
    storage = SqliteStorage(db_path)

    # Doc 1: com summary (status=ingerido)
    rec1_id = storage.upsert_document(
        DocumentRecord(
            url="https://nfe.fazenda.gov.br/with",
            source_domain="nfe.fazenda.gov.br",
            doc_type="nota_tecnica",
            title="Com Summary",
            file_path=tmp_path / "with.pdf",
            status="ingerido",
        )
    )
    # Doc 2: sem summary
    rec2_id = storage.upsert_document(
        DocumentRecord(
            url="https://nfe.fazenda.gov.br/without",
            source_domain="nfe.fazenda.gov.br",
            doc_type="nota_tecnica",
            title="Sem Summary",
            file_path=tmp_path / "without.pdf",
            status="ingerido",
        )
    )
    # Doc 3: sem summary + falhou
    storage.upsert_document(
        DocumentRecord(
            url="https://nfe.fazenda.gov.br/failed",
            source_domain="nfe.fazenda.gov.br",
            doc_type="nota_tecnica",
            title="Falhou",
            file_path=tmp_path / "failed.pdf",
            status="falhou",
        )
    )

    # Insere summary apenas para rec1.
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO doc_summaries(document_id, summary, embedding, created_at) "
            "VALUES (?, ?, ?, ?)",
            (rec1_id, "sumario", b"\x00" * 4, "2026-01-01T00:00:00"),
        )
        conn.commit()

    args = type("Args", (), {"db_path": db_path})()
    rc = cmd_backfill_summaries(args)
    assert rc == 0

    # doc1: status preservado (=ingerido)
    rec1 = storage.get_by_url("https://nfe.fazenda.gov.br/with")
    assert rec1 is not None and rec1.status == "ingerido"

    # doc2 e doc3: viraram pendentes
    rec2 = storage.get_by_url("https://nfe.fazenda.gov.br/without")
    assert rec2 is not None and rec2.status == "nao_ingerido"
    rec3 = storage.get_by_url("https://nfe.fazenda.gov.br/failed")
    assert rec3 is not None and rec3.status == "nao_ingerido"


def test_backfill_idempotente(tmp_path: Path) -> None:
    """Rodar duas vezes nao duplica reset (segunda chamada e no-op)."""
    db_path = _bootstrap_db(tmp_path)
    storage = SqliteStorage(db_path)
    storage.upsert_document(
        DocumentRecord(
            url="https://nfe.fazenda.gov.br/d",
            source_domain="nfe.fazenda.gov.br",
            doc_type="nota_tecnica",
            title="D",
            file_path=tmp_path / "d.pdf",
            status="ingerido",
        )
    )

    args = type("Args", (), {"db_path": db_path})()
    cmd_backfill_summaries(args)
    cmd_backfill_summaries(args)

    with sqlite3.connect(db_path) as conn:
        n_pendentes = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE status='nao_ingerido'"
        ).fetchone()[0]
    assert n_pendentes == 1  # 1 doc, 1 reset, nao duplica