"""Testes para Sprint 2, Fase 14: parent-document retrieval + kind/parent_chunk_id.

Cobre:
    - Migration 0006 adiciona colunas ``kind`` e ``parent_chunk_id``.
    - ``ChunkRecord`` aceita ``kind`` e ``parent_chunk_id``.
    - ``ScoredChunk`` aceita ``kind`` e ``parent_text`` (default = "detail" / None).
    - VectorStore insere ``kind``/``parent_chunk_id`` no sidecar.
    - Search faz 2-stage JOIN: detail -> parent, retornando ``parent_text``.
    - Hit em filho: ``parent_text`` preenchido com texto-pai.
    - Hit em dois filhos do mesmo pai: parent so aparece uma vez (dedup testado
      em test_query_engine, fora deste escopo).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import sqlite_vec

from src.db.sqlite_storage import SqliteStorage
from src.db.vector_store import ChunkRecord, ScoredChunk, VectorStore


def _bootstrap(tmp_path: Path) -> Path:
    db_path = tmp_path / "rag.db"
    SqliteStorage(db_path).init_schema()
    VectorStore(db_path, dim=4).init_schema()
    return db_path


# --- Migration 0006 ------------------------------------------------------


def test_chunk_metadata_tem_colunas_v2_e_v14(tmp_path: Path) -> None:
    """Apos init_schema, a tabela tem section_path (v3) + kind/parent_chunk_id (v6)."""
    db_path = _bootstrap(tmp_path)
    with sqlite3.connect(db_path) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(chunk_metadata)")}
    assert "section_path" in cols
    assert "section_level" in cols
    assert "kind" in cols
    assert "parent_chunk_id" in cols


def test_kind_tem_indice(tmp_path: Path) -> None:
    db_path = _bootstrap(tmp_path)
    with sqlite3.connect(db_path) as conn:
        idx = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
    assert "idx_chunk_metadata_kind" in idx


# --- Defaults / construction ----------------------------------------------


def test_chunk_record_aceita_kind_e_parent_chunk_id() -> None:
    rec = ChunkRecord(
        document_id=1,
        chunk_index=0,
        text="t",
        embedding=[0.0] * 4,
        source_url="u",
        doc_title="d",
        kind="parent",
    )
    assert rec.kind == "parent"
    assert rec.parent_chunk_id is None


def test_chunk_record_defaults_kind_detail_sem_parent() -> None:
    rec = ChunkRecord(
        document_id=1,
        chunk_index=0,
        text="t",
        embedding=[0.0] * 4,
        source_url="u",
        doc_title="d",
    )
    assert rec.kind == "detail"
    assert rec.parent_chunk_id is None


def test_scored_chunk_aceita_kind_e_parent_text() -> None:
    sc = ScoredChunk(text="t", source_url="u", doc_title="d", score=0.9)
    assert sc.kind == "detail"
    assert sc.parent_text is None


def test_scored_chunk_with_parent_text() -> None:
    sc = ScoredChunk(
        text="t", source_url="u", doc_title="d", score=0.9,
        kind="detail", parent_text="paragraph completo aqui",
    )
    assert sc.parent_text == "paragraph completo aqui"


# --- Insert + retrieve ----------------------------------------------------


def test_insert_chunk_persiste_kind_no_sidecar(tmp_path: Path) -> None:
    db_path = _bootstrap(tmp_path)
    vs = VectorStore(db_path, dim=4)
    vs.insert_chunks(
        [
            ChunkRecord(
                document_id=1, chunk_index=0, text="parent",
                embedding=[1.0, 0.0, 0.0, 0.0],
                source_url="u", doc_title="T", kind="parent",
            ),
        ]
    )
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT kind, parent_chunk_id FROM chunk_metadata WHERE chunk_index = 0"
        ).fetchone()
    assert row == ("parent", None)


def test_search_retorna_parent_text_para_detail(tmp_path: Path) -> None:
    """Detail tem parent_chunk_id; search faz JOIN e preenche parent_text."""
    db_path = _bootstrap(tmp_path)
    vs = VectorStore(db_path, dim=4)

    # Parent: texto longo
    parent_text = (
        "Este e o paragrafo pai completo sobre o cancelamento de NF-e em "
        "situacoes onde ha erro de preenchimento do destinatario. Detalhes "
        "abaixo."
    )
    vs.insert_chunks(
        [
            ChunkRecord(
                document_id=1, chunk_index=0, text=parent_text,
                embedding=[1.0, 0.0, 0.0, 0.0],
                source_url="u", doc_title="T", kind="parent",
            ),
        ]
    )
    # Detail: aponta pro parent
    detail_text = "Detalhes do cancelamento abaixo."
    vs.insert_chunks(
        [
            ChunkRecord(
                document_id=1, chunk_index=1, text=detail_text,
                embedding=[0.9, 0.1, 0.0, 0.0],
                source_url="u", doc_title="T",
                kind="detail", parent_chunk_id=0,
            ),
        ]
    )

    hits = vs.search([1.0, 0.0, 0.0, 0.0], top_k=5)
    detail_hits = [h for h in hits if h.text == detail_text]
    assert len(detail_hits) == 1
    assert detail_hits[0].kind == "detail"
    assert detail_hits[0].parent_text == parent_text


def test_search_sem_parent_text_para_orphan_detail(tmp_path: Path) -> None:
    """Detail sem ``parent_chunk_id`` (chunks pre-Fase-14) retornam ``parent_text=None``."""
    db_path = _bootstrap(tmp_path)
    vs = VectorStore(db_path, dim=4)
    vs.insert_chunks(
        [
            ChunkRecord(
                document_id=1, chunk_index=0, text="legacy",
                embedding=[1.0, 0.0, 0.0, 0.0],
                source_url="u", doc_title="T",
                # sem kind / parent_chunk_id -> defaults
            ),
        ]
    )
    hits = vs.search([1.0, 0.0, 0.0, 0.0], top_k=5)
    assert hits[0].kind == "detail"
    assert hits[0].parent_text is None


def test_search_hit_em_pai_retorna_sem_parent_text(tmp_path: Path) -> None:
    """Quando o proprio parent esta no top-K, nao precisamos devolver outro parent."""
    db_path = _bootstrap(tmp_path)
    vs = VectorStore(db_path, dim=4)
    vs.insert_chunks(
        [
            ChunkRecord(
                document_id=1, chunk_index=0, text="PARENT",
                embedding=[1.0, 0.0, 0.0, 0.0],
                source_url="u", doc_title="T", kind="parent",
            ),
            ChunkRecord(
                document_id=1, chunk_index=1, text="DETAIL",
                embedding=[0.0, 1.0, 0.0, 0.0],
                source_url="u", doc_title="T",
                kind="detail", parent_chunk_id=0,
            ),
        ]
    )
    hits = vs.search([1.0, 0.0, 0.0, 0.0], top_k=5)
    parent_hits = [h for h in hits if h.text == "PARENT"]
    assert parent_hits[0].kind == "parent"
    # Parents nao precisam de um "pai do pai".
    assert parent_hits[0].parent_text in (None, "")
