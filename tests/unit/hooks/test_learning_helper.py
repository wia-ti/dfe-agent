"""Testes do helper ``.opencode/hooks/_lib/learning.py`` (PLAN_SPRINT8 B.2 + Sprint 12 B12.1).

Cobre:

- ``marker_path(agent_slug, session_id)``: canonicalizacao + saneamento de
  caracteres especiais (sem ``/``, ``\\``, espacos, etc.).
- ``should_record(agent_slug, session_id)``: idempotencia via marker composto
  ``(agent_slug, session_id)`` em vez de apenas ``agent_slug``.
- ``spawn_summarize_then_embed(transcript_path, agent_slug, session_id)``:
  invoca ``summarize.ts --stdout`` via subprocess sincronico; grava .md em
  ``.opencode/rag/knowledge/``; spawn ``embed.ts --file <md>`` em Popen detached.
- Comportamento em caminhos invalidos / transcript inexistente: skip + log.

> **Sprint 12 (B12.1)**: helper movido de ``.claude/hooks/_lib/`` para
> ``.opencode/hooks/_lib/``; knowledge/scripts migraram para
> ``.opencode/rag/{knowledge,}``.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest


PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]


def _load_learning_module() -> object:
    """Carrega ``.opencode/hooks/_lib/learning.py`` como modulo isolado."""
    script = PROJECT_ROOT / ".opencode" / "hooks" / "_lib" / "learning.py"
    spec = importlib.util.spec_from_file_location("learning_for_test", script)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def learning(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Carrega ``learning.py`` com ``PROJECT_ROOT`` apontando para ``tmp_path``.

    Cria tambem a estrutura ``.opencode/rag/knowledge/`` esperada pelo helper.
    """
    mod = _load_learning_module()
    monkeypatch.setattr(mod, "PROJECT_ROOT", tmp_path)
    knowledge = tmp_path / ".opencode" / "rag" / "knowledge"
    knowledge.mkdir(parents=True, exist_ok=True)
    return mod


def test_marker_path_normalizes_special_chars(learning: object) -> None:
    """Slug com caracteres nao-seguros vira nome de arquivo ASCII previsivel."""
    marker = learning.marker_path("Backend Engineer", "sess/abc 123")

    assert marker.parent == learning.PROJECT_ROOT / ".opencode" / "rag" / "knowledge"
    assert "/" not in marker.name
    assert "\\" not in marker.name
    assert " " not in marker.name
    assert marker.name.startswith("_pending-")
    assert marker.name.endswith(".md.lock")


def test_marker_path_handles_empty_strings(learning: object) -> None:
    """Slugs vazios viram ``agent`` / ``session`` (fallback canonico)."""
    marker = learning.marker_path("", "")
    assert marker.name == "_pending-agent-session.md.lock"


def test_marker_path_uses_compound_key(learning: object) -> None:
    """Marker e composto por ``(agent_slug, session_id)`` para evitar colisao
    entre sessoes diferentes do mesmo agent (PLAN_SPRINT8 B.5)."""
    m1 = learning.marker_path("backend-engineer", "sess-aaa")
    m2 = learning.marker_path("backend-engineer", "sess-bbb")
    assert m1 != m2, (
        f"Markers devem ser distintos por session_id; "
        f"obtido {m1} e {m2}"
    )


def test_should_record_returns_true_when_marker_absent(learning: object) -> None:
    """Marker ausente => deve gravar (retorna True)."""
    assert learning.should_record("backend-engineer", "sess-001") is True


def test_should_record_returns_false_when_marker_exists(learning: object) -> None:
    """Marker presente => NAO grava de novo (idempotente)."""
    marker = learning.marker_path("backend-engineer", "sess-002")
    marker.touch()
    assert learning.should_record("backend-engineer", "sess-002") is False


def test_spawn_skips_when_transcript_missing(
    learning: object,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Transcript inexistente => skip silencioso (nao levanta)."""
    missing = tmp_path / "nope.jsonl"
    popen_calls: list[list[str]] = []
    monkeypatch.setattr(
        learning.subprocess, "Popen", lambda *a, **kw: popen_calls.append([str(x) for x in a]) or MagicMock()
    )

    rc = learning.spawn_summarize_then_embed(missing, "backend-engineer", "sess-003")
    assert rc == 0
    assert popen_calls == [], "NAO deveria spawnar Popen sem transcript"
    err = capsys.readouterr().err
    assert "skip" in err.lower() or "transcript" in err.lower()


def test_spawn_invokes_npx_with_correct_args(
    learning: object,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """summarize.ts --stdout recebe --input, --agent; embed.ts --file recebe .md."""
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"role": "assistant", "content": "x" * 100}) + "\n",
        encoding="utf-8",
    )

    summarize_proc = MagicMock()
    summarize_proc.returncode = 0
    summarize_proc.stdout = b"# Aprendizado\nconteudo\n"
    summarize_proc.stderr = b""

    run_calls: list[tuple[list[str], dict]] = []
    popen_calls: list[list[str]] = []

    def fake_run(args: list[str], **kwargs: object) -> MagicMock:
        run_calls.append(([str(a) for a in args], kwargs))
        return summarize_proc

    def fake_popen(args: list[str], **kwargs: object) -> MagicMock:
        popen_calls.append([str(a) for a in args])
        return MagicMock()

    monkeypatch.setattr(learning.subprocess, "run", fake_run)
    monkeypatch.setattr(learning.subprocess, "Popen", fake_popen)

    rc = learning.spawn_summarize_then_embed(
        transcript, "backend-engineer", "sess-004"
    )
    assert rc == 0

    assert len(run_calls) == 1, (
        f"summarize deveria ser chamado 1x; obtido {len(run_calls)}"
    )
    summarize_argv = run_calls[0][0]
    assert "summarize.ts" in " ".join(summarize_argv)
    assert "--agent" in summarize_argv
    assert "backend-engineer" in summarize_argv
    assert "--stdout" in summarize_argv

    assert len(popen_calls) == 1, (
        f"embed deveria ser spawn 1x; obtido {len(popen_calls)}"
    )
    embed_argv = popen_calls[0]
    assert "embed.ts" in " ".join(embed_argv)
    assert "--file" in embed_argv


def test_spawn_writes_md_to_knowledge_dir(
    learning: object,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Apos summarize, escreve .md em ``.claude/knowledge/``."""
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("assistant content\n", encoding="utf-8")

    summarize_proc = MagicMock()
    summarize_proc.returncode = 0
    summarize_proc.stdout = b"# L\nbloco\n"
    summarize_proc.stderr = b""
    monkeypatch.setattr(learning.subprocess, "run", lambda *a, **kw: summarize_proc)
    monkeypatch.setattr(learning.subprocess, "Popen", lambda *a, **kw: MagicMock())

    learning.spawn_summarize_then_embed(transcript, "backend-engineer", "sess-005")

    knowledge = learning.PROJECT_ROOT / ".opencode" / "rag" / "knowledge"
    md_files = list(knowledge.glob("*.md"))
    assert any(f.name.startswith("_pending-") for f in md_files), (
        f"Esperava .md em {knowledge}; obtido {[f.name for f in md_files]}"
    )


def test_spawn_returns_zero_when_summarize_fails(
    learning: object,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """summarize com rc != 0 => spawn NAO chama embed; rc retornado = 0 (skip)."""
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("x" * 100 + "\n", encoding="utf-8")

    summarize_proc = MagicMock()
    summarize_proc.returncode = 1
    summarize_proc.stdout = b""
    summarize_proc.stderr = b"erro qualquer"

    popen_calls: list[list[str]] = []
    monkeypatch.setattr(learning.subprocess, "run", lambda *a, **kw: summarize_proc)
    monkeypatch.setattr(
        learning.subprocess, "Popen",
        lambda *a, **kw: popen_calls.append([str(x) for x in a]) or MagicMock(),
    )

    rc = learning.spawn_summarize_then_embed(transcript, "backend-engineer", "sess-006")
    assert rc == 0
    assert popen_calls == [], "NAO deveria spawnar embed quando summarize falha"


def test_spawn_creates_marker_only_on_success(
    learning: object,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Marker de idempotencia so' aparece apos summarize com sucesso."""
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("x" * 100 + "\n", encoding="utf-8")

    summarize_proc = MagicMock()
    summarize_proc.returncode = 0
    summarize_proc.stdout = b"# ok\nconteudo\n"
    summarize_proc.stderr = b""
    monkeypatch.setattr(learning.subprocess, "run", lambda *a, **kw: summarize_proc)
    monkeypatch.setattr(learning.subprocess, "Popen", lambda *a, **kw: MagicMock())

    marker_before = learning.marker_path("backend-engineer", "sess-007")
    assert not marker_before.exists()

    learning.spawn_summarize_then_embed(transcript, "backend-engineer", "sess-007")

    assert marker_before.exists(), (
        f"Esperava marker criado em sucesso; {marker_before} nao existe"
    )


def test_spawn_is_idempotent_per_session(
    learning: object,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """2 chamadas com mesmo (agent, session) => 2a invocacao e' no-op."""
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("x" * 100 + "\n", encoding="utf-8")

    summarize_proc = MagicMock()
    summarize_proc.returncode = 0
    summarize_proc.stdout = b"# ok\nc\n"
    summarize_proc.stderr = b""

    run_calls: list[int] = []
    popen_calls: list[int] = []

    monkeypatch.setattr(
        learning.subprocess, "run",
        lambda *a, **kw: run_calls.append(1) or summarize_proc,
    )
    monkeypatch.setattr(
        learning.subprocess, "Popen",
        lambda *a, **kw: popen_calls.append(1) or MagicMock(),
    )

    rc1 = learning.spawn_summarize_then_embed(
        transcript, "backend-engineer", "sess-008"
    )
    rc2 = learning.spawn_summarize_then_embed(
        transcript, "backend-engineer", "sess-008"
    )
    assert rc1 == 0
    assert rc2 == 0
    assert len(run_calls) == 1, (
        f"summarize deveria rodar 1x (idempotente); obtido {len(run_calls)}"
    )
    assert len(popen_calls) == 1, (
        f"embed deveria ser spawn 1x (idempotente); obtido {len(popen_calls)}"
    )


def test_spawn_different_sessions_each_call(
    learning: object,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Sessoes diferentes do mesmo agent NAO sao colapsadas (marker composto)."""
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("x" * 100 + "\n", encoding="utf-8")

    summarize_proc = MagicMock()
    summarize_proc.returncode = 0
    summarize_proc.stdout = b"# ok\nc\n"
    summarize_proc.stderr = b""

    run_calls: list[int] = []
    monkeypatch.setattr(
        learning.subprocess, "run",
        lambda *a, **kw: run_calls.append(1) or summarize_proc,
    )
    monkeypatch.setattr(
        learning.subprocess, "Popen",
        lambda *a, **kw: MagicMock(),
    )

    learning.spawn_summarize_then_embed(
        transcript, "backend-engineer", "sess-A"
    )
    learning.spawn_summarize_then_embed(
        transcript, "backend-engineer", "sess-B"
    )
    assert len(run_calls) == 2, (
        f"2 sessoes distintas -> 2 chamadas summarize; obtido {len(run_calls)}"
    )


def test_project_root_resolves_to_dfe_agent_root() -> None:
    """PROJECT_ROOT deve apontar para o DFe-Agent (PLAN_SPRINT11 B11.1 + Sprint 12 B12.1).

    Bug pre-Sprint 11: ``learning.py:37`` usava ``parents[2]`` em vez de
    ``parents[3]``, fazendo ``PROJECT_ROOT`` resolver para ``.claude/``.
    Consequencia: ``_knowledge_dir()`` virava ``.claude/.claude/knowledge/``
    e ``LOG_PATH`` virava ``.claude/storage/agent_hooks.log`` (artefatos
    reais visiveis no disco ate 2026-08-26). Sprint 12 unificou em
    ``.opencode/hooks/_lib/`` (mesma profundidade 3).
    """
    mod = _load_learning_module()
    # PROJECT_ROOT deve terminar com o diretorio raiz do DFe-Agent.
    # O nome exato do diretorio raiz varia (workspace do usuario);
    # o teste valida que o caminho NAO termina com ".claude" ou ".opencode".
    assert not mod.PROJECT_ROOT.name == ".claude", (
        f"PROJECT_ROOT nao deve ser .claude/ (off-by-one). "
        f"Obtido: {mod.PROJECT_ROOT}"
    )
    assert not mod.PROJECT_ROOT.name == ".opencode", (
        f"PROJECT_ROOT nao deve ser .opencode/ (off-by-one). "
        f"Obtido: {mod.PROJECT_ROOT}"
    )
    # Tambem: PROJECT_ROOT deve ser ancestor de ".opencode/hooks/_lib/learning.py".
    learning_file = PROJECT_ROOT / ".opencode" / "hooks" / "_lib" / "learning.py"
    assert learning_file.is_relative_to(mod.PROJECT_ROOT), (
        f"PROJECT_ROOT={mod.PROJECT_ROOT} deve ser ancestor de "
        f"{learning_file}"
    )


def test_knowledge_dir_is_canonical() -> None:
    """_knowledge_dir() deve retornar ``<PROJECT_ROOT>/.opencode/rag/knowledge``.

    Anti-regressao contra o bug off-by-one que criava
    ``.claude/.claude/knowledge/`` no disco. Sprint 12 (B12.1) unificou
    em ``.opencode/rag/knowledge``.
    """
    mod = _load_learning_module()
    knowledge = mod._knowledge_dir()
    expected = mod.PROJECT_ROOT / ".opencode" / "rag" / "knowledge"
    assert knowledge == expected, (
        f"_knowledge_dir()={knowledge} deve ser igual a "
        f"PROJECT_ROOT/.opencode/rag/knowledge={expected}"
    )


def test_log_path_is_storage_root() -> None:
    """LOG_PATH deve ser ``<PROJECT_ROOT>/storage/agent_hooks.log``.

    Path raiz NAO muda na unificacao Sprint 12: o log e' compartilhado
    com o plugin TS e ja' estava em ``<root>/storage/`` (permanece fora
    de ``.opencode/``).
    """
    mod = _load_learning_module()
    expected = mod.PROJECT_ROOT / "storage" / "agent_hooks.log"
    assert mod.LOG_PATH == expected, (
        f"LOG_PATH={mod.LOG_PATH} deve ser igual a "
        f"PROJECT_ROOT/storage/agent_hooks.log={expected}"
    )
