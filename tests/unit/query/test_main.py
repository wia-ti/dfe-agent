"""Testes do CLI em src.query.__main__.

Cobre:
    - Sem pergunta: imprime uso em stderr e exit != 0.
    - Banco inexistente: imprime JSON com NO_EVIDENCE_MESSAGE e sources vazio, exit 0.
    - Banco vazio (schema inicializado, sem documentos): mesma resposta de "sem base".

Isolamento: cada teste roda o subprocess em ``tmp_path`` para nao afetar o estado
real do storage do desenvolvedor. Usa ``sys.executable -m src.query`` para que o
``__main__.py`` do pacote seja executado exatamente como em producao.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]


def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    """Executa ``python -m src.query <args>`` em ``cwd`` isolado.

    Limpa variaveis de cobertura herdadas do processo de teste para evitar
    conflito com a execucao aninhada do CLI. Tambem define ``HF_HUB_OFFLINE=1``
    para forcar uso do cache local do HuggingFace (caso o modelo ja esteja
    baixado em ``~/.cache/huggingface/``); em testes offline isso evita
    tentativas de download e seus efeitos colaterais (criacao de symlinks,
    ACCESS_VIOLATION em alguns ambientes Windows quando o disco esta cheio).

    Para reduzir uso de memoria do OpenBLAS em subprocessos Windows,
    limitamos ``OPENBLAS_NUM_THREADS=1`` e ``OMP_NUM_THREADS=1``.

    PLAN_SPRINT5 A.1: prepende ``.opencode`` em ``PYTHONPATH`` para que
    ``src.utils.http_guard_bootstrap`` consiga importar ``hooks.domain_guard``
    no subprocess.

    PLAN_SPRINT7 A.4: confirmado em implementacao que o PYTHONPATH para
    localizar o PACOTE ``src`` (raiz) e' obrigatorio por design de
    subprocess em ``tmp_path`` (Python precisa de ``src/`` em sys.path
    para resolver ``-m src.query``). O bootstrap em
    ``src.utils.syspath_bootstrap`` cobre o caso do ``hooks.domain_guard``
    quando o CLI e' invocado a partir do cwd do projeto pelo usuario;
    testes em ``cwd=tmp_path`` continuam precisando deste workaround de
    PYTHONPATH. Comentario do PLAN_SPRINT7 A.4 sobre remocao foi revisto.
    """
    cmd = [sys.executable, "-m", "src.query", *args]
    env = os.environ.copy()
    existing_pp = env.get("PYTHONPATH", "")
    pp_parts: list[str] = [str(PROJECT_ROOT)]
    if existing_pp:
        pp_parts.append(existing_pp)
    env["PYTHONPATH"] = os.pathsep.join(pp_parts)
    env["HF_HUB_OFFLINE"] = "1"
    env["OPENBLAS_NUM_THREADS"] = "1"
    env["OMP_NUM_THREADS"] = "1"
    env.pop("COV_CORE_SOURCE", None)
    env.pop("COV_CORE_CONFIG", None)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
        check=False,
    )


def test_cli_without_question_exits_nonzero(tmp_path: Path) -> None:
    """`python -m src.query` sem pergunta -> exit != 0 e uso em stderr."""
    result = _run_cli(cwd=tmp_path)

    assert result.returncode != 0, (
        f"expected nonzero exit, got {result.returncode}\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    assert "Uso" in result.stderr or "uso" in result.stderr.lower()


def test_cli_with_missing_database_returns_no_evidence_message(tmp_path: Path) -> None:
    """Sem storage/dfe.db, CLI imprime JSON com NO_EVIDENCE_MESSAGE e sources=[]."""
    assert not (tmp_path / "storage" / "dfe.db").exists()

    result = _run_cli("pergunta qualquer", cwd=tmp_path)

    assert result.returncode == 0, (
        f"expected exit 0, got {result.returncode}\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )

    payload = json.loads(result.stdout)
    assert payload["answer"] == "Nao encontrei base para responder"
    assert payload["sources"] == []


def test_cli_with_empty_database_returns_no_evidence_message(tmp_path: Path) -> None:
    """storage/dfe.db existe mas sem chunks indexados -> mesma resposta de 'sem base'."""
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    db_path = storage_dir / "dfe.db"

    conn = _sqlite3_connect_with_vec(db_path)
    try:
        _init_empty_schemas(conn)
    finally:
        conn.close()

    result = _run_cli("pergunta qualquer", cwd=tmp_path)

    assert result.returncode == 0, (
        f"expected exit 0, got {result.returncode}\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    payload = json.loads(result.stdout)
    assert payload["answer"] == "Nao encontrei base para responder"
    assert payload["sources"] == []


# --- Fase 11: --hybrid ----------------------------------------------------


def test_cli_with_hybrid_on_empty_database_does_not_crash(tmp_path: Path) -> None:
    """--hybrid em DB vazio: CLI completa sem erro e devolve 'sem base'."""
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    db_path = storage_dir / "dfe.db"

    conn = _sqlite3_connect_with_vec(db_path)
    try:
        _init_empty_schemas(conn)
    finally:
        conn.close()

    result = _run_cli("--hybrid", "pergunta qualquer", cwd=tmp_path)

    assert result.returncode == 0, (
        f"hybrid CLI crashed: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    payload = json.loads(result.stdout)
    assert payload["answer"] == "Nao encontrei base para responder"
    assert payload["sources"] == []


def test_cli_help_documents_hybrid_flag(tmp_path: Path) -> None:
    """--help documenta a flag ``--hybrid``."""
    result = _run_cli("--help", cwd=tmp_path)
    assert "--hybrid" in result.stdout


def test_cli_with_hierarchical_on_empty_database_does_not_crash(tmp_path: Path) -> None:
    """--hierarchical em DB vazio: degrada para sem chunks; nao falha."""
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    db_path = storage_dir / "dfe.db"

    conn = _sqlite3_connect_with_vec(db_path)
    try:
        _init_empty_schemas(conn)
    finally:
        conn.close()

    result = _run_cli("--hierarchical", "pergunta qualquer", cwd=tmp_path)

    assert result.returncode == 0, (
        f"hierarchical CLI crashed: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    payload = json.loads(result.stdout)
    assert payload["answer"] == "Nao encontrei base para responder"
    assert payload["sources"] == []


def test_cli_help_documents_hierarchical_flag(tmp_path: Path) -> None:
    """--help documenta a flag ``--hierarchical``."""
    result = _run_cli("--help", cwd=tmp_path)
    assert "--hierarchical" in result.stdout


def test_cli_with_rerank_on_empty_database_does_not_crash(tmp_path: Path) -> None:
    """--rerank em DB vazio: degrada para 'sem base' sem invocar cross-encoder."""
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    db_path = storage_dir / "dfe.db"

    conn = _sqlite3_connect_with_vec(db_path)
    try:
        _init_empty_schemas(conn)
    finally:
        conn.close()

    result = _run_cli("--rerank", "pergunta qualquer", cwd=tmp_path)

    assert result.returncode == 0, (
        f"rerank CLI crashed: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    payload = json.loads(result.stdout)
    assert payload["answer"] == "Nao encontrei base para responder"


def test_cli_help_documents_rerank_flag(tmp_path: Path) -> None:
    """--help documenta a flag ``--rerank``."""
    result = _run_cli("--help", cwd=tmp_path)
    assert "--rerank" in result.stdout


# ---------------------------------------------------------------------------
# Helpers locais (isolados: nao usam src.db.* para nao importar embeddings)
# ---------------------------------------------------------------------------


def _sqlite3_connect_with_vec(db_path: Path):
    """Abre sqlite3 com sqlite-vec carregado (espelha o que VectorStore faz)."""
    import sqlite3

    import sqlite_vec

    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    return conn


def _init_empty_schemas(conn) -> None:
    """Cria as tabelas `documents` e `vec_chunks` (dim=384) vazias."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS documents (
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
            status TEXT NOT NULL CHECK(status IN ('nao_ingerido','ingerido','falhou'))
        );
        CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
        """
    )
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0("
        "embedding float[384], document_id INTEGER, chunk_index INTEGER, "
        "text TEXT, source_url TEXT, doc_title TEXT)"
    )
    conn.commit()
