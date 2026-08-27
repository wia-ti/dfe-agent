"""Testes unit do hook ``.opencode/hooks/deployer/stop.py`` (PLAN_SPRINT18 / Task 2.3).

Cobre:

- Hook exit 0 (deploy e' acao atomica, sem pytest).
- Hook NAO invoca pytest.
- Hook NAO chama `learning.spawn_summarize_then_embed` (deployer NAO
  captura RAG; e' acao, nao aprendizado).

Diferenca vs `@dev/stop.py`:
- dev roda pytest geral + captura RAG se payload tem tool_writes_count > 0.
- deployer e' atomico: exit 0 sem pytest e sem RAG.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]
HOOK_SCRIPT: Path = PROJECT_ROOT / ".opencode" / "hooks" / "deployer" / "stop.py"


def _run_hook(payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, "DFE_ACTIVE_AGENT": "deployer"},
        check=False,
        cwd=str(PROJECT_ROOT),
        timeout=60,
    )
    return proc


def test_stop_exits_zero() -> None:
    proc = _run_hook({"session_id": "test-session-001"})
    assert proc.returncode == 0, (
        f"stop do deployer deveria exit 0 (sem pytest, sem RAG); "
        f"obtido rc={proc.returncode}, stderr={proc.stderr!r}"
    )


def test_stop_does_not_run_pytest() -> None:
    proc = _run_hook({"session_id": "test-session-002"})
    assert proc.returncode == 0
    combined = (proc.stdout + proc.stderr).lower()
    assert "pytest" not in combined, (
        "stop do deployer NAO deve rodar pytest. "
        f"stdout+stderr: {(proc.stdout + proc.stderr)[:500]}"
    )


def test_stop_does_not_capture_rag() -> None:
    """Deployer NAO captura RAG mesmo com tool_writes_count > 0."""
    proc = _run_hook(
        {
            "session_id": "test-session-003",
            "tool_writes_count": 5,
        }
    )
    assert proc.returncode == 0
    combined = (proc.stdout + proc.stderr).lower()
    # Nao deve invocar summarize nem embed
    assert "summarize" not in combined and "embed" not in combined, (
        "stop do deployer NAO deve capturar RAG. "
        f"stdout+stderr: {(proc.stdout + proc.stderr)[:500]}"
    )


def test_stop_handles_missing_session_id() -> None:
    """Stop deve exit 0 mesmo sem session_id (defesa)."""
    proc = _run_hook({})
    assert proc.returncode == 0, (
        f"stop deveria exit 0 sem payload; obtido rc={proc.returncode}, "
        f"stderr={proc.stderr!r}"
    )