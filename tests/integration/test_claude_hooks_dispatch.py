"""Dispatch dos hooks por agent via ``.claude/hooks/dispatch.py``.

Sucede ``test_{dev,deployer,code_reviewer}_plugin_dispatch.py`` (plugin TS do
OpenCode). Roda o dispatcher em subprocess real com payloads no formato do
Claude Code (``agent_type`` so' existe dentro de subagent).
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
DISPATCH: Path = PROJECT_ROOT / ".claude" / "hooks" / "dispatch.py"


def _run(event: str, payload: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(DISPATCH), event],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        timeout=60,
        check=False,
    )


def _bash(command: str, agent_type: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"tool_name": "Bash", "tool_input": {"command": command}}
    if agent_type:
        payload["agent_type"] = agent_type
    return payload


def _write(tool: str, agent_type: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"tool_name": tool, "tool_input": {"file_path": "src/x.py"}}
    if agent_type:
        payload["agent_type"] = agent_type
    return payload


@pytest.mark.parametrize(
    "payload, expected",
    [
        # sessao principal = perfil dev
        (_bash("git push origin main"), 2),
        (_bash("gh pr create --fill"), 2),
        (_bash("pip install foo"), 2),
        (_bash("python -m src.collector --once"), 2),
        (_bash("npx tsx .claude/rag/summarize.ts -i t.jsonl"), 2),
        (_bash("pytest tests/unit -q"), 0),
        (_bash("python -m src.ragctl stats"), 0),
        (_bash("npx tsx .claude/rag/search.ts -q foo -a dev"), 0),
        (_bash("npx tsx .claude/rag/embed.ts --file a.md"), 0),
        (_write("Write"), 0),
        # subagents genericos herdam o perfil dev
        (_bash("pip install foo", "general-purpose"), 2),
        (_bash("git push", "Explore"), 2),
        # deployer
        (_bash("git push origin main", "deployer"), 0),
        (_bash("npm publish --access public", "deployer"), 0),
        (_bash("rm -rf src", "deployer"), 2),
        (_write("Edit", "deployer"), 2),
        # code-reviewer
        (_write("Edit", "code-reviewer"), 2),
        (_write("Write", "code-reviewer"), 2),
        (_bash("git log --oneline -3", "code-reviewer"), 0),
        (_bash("git commit -m x", "code-reviewer"), 2),
        # dfe-agent nao tem hooks
        (_bash("python -m src.query foo", "dfe-agent"), 0),
    ],
)
def test_pre_tool_use_dispatch(payload: dict[str, Any], expected: int) -> None:
    proc = _run("pre", payload)
    assert proc.returncode == expected, proc.stderr


def test_post_tool_use_ignores_non_write_tools() -> None:
    assert _run("post", {"tool_name": "Read", "tool_input": {"file_path": "src/x.py"}}).returncode == 0


def test_stop_without_edits_skips_pytest() -> None:
    proc = _run("stop", {"transcript_path": str(PROJECT_ROOT / "nao-existe.jsonl")})
    assert proc.returncode == 0
    assert "pytest" not in proc.stderr


def test_subagent_stop_only_runs_for_deployer() -> None:
    assert _run("subagent-stop", {"agent_type": "code-reviewer"}).returncode == 0
    assert _run("subagent-stop", {"agent_type": "deployer"}).returncode == 0


def test_invalid_payload_is_permissive() -> None:
    proc = subprocess.run(
        [sys.executable, str(DISPATCH), "pre"], input="nao-json", capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0


def _load_dispatch() -> ModuleType:
    spec = importlib.util.spec_from_file_location("dispatch_for_test", DISPATCH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_count_writes_only_in_current_turn(tmp_path: Path) -> None:
    """Conta Write/Edit desde o ultimo prompt real (tool_result nao zera)."""
    entries = [
        {"type": "user", "message": {"content": "faz X"}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Edit"}]}},
        {"type": "user", "message": {"content": "agora Y"}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Write"}, {"type": "tool_use", "name": "Read"}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "content": "ok"}]}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Edit"}]}},
    ]
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")
    assert _load_dispatch().count_writes_in_turn(str(transcript)) == 2


def test_resolve_agent_defaults_to_dev() -> None:
    mod = _load_dispatch()
    assert mod.resolve_agent({}) == "dev"
    assert mod.resolve_agent({"agent_type": "Plan"}) == "dev"
    assert mod.resolve_agent({"agent_type": "deployer"}) == "deployer"
