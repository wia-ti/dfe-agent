"""Testes unit do hook ``.opencode/hooks/deployer/post_tool_use.py`` (PLAN_SPRINT18 / Task 2.3).

Cobre:

- Hook exit 0 para qualquer tool (observer; NAO bloqueia).
- Hook NAO roda pytest (deployer nao testa codigo).
- Hook escreve log_event em ``storage/agent_hooks.log``.

Diferenca vs `@dev/post_tool_use.py`:
- dev roda pytest da suite apropriada.
- deployer e' observador puro (deploy e' acao atomica).
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
    PROJECT_ROOT / ".opencode" / "hooks" / "deployer" / "post_tool_use.py"
)
LOG_PATH: Path = PROJECT_ROOT / "storage" / "agent_hooks.log"


def _run_hook(payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, "DFE_ACTIVE_AGENT": "deployer"},
        check=False,
        cwd=str(PROJECT_ROOT),
        timeout=30,
    )
    return proc


def _truncate_log() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("", encoding="utf-8")


def test_post_tool_use_exits_zero_for_bash() -> None:
    proc = _run_hook(
        {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}}
    )
    assert proc.returncode == 0, (
        f"post_tool_use do deployer deveria exit 0 (observer); "
        f"obtido rc={proc.returncode}, stderr={proc.stderr!r}"
    )


def test_post_tool_use_exits_zero_for_write() -> None:
    """Mesmo Write (que pre_tool_use bloqueia) deve passar no post_tool_use."""
    proc = _run_hook(
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "AGENTS.md", "content": "x"},
        }
    )
    assert proc.returncode == 0, (
        f"post_tool_use deveria exit 0 (PostToolUse nunca bloqueia); "
        f"obtido rc={proc.returncode}, stderr={proc.stderr!r}"
    )


def test_post_tool_use_does_not_run_pytest() -> None:
    """Hook NAO invoca pytest (deployer nao testa codigo)."""
    proc = _run_hook(
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "packages/dfe-agent/src/foo.ts", "content": "x"},
        }
    )
    assert proc.returncode == 0
    assert "pytest" not in (proc.stdout + proc.stderr).lower(), (
        "post_tool_use do deployer NAO deve rodar pytest. "
        f"stdout+stderr: {(proc.stdout + proc.stderr)[:500]}"
    )


def test_post_tool_use_writes_log_event() -> None:
    _truncate_log()
    _run_hook(
        {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}}
    )
    log = LOG_PATH.read_text(encoding="utf-8")
    assert "deployer" in log, (
        f"post_tool_use deveria escrever log_event. Obtido:\n{log}"
    )