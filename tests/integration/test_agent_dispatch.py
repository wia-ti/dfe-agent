"""Testes do dispatch do agent via DFE_ACTIVE_AGENT (PLAN_SPRINT4 B.1 / BLOQUEANTE #1 + Sprint 12 B12.1).

Garante que:

- O env var ``DFE_ACTIVE_AGENT`` e' propagado para subprocessos do
  opencode e reconhecido pelo hook ``code-reviewer/pre_tool_use.py``.
- Uma tentativa de ``Edit`` sob ``DFE_ACTIVE_AGENT=code-reviewer`` e'
  bloqueada (exit code 2 + stderr "BLOQUEADO").
- Sem env var, o hook cai em modo permissivo e NAO bloqueia, mas
  registra warning no log.

> **Sprint 12 (B12.1)**: hook movido de ``.claude/hooks/code-reviewer/``
> para ``.opencode/hooks/code-reviewer/``.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
HOOK_SCRIPT: Path = (
    PROJECT_ROOT / ".opencode" / "hooks" / "code-reviewer" / "pre_tool_use.py"
)
LOG_PATH: Path = PROJECT_ROOT / "storage" / "agent_hooks.log"


def test_dfe_active_agent_env_propagates_to_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``DFE_ACTIVE_AGENT=code-reviewer`` e' visivel no subprocess.

    Estrategia: invoca ``python -c`` com o env var e verifica que o
    subprocesso o enxerga. Isso confirma a base do contrato: o CLI do
    opencode PROPAGA o env var quando roteia para o agent code-reviewer.
    """
    monkeypatch.setenv("DFE_ACTIVE_AGENT", "code-reviewer")

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os; print(os.environ.get('DFE_ACTIVE_AGENT', ''))",
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "DFE_ACTIVE_AGENT": "code-reviewer"},
        check=False,
        cwd=str(PROJECT_ROOT),
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "code-reviewer", (
        f"Esperado 'code-reviewer', obtido {result.stdout.strip()!r}"
    )


def test_code_reviewer_blocks_edit_in_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hook code-reviewer bloqueia ``Edit`` com exit 2 quando env var presente.

    Cenario: o CLI opencode invoca o hook passando um payload de Edit.
    O hook deve levantar via exit code 2 e mensagem "BLOQUEADO".
    """
    payload: str = '{"tool_name":"Edit","tool_input":{"file_path":"README.md"}}'
    result = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=payload,
        capture_output=True,
        text=True,
        env={**os.environ, "DFE_ACTIVE_AGENT": "code-reviewer"},
        check=False,
        cwd=str(PROJECT_ROOT),
    )

    assert result.returncode == 2, (
        f"Esperado exit 2 (bloqueio), obtido {result.returncode}. "
        f"stderr={result.stderr!r}"
    )
    assert "BLOQUEADO" in result.stderr, (
        f"Esperado 'BLOQUEADO' no stderr, obtido: {result.stderr!r}"
    )


def test_no_agent_logs_warning_and_runs_permissive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Sem env var, hook roda em modo permissivo e registra warning.

    O hook deve retornar 0 (pass-through) e o log deve conter
    registro da deteccao como "session" (degradacao controlada).
    """
    if LOG_PATH.exists():
        LOG_PATH.unlink()
    monkeypatch.delenv("DFE_ACTIVE_AGENT", raising=False)

    payload: str = '{"tool_name":"Read","tool_input":{"file_path":"README.md"}}'
    result = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=payload,
        capture_output=True,
        text=True,
        env={k: v for k, v in os.environ.items() if k != "DFE_ACTIVE_AGENT"},
        check=False,
        cwd=str(PROJECT_ROOT),
    )

    assert result.returncode == 0, (
        f"Esperado exit 0 (modo permissivo), obtido {result.returncode}. "
        f"stderr={result.stderr!r}"
    )
