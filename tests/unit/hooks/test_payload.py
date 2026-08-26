"""Testes do helper `.opencode/hooks/_lib/payload.py` (PLAN_SPRINT10 C.1).

Sprint 12 (B12.1) moveu o helper de ``.claude/hooks/_lib/`` para
``.opencode/hooks/_lib/``. Suite cobre:

- `detect_active_agent` retorna slug explicito do payload.
- `detect_active_agent` cai para `DFE_ACTIVE_AGENT` env var.
- `detect_active_agent` cai para `hook_dir_name` se env ausente.
- `detect_active_agent` infere pelo session_id via `_AGENT_HINTS`.
- **Sprint 10 C.1**: slug `dev` e' reconhecido (sem falsos positivos com
  "developer", "device", "devotee" etc.).
- Helpers de extracao (`get_tool_name`, `get_tool_args`, `get_command`,
  `get_file_path`) normalizam entre formato Claude Code e OpenCode.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]
PAYLOAD_LIB: Path = PROJECT_ROOT / ".opencode" / "hooks" / "_lib" / "payload.py"


def _import_payload():
    import sys
    sys.path.insert(0, str(PROJECT_ROOT / ".opencode" / "hooks"))
    from _lib import payload as _p
    return _p


@pytest.fixture(scope="module")
def payload_mod():
    return _import_payload()


def test_payload_module_imports(payload_mod) -> None:
    """payload.py compila e exporta funcoes canonicas."""
    for name in (
        "read_payload",
        "detect_active_agent",
        "get_tool_name",
        "get_tool_args",
        "get_command",
        "get_file_path",
        "block",
        "allow",
        "log_event",
    ):
        assert hasattr(payload_mod, name), f"payload.py deve exportar `{name}`"


def test_detect_active_agent_from_payload_explicit(payload_mod) -> None:
    """Campo explicito `agent` no payload tem prioridade absoluta."""
    detected = payload_mod.detect_active_agent(
        {"agent": "dev"}, hook_dir_name="code-reviewer"
    )
    assert detected == "dev"


def test_detect_active_agent_from_env_var(
    payload_mod, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DFE_ACTIVE_AGENT", "dev")
    detected = payload_mod.detect_active_agent({})
    assert detected == "dev"


def test_detect_active_agent_from_hook_dir_name(
    payload_mod, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DFE_ACTIVE_AGENT", raising=False)
    detected = payload_mod.detect_active_agent({}, hook_dir_name="dev")
    assert detected == "dev"


def test_detect_active_agent_fallback_session(payload_mod) -> None:
    """Sprint 10 C.1: session_id contendo `-dev-` retorna slug `dev`."""
    detected = payload_mod.detect_active_agent(
        {"session_id": "01HQRS-dev-2026-08-26"}, hook_dir_name=None
    )
    assert detected == "dev"


def test_detect_active_agent_does_not_match_developer(payload_mod) -> None:
    """Heuristica NAO deve casar 'developer' como `dev` (lookhead negativo)."""
    detected = payload_mod.detect_active_agent(
        {"session_id": "sess-developer-001"}, hook_dir_name=None
    )
    assert detected != "dev", (
        f"Heuristica casou 'developer' como `dev` (lookhead falhou); "
        f"detectado={detected!r}"
    )


def test_detect_active_agent_does_not_match_device(payload_mod) -> None:
    """Heuristica NAO deve casar 'device' como `dev`."""
    detected = payload_mod.detect_active_agent(
        {"session_id": "sess-device-driver"}, hook_dir_name=None
    )
    assert detected != "dev"


def test_detect_active_agent_default_session(payload_mod) -> None:
    """Fallback final: retorna 'session' se nada bate."""
    detected = payload_mod.detect_active_agent(
        {"session_id": "01HQRS-abc-xyz"}, hook_dir_name=None
    )
    assert detected == "session"


def test_get_tool_name_normalizes_claude_vs_opencode(payload_mod) -> None:
    """Claude Code usa `tool_name`; OpenCode usa `tool`."""
    assert payload_mod.get_tool_name({"tool_name": "Bash"}) == "Bash"
    assert payload_mod.get_tool_name({"tool": "Bash"}) == "Bash"
    assert payload_mod.get_tool_name({}) == ""


def test_get_command_extracts_correctly(payload_mod) -> None:
    payload = {"tool_input": {"command": "ls -la"}}
    assert payload_mod.get_command(payload) == "ls -la"


def test_get_file_path_handles_multiple_keys(payload_mod) -> None:
    """`file_path`, `path` e `notebook_path` sao aceitos."""
    assert payload_mod.get_file_path({"tool_input": {"file_path": "a.py"}}) == "a.py"
    assert payload_mod.get_file_path({"tool_input": {"path": "b.py"}}) == "b.py"
    assert (
        payload_mod.get_file_path({"tool_input": {"notebook_path": "c.ipynb"}})
        == "c.ipynb"
    )
    assert payload_mod.get_file_path({"tool_input": {}}) == ""
