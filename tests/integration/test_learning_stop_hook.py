"""Testes de integracao do pipeline ``stop.py -> learning`` (PLAN_SPRINT11 C + Sprint 12 B12.1).

Cobre o hook canonico ``dev/stop.py`` (unico hook de stop ativo apos
Sprint 11; os 3 hooks legacy — backend-engineer, ml-engineer,
prompt-engineer — foram removidos em Sprint 11 C.2).

Cada hook deve:

1. Rodar pytest (gate de qualidade existente).
2. Se pytest passar E o payload contiver ``tool_writes_count > 0``: chamar
   ``learning.spawn_summarize_then_embed`` com ``(transcript_path,
   agent_slug, session_id)``.
3. Se pytest falhar: NAO chamar learning (gate de qualidade).
4. Se payload NAO contiver ``tool_writes_count`` (ou for zero): NAO chamar
   learning (escopo = so' implementacoes).
5. Idempotencia: 2 chamadas com mesmo ``(agent, session)`` => 2a nao chama
   learning.

> **Sprint 12 (B12.1)**: hook movido de ``.claude/hooks/dev/`` para
> ``.opencode/hooks/dev/``. Knowledge/scripts migraram para
> ``.opencode/rag/{knowledge,}``.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest


PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
AGENT_DIR: str = "dev"


def _load_hook_module(hook_name: str, module_name: str):
    """Carrega ``.opencode/hooks/dev/<hook_name>.py`` como modulo isolado."""
    script = PROJECT_ROOT / ".opencode" / "hooks" / AGENT_DIR / hook_name
    spec = importlib.util.spec_from_file_location(module_name, script)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_payload(session_id: str, tool_writes_count: int) -> str:
    """Constroi payload JSON igual ao que o plugin TS envia no stop event."""
    return json.dumps(
        {
            "session_id": session_id,
            "agent": AGENT_DIR,
            "tool_writes_count": tool_writes_count,
        }
    )


@pytest.fixture
def transcript_file(tmp_path: Path) -> Path:
    """Transcript JSONL valido usado pelo helper."""
    path = tmp_path / "transcript.jsonl"
    path.write_text(
        json.dumps({"role": "assistant", "content": "x" * 100}) + "\n",
        encoding="utf-8",
    )
    return path


def test_dev_stop_runs_learning_after_pytest_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, transcript_file: Path
) -> None:
    """pytest rc=0 + writes > 0 => learning helper e' chamado 1x."""
    mod = _load_hook_module("stop.py", "dev_stop_pass")

    monkeypatch.setattr(mod.learning, "PROJECT_ROOT", tmp_path)
    (tmp_path / ".opencode" / "rag" / "knowledge").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(mod, "read_payload", lambda: {
        "session_id": "sess-pass-1",
        "agent": AGENT_DIR,
        "tool_writes_count": 3,
        "transcript_path": str(transcript_file),
    })

    monkeypatch.setattr(mod, "run_pytest", lambda *_a, **_kw: (0, "ok"))

    learning_calls: list[tuple[Path, str, str]] = []

    def fake_summarize_then_embed(
        transcript: Path, agent_slug: str, session_id: str
    ) -> int:
        learning_calls.append((transcript, agent_slug, session_id))
        return 0

    monkeypatch.setattr(
        mod.learning, "spawn_summarize_then_embed", fake_summarize_then_embed
    )

    rc = mod.main()
    assert rc == 0
    assert len(learning_calls) == 1, (
        f"Esperava 1 chamada a learning; obtido {len(learning_calls)}"
    )
    assert learning_calls[0][1] == AGENT_DIR
    assert learning_calls[0][2] == "sess-pass-1"


def test_dev_stop_blocks_when_pytest_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, transcript_file: Path
) -> None:
    """pytest rc != 0 => learning NAO e' chamado (gate de qualidade)."""
    mod = _load_hook_module("stop.py", "dev_stop_fail")
    monkeypatch.setattr(mod.learning, "PROJECT_ROOT", tmp_path)
    (tmp_path / ".opencode" / "rag" / "knowledge").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(mod, "read_payload", lambda: {
        "session_id": "sess-fail-1",
        "agent": AGENT_DIR,
        "tool_writes_count": 5,
        "transcript_path": str(transcript_file),
    })

    monkeypatch.setattr(mod, "run_pytest", lambda *_a, **_kw: (1, "FAIL"))

    learning_calls: list[tuple] = []

    def fake_summarize_then_embed(*_a: object, **_kw: object) -> int:
        learning_calls.append(True)
        return 0

    monkeypatch.setattr(
        mod.learning, "spawn_summarize_then_embed", fake_summarize_then_embed
    )

    with pytest.raises(SystemExit) as exc_info:
        mod.main()
    assert exc_info.value.code == 2, (
        f"pytest falhou => hook deve bloquear com exit 2; obtido {exc_info.value.code}"
    )
    assert learning_calls == [], (
        f"learning NAO deveria ser chamado quando pytest falha; obtido {learning_calls}"
    )


def test_dev_stop_skips_learning_when_no_edits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, transcript_file: Path
) -> None:
    """payload sem writes (>0) => learning NAO e' chamado (escopo = so' impl)."""
    mod = _load_hook_module("stop.py", "dev_stop_no_edits")
    monkeypatch.setattr(mod.learning, "PROJECT_ROOT", tmp_path)
    (tmp_path / ".opencode" / "rag" / "knowledge").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(mod, "read_payload", lambda: {
        "session_id": "sess-no-edits",
        "agent": AGENT_DIR,
        "tool_writes_count": 0,
        "transcript_path": str(transcript_file),
    })

    monkeypatch.setattr(mod, "run_pytest", lambda *_a, **_kw: (0, "ok"))

    learning_calls: list[tuple] = []

    def fake_summarize_then_embed(*_a: object, **_kw: object) -> int:
        learning_calls.append(True)
        return 0

    monkeypatch.setattr(
        mod.learning, "spawn_summarize_then_embed", fake_summarize_then_embed
    )

    rc = mod.main()
    assert rc == 0
    assert learning_calls == [], (
        f"learning NAO deveria ser chamado sem edits; obtido {learning_calls}"
    )


def test_dev_stop_skips_learning_when_writes_field_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, transcript_file: Path
) -> None:
    """payload sem campo tool_writes_count => learning NAO e' chamado."""
    mod = _load_hook_module("stop.py", "dev_stop_no_writes_field")
    monkeypatch.setattr(mod.learning, "PROJECT_ROOT", tmp_path)
    (tmp_path / ".opencode" / "rag" / "knowledge").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(mod, "read_payload", lambda: {
        "session_id": "sess-no-field",
        "agent": AGENT_DIR,
        "transcript_path": str(transcript_file),
    })

    monkeypatch.setattr(mod, "run_pytest", lambda *_a, **_kw: (0, "ok"))

    learning_calls: list[tuple] = []

    def fake_summarize_then_embed(*_a: object, **_kw: object) -> int:
        learning_calls.append(True)
        return 0

    monkeypatch.setattr(
        mod.learning, "spawn_summarize_then_embed", fake_summarize_then_embed
    )

    rc = mod.main()
    assert rc == 0
    assert learning_calls == []


# ---------------------------------------------------------------------------
# Idempotencia composta
# ---------------------------------------------------------------------------


def test_stop_idempotent_per_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, transcript_file: Path
) -> None:
    """2 chamadas com mesmo session_id => 2a no-op (marker composto).

    NAO mockamos ``spawn_summarize_then_embed``: deixamos o real rodar
    e verificamos que o marker composto garante idempotencia end-to-end.
    """
    mod = _load_hook_module("stop.py", "dev_stop_idem")
    monkeypatch.setattr(mod.learning, "PROJECT_ROOT", tmp_path)
    (tmp_path / ".opencode" / "rag" / "knowledge").mkdir(parents=True, exist_ok=True)

    summarize_calls: list[int] = []

    def fake_run(*_a: object, **_kw: object) -> MagicMock:
        summarize_calls.append(1)
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = b"# ok\nc\n"
        proc.stderr = b""
        return proc

    monkeypatch.setattr(mod.learning.subprocess, "run", fake_run)
    monkeypatch.setattr(
        mod.learning.subprocess, "Popen", lambda *a, **kw: MagicMock()
    )
    monkeypatch.setattr(mod, "read_payload", lambda: {
        "session_id": "sess-idem",
        "agent": AGENT_DIR,
        "tool_writes_count": 1,
        "transcript_path": str(transcript_file),
    })
    monkeypatch.setattr(mod, "run_pytest", lambda *_a, **_kw: (0, "ok"))

    rc1 = mod.main()
    rc2 = mod.main()
    assert rc1 == 0
    assert rc2 == 0
    assert len(summarize_calls) == 1, (
        f"Esperava 1 chamada a summarize (idempotente); obtido {len(summarize_calls)}"
    )


def test_stop_different_sessions_each_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, transcript_file: Path
) -> None:
    """Sessoes diferentes do mesmo agent NAO sao colapsadas."""
    mod = _load_hook_module("stop.py", "dev_stop_distinct")
    monkeypatch.setattr(mod.learning, "PROJECT_ROOT", tmp_path)
    (tmp_path / ".opencode" / "rag" / "knowledge").mkdir(parents=True, exist_ok=True)

    learning_calls: list[tuple] = []

    session_counter = {"n": 0}

    def fake_payload() -> dict:
        session_counter["n"] += 1
        return {
            "session_id": f"sess-distinct-{session_counter['n']}",
            "agent": AGENT_DIR,
            "tool_writes_count": 1,
            "transcript_path": str(transcript_file),
        }

    def fake_summarize_then_embed(
        transcript: Path, agent_slug: str, session_id: str
    ) -> int:
        learning_calls.append((transcript, agent_slug, session_id))
        return 0

    monkeypatch.setattr(mod, "read_payload", fake_payload)
    monkeypatch.setattr(mod, "run_pytest", lambda *_a, **_kw: (0, "ok"))
    monkeypatch.setattr(
        mod.learning, "spawn_summarize_then_embed", fake_summarize_then_embed
    )

    rc1 = mod.main()
    rc2 = mod.main()
    assert rc1 == 0
    assert rc2 == 0
    assert len(learning_calls) == 2, (
        f"2 sessoes distintas -> 2 chamadas; obtido {len(learning_calls)}"
    )
    assert learning_calls[0][2] != learning_calls[1][2]
