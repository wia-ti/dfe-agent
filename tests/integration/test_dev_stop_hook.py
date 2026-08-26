"""Testes de integracao do hook `.opencode/hooks/dev/stop.py` (PLAN_SPRINT10 B.3 + Sprint 12 B12.1).

Cobre os 4 cenarios canonicos:

1. `pytest rc=0 + tool_writes_count > 0 + transcript existe` => learning
   helper e' chamado 1x com agent_slug=`dev`.
2. `pytest rc != 0` => block (exit 2) e learning NAO e' chamado.
3. `pytest rc=0 + tool_writes_count=0` => learning NAO e' chamado
   (escopo = so' implementacoes).
4. Idempotencia por (agent_slug, session_id) composto.

Implementado como subprocesso Python (padrao de
``tests/integration/test_learning_stop_hook.py``) para nao acoplar com
detalhes internos de import do hook.

> **Sprint 12 (B12.1)**: hook movido de ``.claude/hooks/dev/`` para
> ``.opencode/hooks/dev/``.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
HOOK_SCRIPT: Path = PROJECT_ROOT / ".opencode" / "hooks" / "dev" / "stop.py"


def _make_payload(
    session_id: str,
    tool_writes_count: int,
    transcript_path: str | None = None,
) -> str:
    p: dict[str, object] = {
        "session_id": session_id,
        "agent": "dev",
        "tool_writes_count": tool_writes_count,
    }
    if transcript_path:
        p["transcript_path"] = transcript_path
    return json.dumps(p)


def _make_fake_stdin(payload: str) -> object:
    class _FakeStdin:
        def isatty(self) -> bool:
            return False

        def read(self) -> str:
            return payload

    return _FakeStdin()


@pytest.fixture
def transcript_file(tmp_path: Path) -> Path:
    path: Path = tmp_path / "transcript.jsonl"
    path.write_text(
        json.dumps({"role": "assistant", "content": "x" * 200}) + "\n",
        encoding="utf-8",
    )
    return path


def _load_hook_module():
    """Carrega ``dev/stop.py`` em isolamento, similar a ``test_learning_stop_hook.py``."""
    spec = importlib.util.spec_from_file_location("dev_stop", HOOK_SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_stop_compiles() -> None:
    proc = subprocess_py_compile(HOOK_SCRIPT)
    assert proc == 0


def subprocess_py_compile(path: Path) -> int:
    import subprocess
    proc = subprocess.run(
        [sys.executable, "-m", "py_compile", str(path)],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(PROJECT_ROOT),
        timeout=15,
    )
    return proc.returncode


def test_stop_uses_dev_slug() -> None:
    """O modulo exporta AGENT_SLUG == 'dev'."""
    mod = _load_hook_module()
    assert mod.AGENT_SLUG == "dev"


def test_stop_runs_full_suite_not_subset(tmp_path: Path, monkeypatch) -> None:
    """Suites do `@dev` sao `['tests/']` (suite completa), NAO subset."""
    mod = _load_hook_module()
    captured: dict[str, object] = {}

    def fake_run_pytest(suites, timeout=120):
        captured["suites"] = list(suites)
        captured["timeout"] = timeout
        return 0, "[ok] fake pytest"

    monkeypatch.setattr(mod, "run_pytest", fake_run_pytest)
    monkeypatch.setattr(mod, "read_payload", lambda: {
        "session_id": "sess-1",
        "agent": "dev",
        "tool_writes_count": 0,
    })

    rc = mod.main()
    assert rc == 0
    assert captured["suites"] == ["tests/"], (
        f"@dev stop.py deve rodar suite completa `['tests/']`; "
        f"obtido {captured['suites']!r}"
    )


def test_stop_blocks_when_pytest_fails(tmp_path: Path, monkeypatch) -> None:
    """pytest rc != 0 => exit 2 (gate de qualidade)."""
    mod = _load_hook_module()
    learning_called: dict[str, int] = {"count": 0}

    def fake_run_pytest(suites, timeout=120):
        return 1, "[fail] pytest failure"

    def fake_spawn(*args, **kwargs):
        learning_called["count"] += 1
        return 0

    monkeypatch.setattr(mod, "run_pytest", fake_run_pytest)
    monkeypatch.setattr(mod.learning, "spawn_summarize_then_embed", fake_spawn)
    monkeypatch.setattr(mod, "read_payload", lambda: {
        "session_id": "sess-fail",
        "agent": "dev",
        "tool_writes_count": 5,
    })

    with pytest.raises(SystemExit) as exc_info:
        mod.main()
    assert exc_info.value.code == 2, (
        f"pytest falhou => exit 2 esperado; obtido {exc_info.value.code}"
    )
    assert learning_called["count"] == 0, (
        "learning NAO deve ser chamado quando pytest falha."
    )


def test_stop_skips_learning_when_no_edits(tmp_path: Path, monkeypatch) -> None:
    """tool_writes_count=0 => learning NAO e' chamado (escopo = so' impl)."""
    mod = _load_hook_module()
    learning_called: dict[str, int] = {"count": 0}

    def fake_run_pytest(suites, timeout=120):
        return 0, "[ok]"

    def fake_spawn(*args, **kwargs):
        learning_called["count"] += 1
        return 0

    monkeypatch.setattr(mod, "run_pytest", fake_run_pytest)
    monkeypatch.setattr(mod.learning, "spawn_summarize_then_embed", fake_spawn)
    monkeypatch.setattr(mod, "read_payload", lambda: {
        "session_id": "sess-no-edits",
        "agent": "dev",
        "tool_writes_count": 0,
    })

    rc = mod.main()
    assert rc == 0
    assert learning_called["count"] == 0


def test_stop_runs_learning_when_edits_and_pytest_passes(
    tmp_path: Path, monkeypatch, transcript_file: Path
) -> None:
    """Caminho feliz: pytest passa + writes > 0 + transcript existe => learning 1x."""
    mod = _load_hook_module()
    learning_calls: list[dict[str, object]] = []

    def fake_run_pytest(suites, timeout=120):
        return 0, "[ok]"

    def fake_spawn(transcript, agent, session):
        learning_calls.append({
            "transcript": str(transcript),
            "agent": agent,
            "session": session,
        })
        return 0

    monkeypatch.setattr(mod, "run_pytest", fake_run_pytest)
    monkeypatch.setattr(mod.learning, "spawn_summarize_then_embed", fake_spawn)
    monkeypatch.setattr(mod.learning, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(mod, "read_payload", lambda: {
        "session_id": "sess-pass",
        "agent": "dev",
        "tool_writes_count": 3,
        "transcript_path": str(transcript_file),
    })

    rc = mod.main()
    assert rc == 0
    assert len(learning_calls) == 1, (
        f"Esperado 1 chamada ao learning; obtido {len(learning_calls)}"
    )
    assert learning_calls[0]["agent"] == "dev"
    assert learning_calls[0]["session"] == "sess-pass"
