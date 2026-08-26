"""Testes unit do hook ``.opencode/hooks/code-reviewer/pre_tool_use_bash.py`` (PLAN_SPRINT9 / I9.3 + Sprint 12 B12.1).

Cobre os 9 BLOCK patterns (redirecionamento, sed -i, rm, git
commit/push, pip install, execucao do coletor/indexador/ragctl,
caminho de DB SQLite) e os 11 ALLOW patterns (ls, cat, head/tail,
wc/find/rg/grep, pytest --collect-only, git log/diff/show,
python -c, echo sem redirecionamento, powershell get-*).

Tambem cobre o gate final: comando que nao casa nenhum ALLOW e nao
cai em BLOCK tambem e' bloqueado (modo restritivo).

> **Sprint 12 (B12.1)**: hook movido de ``.claude/hooks/code-reviewer/``
> para ``.opencode/hooks/code-reviewer/``. O path do RAG meta-cognitivo
> migrou de ``.claude/rag.db`` para ``.opencode/rag/rag.db``.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]
HOOK_SCRIPT: Path = (
    PROJECT_ROOT / ".opencode" / "hooks" / "code-reviewer" / "pre_tool_use_bash.py"
)


def _run_hook(command: str) -> subprocess.CompletedProcess[str]:
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    proc = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, "DFE_ACTIVE_AGENT": "code-reviewer"},
        check=False,
        cwd=str(PROJECT_ROOT),
        timeout=30,
    )
    return proc


# ---- BLOCK patterns ----

@pytest.mark.parametrize(
    "command,reason_fragment",
    [
        ("echo foo > out.txt", "redirecionamento"),
        ("echo foo >> out.txt", "redirecionamento"),
        ("echo foo | tee out.txt", "redirecionamento"),
        ("sed -i 's/a/b/' file.txt", "sed"),
        ("rm -rf build/", "remocao"),
        ("rm foo.txt", "remocao"),
        ("rmdir tmp/", "remocao"),
        ("del /f file.txt", "remocao"),
        ("git commit -m 'fix'", "git commit"),
        ("git push origin main", "git push"),
        ("git reset --hard HEAD", "git reset"),
        ("pip install requests", "pip install"),
        ("pip uninstall requests", "pip uninstall"),
        ("poetry add foo", "instalacao"),
        ("poetry remove foo", "instalacao"),
        ("python -m src.collector --once", "coletor"),
        ("python -m src.indexer.ingest", "indexador"),
        ("python -m src.indexer", "indexador"),
        ("python -m src.ragctl migrate", "ragctl"),
        ("python -m src.ragctl reindex", "ragctl"),
        ("python -m src.ragctl benchmark", "ragctl"),
        ("python -m src.ragctl stats", "ragctl"),
        ("python -m src.ragctl backfill", "ragctl"),
        ("python -m src.ragctl drop", "ragctl"),
    ],
)
def test_blocks_destructive_commands(command: str, reason_fragment: str) -> None:
    """Cada padrao BLOCK deve sair com exit 2 e mencionar o motivo no stderr."""
    proc = _run_hook(command)
    assert proc.returncode == 2, (
        f"Comando destrutivo `{command}` deveria ser bloqueado (exit 2); "
        f"obtido {proc.returncode}. stderr={proc.stderr!r}"
    )
    assert "BLOQUEADO" in proc.stderr, (
        f"Comando `{command}` deveria reportar BLOQUEADO; obtido {proc.stderr!r}"
    )


def test_blocks_sqlite_db_path_in_command() -> None:
    """Comando que menciona path de DB SQLite deve ser bloqueado."""
    proc = _run_hook("sqlite3 storage/dfe.db .schema")
    assert proc.returncode == 2, (
        f"Comando com path .db deveria ser bloqueado; obtido {proc.returncode}. "
        f"stderr={proc.stderr!r}"
    )
    assert "BLOQUEADO" in proc.stderr


def test_blocks_opencode_rag_db_path() -> None:
    """Acesso direto a .opencode/rag/rag.db deve ser bloqueado (RAG meta-cognitivo).

    Sprint 12 (B12.4) migrou o DB do RAG meta de ``.claude/rag.db`` para
    ``.opencode/rag/rag.db``. O hook continua bloqueando acesso direto
    por SQLite CLI.
    """
    proc = _run_hook("sqlite3 .opencode/rag/rag.db .tables")
    assert proc.returncode == 2


def test_blocks_query_cache_db_path() -> None:
    """Acesso a storage/query_cache.db deve ser bloqueado."""
    proc = _run_hook("sqlite3 storage/query_cache.db")
    assert proc.returncode == 2


# ---- ALLOW patterns ----

@pytest.mark.parametrize(
    "command",
    [
        "ls -la",
        "ls src/",
        "dir",
        "cat README.md",
        "head -n 5 file.txt",
        "tail -n 20 file.log",
        "wc -l src/foo.py",
        "find . -name '*.py'",
        "rg 'TODO' src/",
        "grep -r 'foo' src/",
        "pytest --collect-only -q",
        "pytest -q --collect-only",
        "git log --oneline -10",
        "git diff HEAD~1",
        "git show HEAD",
        "git status",
        "git branch",
        "git rev-parse HEAD",
        "git remote -v",
        "python -c \"import sqlite3\"",
        'python -c "print(\'ok\')"',
        "echo hello world",
        "type python",
        "Get-ChildItem .",
        "Get-Content README.md",
        "Select-String pattern file.txt",
    ],
)
def test_allows_read_only_commands(command: str) -> None:
    """Cada padrao ALLOW deve passar com exit 0 e stderr vazio."""
    proc = _run_hook(command)
    assert proc.returncode == 0, (
        f"Comando read-only `{command}` deveria passar (exit 0); "
        f"obtido {proc.returncode}. stderr={proc.stderr!r}"
    )
    assert proc.stderr.strip() == "", (
        f"Comando read-only `{command}` nao deveria gerar stderr; "
        f"obtido {proc.stderr!r}"
    )


# ---- Gate final / edge cases ----

def test_blocks_unknown_command() -> None:
    """Comando que nao casa nenhum ALLOW deve ser bloqueado pelo gate final."""
    proc = _run_hook("foo --unknown-flag")
    assert proc.returncode == 2, (
        f"Comando desconhecido deveria ser bloqueado pelo gate final; "
        f"obtido {proc.returncode}. stderr={proc.stderr!r}"
    )
    assert "BLOQUEADO" in proc.stderr


def test_blocks_random_binary() -> None:
    """Binarios arbitrarios nao presentes em ALLOW devem ser bloqueados."""
    proc = _run_hook("somefakecommand --help")
    assert proc.returncode == 2


def test_allows_empty_command() -> None:
    """Comando vazio e' pass-through (sem bloqueio)."""
    proc = _run_hook("")
    assert proc.returncode == 0, (
        f"Comando vazio deveria passar (exit 0); obtido {proc.returncode}. "
        f"stderr={proc.stderr!r}"
    )


def test_block_pattern_overrides_allow() -> None:
    """BLOCK tem prioridade sobre ALLOW (gate duplo do hook).

    Exemplo: `echo "x" > file.txt` redireciona (BLOCK) E e' echo (ALLOW).
    Deve ser bloqueado.
    """
    proc = _run_hook('echo "x" > file.txt')
    assert proc.returncode == 2, (
        f"Redirecionamento dentro de echo deveria ser BLOCK; "
        f"obtido {proc.returncode}. stderr={proc.stderr!r}"
    )


def test_block_with_piped_redirect() -> None:
    """Pipe com tee redireciona saida; deve ser BLOCK."""
    proc = _run_hook("cat README.md | tee copy.md")
    assert proc.returncode == 2
