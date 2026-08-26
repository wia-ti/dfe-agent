"""Testes unit do hook ``.opencode/hooks/code-reviewer/pre_tool_use.py`` (PLAN_SPRINT9 / I9.2 + Sprint 12 B12.1).

Cobre cada tool interceptada pelo ``_WRITE_TOOLS`` (Write / Edit /
MultiEdit / NotebookEdit) e cada tool read-only que o agent tem
autorizada (Read / Glob / Grep / WebFetch / WebSearch). Valida tambem
que o log de eventos registra o bloqueio e que a mensagem de erro
cita o escopo read-only para o agent entender o motivo.

Estrategia: ``subprocess.run`` com ``sys.executable`` (padrao de
``tests/integration/test_agent_dispatch.py``), evitando acoplar com
detalhes internos de import do hook.

> **Sprint 12 (B12.1)**: hook movido de ``.claude/hooks/code-reviewer/``
> para ``.opencode/hooks/code-reviewer/``.
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
    PROJECT_ROOT / ".opencode" / "hooks" / "code-reviewer" / "pre_tool_use.py"
)
LOG_PATH: Path = PROJECT_ROOT / "storage" / "agent_hooks.log"


def _run_hook(payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
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


def _truncate_log() -> None:
    """Garante estado limpo do log antes de testes que inspecionam linha nova."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("", encoding="utf-8")


@pytest.mark.parametrize(
    "tool_name",
    ["Write", "Edit", "MultiEdit", "NotebookEdit"],
)
def test_blocks_write_family(tool_name: str) -> None:
    """Cada tool de escrita deve sair com exit 2 e stderr contendo BLOQUEADO."""
    proc = _run_hook({
        "tool_name": tool_name,
        "tool_input": {"file_path": "src/qualquer.py"},
    })
    assert proc.returncode == 2, (
        f"{tool_name} deveria ser bloqueado com exit 2; obtido {proc.returncode}. "
        f"stderr={proc.stderr!r}"
    )
    assert "BLOQUEADO" in proc.stderr, (
        f"{tool_name} deveria reportar BLOQUEADO no stderr; obtido {proc.stderr!r}"
    )


def test_blocks_write_message_cites_read_only() -> None:
    """Mensagem de bloqueio deve dizer 'read-only' para o agent entender."""
    proc = _run_hook({
        "tool_name": "Write",
        "tool_input": {"file_path": "README.md"},
    })
    assert proc.returncode == 2
    assert "read-only" in proc.stderr.lower(), (
        f"Mensagem de bloqueio deve mencionar 'read-only'; obtido {proc.stderr!r}"
    )


def test_blocks_edit_references_delegation_path() -> None:
    """Mensagem de bloqueio deve sugerir o agent de implementacao como destino."""
    proc = _run_hook({
        "tool_name": "Edit",
        "tool_input": {"file_path": "src/foo.py"},
    })
    assert proc.returncode == 2
    for agent in ("dev",):
        assert agent in proc.stderr, (
            f"Mensagem deve apontar delegacao para '{agent}'; obtido {proc.stderr!r}"
        )


@pytest.mark.parametrize(
    "tool_name",
    ["Read", "Glob", "Grep", "WebFetch", "WebSearch", "List"],
)
def test_allows_read_only_tools(tool_name: str) -> None:
    """Tools read-only devem passar com exit 0 e stderr vazio."""
    proc = _run_hook({
        "tool_name": tool_name,
        "tool_input": {"file_path": "README.md"},
    })
    assert proc.returncode == 0, (
        f"{tool_name} deveria passar com exit 0; obtido {proc.returncode}. "
        f"stderr={proc.stderr!r}"
    )
    assert proc.stderr.strip() == "", (
        f"{tool_name} nao deveria gerar stderr; obtido {proc.stderr!r}"
    )


def test_block_writes_log_entry() -> None:
    """Bloqueio de Write deve registrar linha no log de eventos."""
    _truncate_log()
    proc = _run_hook({
        "tool_name": "Write",
        "tool_input": {"file_path": "src/qualquer.py"},
    })
    assert proc.returncode == 2
    log_text = LOG_PATH.read_text(encoding="utf-8")
    assert "[code-reviewer]" in log_text, (
        f"Log deveria ter tag [code-reviewer]; conteudo: {log_text!r}"
    )
    assert "pre_tool_use_block_write" in log_text, (
        f"Log deveria registrar evento pre_tool_use_block_write; "
        f"conteudo: {log_text!r}"
    )


def test_block_includes_file_path_in_log() -> None:
    """Linha de log deve incluir o arquivo alvo do bloqueio."""
    _truncate_log()
    target = "src/parser/qualquer.py"
    proc = _run_hook({
        "tool_name": "Write",
        "tool_input": {"file_path": target},
    })
    assert proc.returncode == 2
    log_text = LOG_PATH.read_text(encoding="utf-8")
    assert target in log_text, (
        f"Log deveria mencionar o arquivo alvo '{target}'; "
        f"conteudo: {log_text!r}"
    )


def test_handles_missing_payload_gracefully() -> None:
    """Sem payload (stdin vazio) hook nao deve crashar; cai em modo permissivo."""
    proc = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input="",
        capture_output=True,
        text=True,
        env={**os.environ, "DFE_ACTIVE_AGENT": "code-reviewer"},
        check=False,
        cwd=str(PROJECT_ROOT),
        timeout=30,
    )
    assert proc.returncode == 0, (
        f"Hook deveria tolerar payload vazio com exit 0; obtido {proc.returncode}. "
        f"stderr={proc.stderr!r}"
    )
