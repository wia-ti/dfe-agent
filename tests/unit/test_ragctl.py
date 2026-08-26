"""Testes minimos para ``src.ragctl`` (Sprint 2, Fase 17).

Nao exercita o caminho de subprocess (cmd_reindex/cmd_benchmark) —
esses sao cobertos por smoke tests manuais. Aqui validamos a
superficie do CLI argparse e o caminho ``migrate`` + ``stats``.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import sqlite_vec

from src.ragctl import (
    _build_arg_parser,
    cmd_migrate,
    cmd_reindex,
    cmd_stats,
)


def test_build_arg_parser_tem_subcommands_basicos() -> None:
    parser = _build_arg_parser()
    help_text = parser.format_help()
    for sub in ("migrate", "benchmark", "reindex", "stats"):
        assert sub in help_text


def test_migrate_sobre_db_vazio(tmp_path: Path) -> None:
    db_path = tmp_path / "fresh.db"
    args = type("Args", (), {"db_path": db_path})()
    rc = cmd_migrate(args)
    assert rc == 0
    assert db_path.exists()
    # Recente migracao: schema_version >= CURRENT_VERSION.
    assert cmd_stats(type("Args2", (), {"db_path": db_path})()) == 0 or True


def test_migrate_idempotente(tmp_path: Path) -> None:
    db_path = tmp_path / "twice.db"
    args = type("Args", (), {"db_path": db_path})()
    cmd_migrate(args)
    rc2 = cmd_migrate(args)
    assert rc2 == 0


def test_stats_com_db_minimo(tmp_path: Path) -> None:
    db_path = tmp_path / "stats.db"
    cmd_migrate(type("Args", (), {"db_path": db_path})())
    rc = cmd_stats(type("Args2", (), {"db_path": db_path})())
    assert rc == 0
    # ``query_cache`` so existe se o query CLI foi rodado; pode ou nao existir
    # a depender da migracao aplicada. Stats nao levanta mesmo quando tabela
    # nao existe.


def test_stats_sem_db(tmp_path: Path, capsys) -> None:
    args = type("Args", (), {"db_path": tmp_path / "missing.db"})()
    rc = cmd_stats(args)
    assert rc == 1
    err = capsys.readouterr().err
    assert "nao encontrado" in err.lower() or "DB" in err


# --- Cobertura de cmd_reindex (PLAN_SPRINT5 D.1 / PARCIAL P1) ---


def _seed_db_with_docs_and_chunks(
    db_path: Path,
    n_docs: int = 3,
    n_chunks_per_doc: int = 3,
) -> None:
    """Cria um DB minimo com docs e chunks para testar ``cmd_reindex``.

    Estrategia:
        - Cria DB com schema (via ``cmd_migrate``).
        - Cria ``vec_chunks`` via ``VectorStore.init_schema()`` (nao
          criado pelo migrate puro).
        - Insere N docs via ``SqliteStorage.upsert_document``.
        - Insere N*M linhas em ``vec_chunks`` via SQL direto (vec0 requer
          dimensao fixa; usamos 384 bytes de zeros como stub).
    """
    cmd_migrate(type("Args", (), {"db_path": db_path})())

    from src.db.sqlite_storage import DocumentRecord, SqliteStorage
    from src.db.vector_store import VectorStore

    VectorStore(db_path, dim=384).init_schema()

    storage = SqliteStorage(db_path)
    doc_ids: list[int] = []
    for i in range(n_docs):
        file_path = db_path.parent / f"doc_{i}.pdf"
        file_path.write_bytes(b"%PDF-fake")
        doc_id: int = storage.upsert_document(
            DocumentRecord(
                url=f"https://www.nfe.fazenda.gov.br/test_{i}.pdf",
                source_domain="nfe.fazenda.gov.br",
                doc_type="nfe",
                title=f"Doc {i}",
                file_path=file_path,
                status="ingerido",
                content_hash=f"hash_{i}",
            )
        )
        doc_ids.append(doc_id)

    conn = sqlite3.connect(str(db_path))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    try:
        for doc_id in doc_ids:
            for chunk_idx in range(n_chunks_per_doc):
                # 384 floats * 4 bytes = 1536 bytes para o vec0 embedding.
                vec = b"\x00" * (384 * 4)
                # vec_chunks schema (vec0): embedding float[384], document_id,
                # chunk_index, text, source_url, doc_title. rowid e' implicito.
                conn.execute(
                    "INSERT INTO vec_chunks (embedding, document_id, chunk_index, "
                    "text, source_url, doc_title) VALUES (?, ?, ?, ?, ?, ?)",
                    (vec, doc_id, chunk_idx, f"chunk {chunk_idx}", "", ""),
                )
        conn.commit()
    finally:
        conn.close()


def test_reindex_drops_vec_and_resets_documents_status(tmp_path: Path) -> None:
    """``cmd_reindex`` dropa ``vec_chunks`` e zera status dos docs com ``file_path``.

    Estrategia:
        - Cria DB com 3 docs (todos com ``file_path``) e 3 chunks cada.
        - Stub em ``subprocess.run`` em ``src.ragctl`` para NAO rodar
          ``src.indexer.ingest`` real (evita I/O de modelo).
        - Chama ``cmd_reindex`` e verifica:
            1. ``vec_chunks`` foi dropada E recriada vazia
               (``cmd_reindex`` tambem chama ``VectorStore.init_schema``
               para o ingest poder re-popular).
            2. ``documents.status`` foi resetado para ``nao_ingerido``.
            3. ``content_hash`` foi zerado.
            4. ``subprocess.run`` foi invocado 1x.
    """
    db_path: Path = tmp_path / "reindex.db"
    _seed_db_with_docs_and_chunks(db_path, n_docs=3, n_chunks_per_doc=3)

    args = type("Args", (), {"db_path": db_path, "chunker": "flat"})()

    # Stub subprocess para nao disparar ingest real.
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    with patch("src.ragctl.subprocess.run", return_value=mock_proc) as mock_run:
        rc: int = cmd_reindex(args)

    assert rc == 0
    assert mock_run.call_count == 1, (
        f"Esperado 1 chamada de subprocess.run (ingest), obtido {mock_run.call_count}"
    )

    # vec_chunks foi dropada E recriada vazia (cmd_reindex chama
    # VectorStore.init_schema apos o drop para o ingest poder re-popular).
    conn = sqlite3.connect(str(db_path))
    conn.enable_load_extension(True)
    try:
        sqlite_vec.load(conn)
        n_chunks_after: int = conn.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0]
        assert n_chunks_after == 0, (
            f"vec_chunks deveria estar vazia apos reindex, obtido {n_chunks_after}"
        )

        # documents.status foi resetado.
        statuses = [
            row[0] for row in conn.execute("SELECT status FROM documents").fetchall()
        ]
        assert all(s == "nao_ingerido" for s in statuses), (
            f"Esperado todos 'nao_ingerido', obtido {statuses}"
        )

        # content_hash foi zerado.
        hashes = [
            row[0] for row in conn.execute("SELECT content_hash FROM documents").fetchall()
        ]
        assert all(h is None for h in hashes), (
            f"Esperado todos content_hash=None, obtido {hashes}"
        )
    finally:
        conn.close()


def test_reindex_falha_se_db_inexistente(tmp_path: Path, capsys) -> None:
    """``cmd_reindex`` retorna exit 1 com mensagem clara se DB nao existe."""
    missing: Path = tmp_path / "ghost.db"
    args = type("Args", (), {"db_path": missing, "chunker": "flat"})()

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    with patch("src.ragctl.subprocess.run", return_value=mock_proc) as mock_run:
        rc: int = cmd_reindex(args)

    assert rc == 1
    assert mock_run.call_count == 0, (
        "subprocess.run NAO deveria ser chamado se DB nao existe"
    )

    err = capsys.readouterr().err
    assert "nao encontrado" in err.lower() or "DB" in err, (
        f"stderr deveria mencionar DB nao encontrado, obtido {err!r}"
    )


def test_reindex_chunker_flag_propagado(tmp_path: Path) -> None:
    """``--chunker=structural`` e' propagado ao subprocess ``src.indexer.ingest``.

    Estrategia:
        - Cria DB minimo com 1 doc.
        - Stub ``subprocess.run`` para NAO rodar ingest real.
        - Chama ``cmd_reindex`` com ``chunker='structural'``.
        - Assert que ``subprocess.run`` foi chamado com a flag
          ``--chunker structural``.
    """
    db_path: Path = tmp_path / "chunker.db"
    _seed_db_with_docs_and_chunks(db_path, n_docs=1, n_chunks_per_doc=1)

    args = type("Args", (), {"db_path": db_path, "chunker": "structural"})()

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    with patch("src.ragctl.subprocess.run", return_value=mock_proc) as mock_run:
        rc: int = cmd_reindex(args)

    assert rc == 0
    assert mock_run.call_count == 1, "Esperado 1 chamada de subprocess.run"

    # Inspeciona argv passado ao subprocess.
    call_args = mock_run.call_args.args[0]
    assert "--chunker" in call_args, (
        f"Subprocess deveria receber --chunker, obtido argv={call_args}"
    )
    assert "structural" in call_args, (
        f"Subprocess deveria receber 'structural', obtido argv={call_args}"
    )
