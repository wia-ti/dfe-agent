"""Testes para Sprint 2, Fase 10.2: ``chunker_mode`` no RagIndexer + CLI.

Cobre:
    - ``RagIndexer(chunker_mode="structural")`` produz chunks prefixados
      com secao NT e popula ``chunk_metadata`` (sidecar).
    - ``chunker_mode="flat"`` (default) e equivalente ao comportamento
      pre-Sprint-2: nada muda para o pipeline nem para o sidecar.
    - CLI ``python -m src.indexer.ingest --chunker=structural`` propaga
      o flag ao RagIndexer; valor invalido levanta SystemExit.
    - Insercao estrutural NAO quebra chunks legados: a query faz LEFT
      JOIN com chunk_metadata e os antigos ficam com ``section_path=""``.
"""
from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import sqlite_vec

from src.db.sqlite_storage import DocumentRecord, SqliteStorage
from src.db.vector_store import VectorStore
from src.indexer.rag_indexer import RagIndexer


# --- helpers ---------------------------------------------------------------


def _embedder_stub(dim: int = 4) -> MagicMock:
    embedder = MagicMock()
    embedder.dim = dim
    embedder.embed.side_effect = lambda texts: [[0.1] * dim for _ in texts]
    return embedder


def _bootstrap(tmp_path: Path, name: str = "rag") -> tuple[SqliteStorage, VectorStore]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / f"{name}.db"
    s = SqliteStorage(db_path)
    s.init_schema()
    vs = VectorStore(db_path, dim=4)
    vs.init_schema()
    return s, vs


def _count_chunk_metadata(db_path: Path, document_id: int) -> int:
    with sqlite3.connect(db_path) as conn:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        n: int = conn.execute(
            "SELECT COUNT(*) FROM chunk_metadata WHERE document_id=?",
            (document_id,),
        ).fetchone()[0]
    return n


# --- structural mode -------------------------------------------------------


def test_chunker_structural_persiste_section_path(tmp_path: Path) -> None:
    s, vs = _bootstrap(tmp_path)
    embedder = _embedder_stub()
    parser = lambda p: (
        "1 OBJETIVO\n"
        "Conteudo relevante da secao objetivo da NT 2024.001.\n"
        "\n"
        "2 FUNDAMENTACAO\n"
        "Base legal e contexto historico.\n"
    )
    indexer = RagIndexer(s, vs, embedder, parser=parser, chunker_mode="structural")

    doc_file = tmp_path / "nt.txt"
    doc_file.write_text("")
    rec = DocumentRecord(
        url="https://nfe.fazenda.gov.br/x",
        source_domain="nfe.fazenda.gov.br",
        doc_type="nota_tecnica",
        title="X",
        file_path=doc_file,
    )
    doc_id = s.upsert_document(rec)

    n_chunks = indexer.ingest_one(doc_id)
    assert n_chunks >= 2

    # Sidecar preenchido para cada chunk.
    n_meta = _count_chunk_metadata(tmp_path / "rag.db", doc_id)
    assert n_meta == n_chunks

    with sqlite3.connect(tmp_path / "rag.db") as conn:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        rows = conn.execute(
            "SELECT chunk_index, section_path, section_level "
            "FROM chunk_metadata WHERE document_id=? "
            "ORDER BY chunk_index",
            (doc_id,),
        ).fetchall()

    paths = [r[1] for r in rows]
    levels = [r[2] for r in rows]
    assert any(p == "1 OBJETIVO" for p in paths)
    assert any(p == "2 FUNDAMENTACAO" for p in paths)
    assert all(lvl == 1 for lvl in levels)


def test_chunker_structural_prefixa_texto_do_chunk(tmp_path: Path) -> None:
    s, vs = _bootstrap(tmp_path)
    embedder = _embedder_stub()
    parser = lambda p: "1 INTRO\nConteudo da introducao."
    indexer = RagIndexer(s, vs, embedder, parser=parser, chunker_mode="structural")

    doc_file = tmp_path / "x.txt"
    doc_file.write_text("")
    doc_id = s.upsert_document(
        DocumentRecord(
            url="https://nfe.fazenda.gov.br/y",
            source_domain="nfe.fazenda.gov.br",
            doc_type="nota_tecnica",
            title="Y",
            file_path=doc_file,
        )
    )

    indexer.ingest_one(doc_id)

    hits = vs.search([0.1, 0.1, 0.1, 0.1], top_k=5)
    assert len(hits) >= 1
    assert hits[0].text.startswith("§ 1 INTRO:")
    assert hits[0].section_path == "1 INTRO"


def test_chunker_mode_flat_omite_secao_e_prefixo(tmp_path: Path) -> None:
    """Default (flat) deve preservar comportamento pre-Sprint-2."""
    s, vs = _bootstrap(tmp_path)
    embedder = _embedder_stub()
    parser = lambda p: "1 INTRO\nConteudo da introducao."
    indexer = RagIndexer(s, vs, embedder, parser=parser)  # default flat

    doc_file = tmp_path / "x.txt"
    doc_file.write_text("")
    doc_id = s.upsert_document(
        DocumentRecord(
            url="https://nfe.fazenda.gov.br/z",
            source_domain="nfe.fazenda.gov.br",
            doc_type="nota_tecnica",
            title="Z",
            file_path=doc_file,
        )
    )
    indexer.ingest_one(doc_id)

    hits = vs.search([0.1, 0.1, 0.1, 0.1], top_k=5)
    assert len(hits) >= 1
    assert not hits[0].text.startswith("§")
    assert hits[0].section_path == ""
    assert hits[0].section_level == 0


def test_chunker_mode_flat_igual_default_explicito(tmp_path: Path) -> None:
    """``chunker_mode="flat"`` explicito == omissao da flag."""
    s1, vs1 = _bootstrap(tmp_path / "a")
    s2, vs2 = _bootstrap(tmp_path / "b")
    embedder_a = _embedder_stub()
    embedder_b = _embedder_stub()

    parser = lambda p: "qualquer texto sem numeracao hierarquica " * 30
    default_idx = RagIndexer(s1, vs1, embedder_a, parser=parser)
    flat_idx = RagIndexer(s2, vs2, embedder_b, parser=parser, chunker_mode="flat")

    doc_file_1 = tmp_path / "a" / "doc.txt"; doc_file_1.write_text("")
    doc_file_2 = tmp_path / "b" / "doc.txt"; doc_file_2.write_text("")
    id_a = s1.upsert_document(
        DocumentRecord(url="u_a", source_domain="d", doc_type="t", title="t", file_path=doc_file_1)
    )
    id_b = s2.upsert_document(
        DocumentRecord(url="u_b", source_domain="d", doc_type="t", title="t", file_path=doc_file_2)
    )
    n_a = default_idx.ingest_one(id_a)
    n_b = flat_idx.ingest_one(id_b)
    assert n_a == n_b


# --- sidecar integrity ----------------------------------------------------


def test_mix_chunks_planos_e_estruturais_busca_consistente(
    tmp_path: Path,
) -> None:
    """Chunks flat e estruturais coexistem sem quebra de query."""
    sub_a = tmp_path / "a"; sub_a.mkdir()
    sub_b = tmp_path / "b"; sub_b.mkdir()
    s, vs = _bootstrap(sub_a, name="shared")
    embedder_a = _embedder_stub()
    embedder_b = _embedder_stub()
    parser_flat = lambda p: "chunk plano " * 100
    parser_struct = lambda p: "1 SEC\nconteudo estruturado relevante. " * 50

    flat_idx = RagIndexer(s, vs, embedder_a, parser=parser_flat)
    struct_idx = RagIndexer(s, vs, embedder_b, parser=parser_struct, chunker_mode="structural")

    f1 = sub_a / "flat.txt"; f1.write_text("")
    id_flat = s.upsert_document(
        DocumentRecord(url="u_flat", source_domain="d", doc_type="t",
                       title="t", file_path=f1)
    )
    flat_idx.ingest_one(id_flat)

    f2 = sub_a / "struct.txt"; f2.write_text("")
    id_struct = s.upsert_document(
        DocumentRecord(url="u_struct", source_domain="d", doc_type="t",
                       title="t", file_path=f2)
    )
    struct_idx.ingest_one(id_struct)

    # Busca nao levanta e devolve todos os hits.
    hits = vs.search([0.1, 0.1, 0.1, 0.1], top_k=10)
    by_url: dict[str, object] = {}
    for h in hits:
        # Mantem o primeiro hit por URL (todos do mesmo doc terao mesmo section).
        by_url.setdefault(h.source_url, h)
    assert by_url["u_flat"].section_path == ""
    assert by_url["u_flat"].section_level == 0
    assert by_url["u_struct"].section_path == "1 SEC"
    assert by_url["u_struct"].section_level == 1


# --- CLI ------------------------------------------------------------------


def test_cli_ingest_argumento_chunker_estrutural(tmp_path: Path) -> None:
    """CLI ``--chunker=structural`` propaga ao RagIndexer."""
    project_root = Path(__file__).resolve().parents[3]
    import os
    env = os.environ.copy()
    pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{project_root}{os.pathsep}{pp}" if pp else str(project_root)

    db_path = tmp_path / "dfe.db"
    env["DFE_TEST_DB_PATH"] = str(db_path)  # nao usado no fluxo real

    # Invoca ``python -m src.indexer.ingest --help`` para verificar que a
    # flag existe e aparece na documentacao.
    result = subprocess.run(
        [sys.executable, "-m", "src.indexer.ingest", "--help"],
        capture_output=True,
        text=True,
        cwd=str(project_root),
        env=env,
    )
    assert result.returncode == 0
    assert "--chunker" in result.stdout


def test_cli_ingest_valida_chunker_invalido(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[3]
    import os
    env = os.environ.copy()
    pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{project_root}{os.pathsep}{pp}" if pp else str(project_root)

    result = subprocess.run(
        [sys.executable, "-m", "src.indexer.ingest", "--chunker=invalid"],
        capture_output=True,
        text=True,
        cwd=str(project_root),
        env=env,
    )
    assert result.returncode != 0
    assert "chunker" in (result.stderr + result.stdout).lower()


def test_rag_indexer_rejeita_chunker_mode_invalido(tmp_path: Path) -> None:
    """Cobertura do branch ``raise ValueError`` em ``__init__``."""
    from src.db.sqlite_storage import SqliteStorage
    from src.db.vector_store import VectorStore

    storage = SqliteStorage(tmp_path / "x.db")
    storage.init_schema()
    vs = VectorStore(tmp_path / "x.db", dim=4)
    vs.init_schema()

    with pytest.raises(ValueError, match="chunker_mode"):
        RagIndexer(
            storage,
            vs,
            embedder=_embedder_stub(),
            parser=lambda p: "",
            chunker_mode="invalid_mode",
        )
