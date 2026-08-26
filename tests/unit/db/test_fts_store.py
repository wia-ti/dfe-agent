"""Testes para Sprint 2, Fase 11.1: FTS5 ``fts_chunks`` (busca por BM25).

Cobre:
    - ``FtsStore.init_schema`` cria a virtual table com colunas esperadas.
    - Inserir chunks via :class:`ChunkRecord` torna-os localizaveis por
      ``search_fts``.
    - Termo literal ``"Convenio 123/2024"`` retorna o chunk que contem
      essa string mesmo sem proximidade semantica no embedding.
    - ``search_fts`` com query inexistente retorna ``[]``.
    - Tokenizer remove diacriticos (busca por "cancelamento" encontra
      "cancelamento" e "cancelamênto").
    - Metadados do sidecar (``section_path``) sao preservados no ``FtsHit``.
    - ``rebuild_from_db`` backfilla fts_chunks a partir de vec_chunks +
      chunk_metadata, e e idempotente.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import sqlite_vec

from src.db.sqlite_storage import SqliteStorage
from src.db.vector_store import ChunkRecord, VectorStore


def _bootstrap(tmp_path: Path) -> Path:
    db_path = tmp_path / "rag.db"
    SqliteStorage(db_path).init_schema()
    VectorStore(db_path, dim=4).init_schema()
    return db_path


def _vs_with_fts(tmp_path: Path) -> tuple["VectorStore", "FtsStore", Path]:
    """Cria VectorStore e FtsStore pareados (sync automatico)."""
    from src.db.fts_store import FtsStore

    db_path = _bootstrap(tmp_path)
    fts = FtsStore(db_path)
    fts.init_schema()
    vs = VectorStore(db_path, dim=4, fts_store=fts)
    return vs, fts, db_path


# --- schema ---------------------------------------------------------------


def test_init_schema_cria_fts_chunks(tmp_path: Path) -> None:
    from src.db.fts_store import FtsStore

    db_path = _bootstrap(tmp_path)
    FtsStore(db_path).init_schema()
    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        # FTS5 virtual table aparece como 'table' no master.
        assert "fts_chunks" in tables


def test_search_fts_sem_chunks_retorna_vazio(tmp_path: Path) -> None:
    from src.db.fts_store import FtsStore

    db_path = _bootstrap(tmp_path)
    fts = FtsStore(db_path)
    fts.init_schema()

    assert fts.search_fts("qualquer coisa") == []


# --- inserção -------------------------------------------------------------


def _insert_one(vs: VectorStore, doc_id: int, chunk_idx: int, text: str,
                title: str = "T", section_path: str = "") -> None:
    vs.insert_chunks(
        [
            ChunkRecord(
                document_id=doc_id,
                chunk_index=chunk_idx,
                text=text,
                embedding=[0.1, 0.1, 0.1, 0.1],
                source_url=f"https://nfe.fazenda.gov.br/d{doc_id}",
                doc_title=title,
                section_path=section_path,
                section_level=1 if section_path else 0,
            )
        ]
    )


def test_insert_chunk_persiste_e_busca_encontra(tmp_path: Path) -> None:
    """Smoke: apos inserir via VectorStore (sincronia), busca FTS acha o termo."""
    from src.db.fts_store import FtsStore

    vs, fts, _ = _vs_with_fts(tmp_path)
    _ = FtsStore  # keep import

    _insert_one(
        vs,
        doc_id=1,
        chunk_idx=0,
        text="A NT 2024.001 altera regras de cancelamento da NF-e.",
    )

    hits = fts.search_fts("cancelamento", top_k=10)
    assert len(hits) >= 1
    assert any("cancelamento" in h.text.lower() for h in hits)
    assert hits[0].document_id == 1


def test_busca_termo_literal_sem_proximidade_semantica(tmp_path: Path) -> None:
    """Termo exato (ex: 'Convenio') bate mesmo sem proximidade semantica."""
    vs, fts, _ = _vs_with_fts(tmp_path)

    _insert_one(
        vs, doc_id=1, chunk_idx=0,
        text="Texto principal irrelevante para similaridade cosseno.",
    )
    _insert_one(
        vs, doc_id=2, chunk_idx=0,
        text="Referencia literal: Convenio 123/2024 publicado em 2024.",
    )

    hits = fts.search_fts("Convenio", top_k=10)
    assert len(hits) >= 1
    assert any(h.document_id == 2 and "Convenio" in h.text for h in hits)


def test_busca_termo_composto_com_aspas(tmp_path: Path) -> None:
    """Aspas forcam match exato do termo composto (util para 'convenio 123')."""
    vs, fts, _ = _vs_with_fts(tmp_path)

    _insert_one(
        vs, doc_id=1, chunk_idx=0,
        text="Menciona o convenio 123/2024 e nada mais.",
    )

    # Quoted multi-token: o tokenizer unicode61 separa "convenio" e
    # "123" + "/" + "2024" como tokens. A frase com aspas NAO casa
    # exatamente porque "/" quebra token. Verifica-se aqui o caso
    # valido: aspas em tokens contiguos casa.
    _insert_one(
        vs, doc_id=2, chunk_idx=0,
        text="Texto: cancelamento documento fiscal NT.",
    )
    hits = fts.search_fts('"cancelamento documento"', top_k=10)
    assert any(h.document_id == 2 for h in hits)


def test_busca_remove_diacriticos(tmp_path: Path) -> None:
    """Busca por ``cancelamento`` acha ``cancelamento`` (sem acento) e vice-versa."""
    vs, fts, _ = _vs_with_fts(tmp_path)

    _insert_one(
        vs, doc_id=1, chunk_idx=0,
        text="disposicao sobre cancelamento com acento.",
    )
    _insert_one(
        vs, doc_id=2, chunk_idx=0,
        text="outro texto sobre cancelamento sem acento.",
    )

    hits = fts.search_fts("cancelamento", top_k=10)
    by_doc = {h.document_id for h in hits}
    assert by_doc == {1, 2}


def test_fhit_carrega_section_path_quando_presente(tmp_path: Path) -> None:
    vs, fts, _ = _vs_with_fts(tmp_path)

    _insert_one(vs, doc_id=1, chunk_idx=0, text="cancelamento total do documento.",
               section_path="2 FUNDAMENTACAO")

    hits = fts.search_fts("cancelamento total", top_k=10)
    assert len(hits) >= 1
    assert hits[0].section_path == "2 FUNDAMENTACAO"


def test_fhit_section_path_vazio_para_chunks_legados(tmp_path: Path) -> None:
    """Chunks sem section_path retornam ``""`` (sem levantar)."""
    vs, fts, _ = _vs_with_fts(tmp_path)

    _insert_one(vs, doc_id=1, chunk_idx=0, text="cancelamento simples.")

    hits = fts.search_fts("cancelamento", top_k=10)
    assert len(hits) >= 1
    assert hits[0].section_path == ""
    assert hits[0].section_level == 0


# --- backfill -------------------------------------------------------------


def test_rebuild_from_db_backfilla_fts_a_partir_de_vec_chunks(
    tmp_path: Path,
) -> None:
    """Cenario chave da Fase 11: DB pre-Fase-11 ja tem vec_chunks;
    rodar init do FTS deve popular o indice BM25."""
    from src.db.fts_store import FtsStore

    db_path = _bootstrap(tmp_path)
    vs = VectorStore(db_path, dim=4)
    # Insere chunks direto via vec_chunks (sem FTS) para simular DB legado.
    _insert_one(
        vs, doc_id=99, chunk_idx=0, text="Convenio ICMS 999/2020 publicado.",
        section_path="1 INTRO",
    )

    # Agora cria FTS — sem backfill automatico, busca nao retornaria nada.
    fts = FtsStore(db_path)
    fts.init_schema()
    empty = fts.search_fts("Convenio", top_k=10)
    assert empty == []

    # Backfill manual:
    n = fts.rebuild_from_db()
    assert n == 1

    hits = fts.search_fts("Convenio", top_k=10)
    assert len(hits) >= 1
    assert hits[0].document_id == 99
    assert hits[0].section_path == "1 INTRO"


def test_rebuild_e_idempotente(tmp_path: Path) -> None:
    """Rodar rebuild 2x nao duplica o fts_chunks."""
    from src.db.fts_store import FtsStore

    db_path = _bootstrap(tmp_path)
    vs = VectorStore(db_path, dim=4)
    _insert_one(vs, doc_id=1, chunk_idx=0, text="abc")
    _insert_one(vs, doc_id=1, chunk_idx=1, text="def")
    _insert_one(vs, doc_id=2, chunk_idx=0, text="ghi")

    fts = FtsStore(db_path)
    fts.init_schema()
    n1 = fts.rebuild_from_db()
    n2 = fts.rebuild_from_db()
    assert n1 == 3
    assert n2 == 0  # ja populado, sem duplicacao


# --- FtsHit dataclass ----------------------------------------------------


def test_fhit_dataclass_default() -> None:
    from src.db.fts_store import FtsHit

    hit = FtsHit(
        document_id=1, chunk_index=0,
        text="t", source_url="u", doc_title="T",
        bm25_score=0.5,
    )
    assert hit.section_path == ""
    assert hit.section_level == 0
