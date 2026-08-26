"""Testes anti-regressao de paths canonicos do harness (PLAN_SPRINT12 B12.1 / 1.1).

Sprint 12 unificou todo o harness em ``.opencode/``. Antes da unificacao:

- Hooks Python viviam em ``.claude/hooks/{dev,code-reviewer,_lib}/``.
- Scripts TS do RAG meta-cognitivo viviam em ``.claude/scripts/``.
- Knowledge e rag.db viviam em ``.claude/{knowledge,rag.db}``.

Apos a unificacao:

- Hooks Python vivem em ``.opencode/hooks/{dev,code-reviewer,_lib}/``.
- Scripts TS vivem em ``.opencode/rag/*.ts`` (com ``lib/`` subordinado).
- Knowledge e rag.db vivem em ``.opencode/rag/{knowledge,rag.db}``.

Este modulo protege contra regressao de paths canonicos. Cada teste
carrega o modulo canonico diretamente do novo path e valida:

- ``PROJECT_ROOT`` resolve para a raiz do DFe-Agent (nao vira
  ``.opencode/`` ou ``.claude/``).
- Diretorios de saida (knowledge, scripts, log) apontam para os novos
  paths em ``.opencode/rag/`` ou ``<PROJECT_ROOT>/storage``.

Lembrete: ``_lib/learning.py::PROJECT_ROOT`` usa
``Path(__file__).resolve().parents[3]``. Antes da unificacao o arquivo
morava em ``.claude/hooks/_lib/`` (3 niveis ate a raiz); agora mora em
``.opencode/hooks/_lib/`` (mesma profundidade). A profundidade
permanece 3 niveis; o teste ``test_*_project_root_resolves_to_dfe_agent_root``
valida que o off-by-one nao volta.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]


def _load(module_relpath: str, module_name: str) -> object:
    """Carrega modulo Python de path absoluto via ``importlib``.

    Args:
        module_relpath: path relativo a ``PROJECT_ROOT`` (ex.:
            ``".opencode/hooks/_lib/learning.py"``).
        module_name: nome sintetico para o modulo carregado.
    """
    script = PROJECT_ROOT / module_relpath
    assert script.exists(), (
        f"Modulo canonico esperado em {script}; nao encontrado. "
        f"Verifique se a unificacao Sprint 12 foi aplicada."
    )
    spec = importlib.util.spec_from_file_location(module_name, script)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _project_root_from(mod: object) -> Path:
    """Retorna ``PROJECT_ROOT`` do modulo carregado (deve ser ancestor)."""
    return mod.PROJECT_ROOT  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Anti-regressao: PROJECT_ROOT permanece na raiz do DFe-Agent
# ---------------------------------------------------------------------------


def test_learning_project_root_resolves_to_dfe_agent_root() -> None:
    """``learning.PROJECT_ROOT`` nao pode virar ``.opencode`` (off-by-one).

    Bug pre-Sprint 11 (``learning.py:37`` usava ``parents[2]``): resolvia
    para ``.claude/`` em vez de DFe-Agent root, gerando artefatos em
    ``.claude/.claude/knowledge/`` e ``.claude/storage/agent_hooks.log``.
    Sprint 11 corrigiu para ``parents[3]``. Sprint 12 mantem 3 niveis
    de profundidade (``.opencode/hooks/_lib/``).
    """
    mod = _load(".opencode/hooks/_lib/learning.py", "learning_sprint12")
    proj = _project_root_from(mod)
    assert proj.name != ".opencode", (
        f"PROJECT_ROOT nao deve ser .opencode/ (off-by-one). Obtido: {proj}"
    )
    assert proj.name != ".claude", (
        f"PROJECT_ROOT nao deve ser .claude/ (regressao). Obtido: {proj}"
    )
    learning_file = PROJECT_ROOT / ".opencode" / "hooks" / "_lib" / "learning.py"
    assert learning_file.is_relative_to(proj), (
        f"PROJECT_ROOT={proj} deve ser ancestor de {learning_file}"
    )


def test_payload_project_root_resolves_to_dfe_agent_root() -> None:
    """``payload.PROJECT_ROOT`` nao pode virar ``.opencode`` (off-by-one)."""
    mod = _load(".opencode/hooks/_lib/payload.py", "payload_sprint12")
    proj = _project_root_from(mod)
    assert proj.name not in (".opencode", ".claude"), (
        f"PROJECT_ROOT nao deve ser .opencode/ nem .claude/; obtido: {proj}"
    )


def test_test_runner_project_root_resolves_to_dfe_agent_root() -> None:
    """``test_runner.PROJECT_ROOT`` nao pode virar ``.opencode`` (off-by-one)."""
    mod = _load(
        ".opencode/hooks/_lib/test_runner.py", "test_runner_sprint12"
    )
    proj = _project_root_from(mod)
    assert proj.name not in (".opencode", ".claude"), (
        f"PROJECT_ROOT nao deve ser .opencode/ nem .claude/; obtido: {proj}"
    )


# ---------------------------------------------------------------------------
# Anti-regressao: diretorios de saida apontam para .opencode/rag/
# ---------------------------------------------------------------------------


def test_knowledge_dir_after_migration_is_opencode_rag_knowledge() -> None:
    """``_knowledge_dir()`` deve apontar para ``<PROJECT_ROOT>/.opencode/rag/knowledge``.

    Antes da unificacao (Sprints 1-11) era ``.claude/knowledge``.
    Sprint 12 unificou em ``.opencode/rag/knowledge``.
    """
    mod = _load(".opencode/hooks/_lib/learning.py", "learning_for_kdir")
    knowledge = mod._knowledge_dir()  # type: ignore[attr-defined]
    expected = mod.PROJECT_ROOT / ".opencode" / "rag" / "knowledge"  # type: ignore[attr-defined]
    assert knowledge == expected, (
        f"_knowledge_dir()={knowledge} deve ser igual a "
        f"PROJECT_ROOT/.opencode/rag/knowledge={expected}"
    )


def test_log_path_after_migration_is_storage_root() -> None:
    """``LOG_PATH`` continua em ``<PROJECT_ROOT>/storage/agent_hooks.log``.

    Path raiz NAO muda na unificacao (permanece fora de ``.opencode/``):
    o log e' compartilhado com o plugin TS e ja' estava em ``<root>/storage/``.
    """
    mod = _load(".opencode/hooks/_lib/learning.py", "learning_for_log")
    expected = mod.PROJECT_ROOT / "storage" / "agent_hooks.log"  # type: ignore[attr-defined]
    assert mod.LOG_PATH == expected, (  # type: ignore[attr-defined]
        f"LOG_PATH={mod.LOG_PATH} deve ser igual a "  # type: ignore[attr-defined]
        f"PROJECT_ROOT/storage/agent_hooks.log={expected}"
    )


# ---------------------------------------------------------------------------
# Anti-regressao: novos paths em constantes exportadas
# ---------------------------------------------------------------------------


def test_knowledge_dir_uses_opencode_rag_path() -> None:
    """Constante exportada ``KNOWLEDGE_DIR`` deve apontar para ``.opencode/rag/knowledge``."""
    mod = _load(".opencode/hooks/_lib/learning.py", "learning_for_kconst")
    expected = mod.PROJECT_ROOT / ".opencode" / "rag" / "knowledge"  # type: ignore[attr-defined]
    assert mod.KNOWLEDGE_DIR == expected, (  # type: ignore[attr-defined]
        f"KNOWLEDGE_DIR={mod.KNOWLEDGE_DIR} deve ser igual a "  # type: ignore[attr-defined]
        f"PROJECT_ROOT/.opencode/rag/knowledge={expected}"
    )


def test_scripts_dir_uses_opencode_rag_path() -> None:
    """Constante exportada ``SCRIPTS_DIR`` deve apontar para ``.opencode/rag/``."""
    mod = _load(".opencode/hooks/_lib/learning.py", "learning_for_sconst")
    expected = mod.PROJECT_ROOT / ".opencode" / "rag"  # type: ignore[attr-defined]
    assert mod.SCRIPTS_DIR == expected, (  # type: ignore[attr-defined]
        f"SCRIPTS_DIR={mod.SCRIPTS_DIR} deve ser igual a "  # type: ignore[attr-defined]
        f"PROJECT_ROOT/.opencode/rag={expected}"
    )


def test_spawn_summarize_invokes_opencode_rag_summarize(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``spawn_summarize_then_embed`` deve invocar ``.opencode/rag/summarize.ts``.

    Antes (Sprints 1-11): ``.claude/scripts/summarize.ts``.
    Apos (Sprint 12): ``.opencode/rag/summarize.ts``.

    Estrategia: carrega o modulo com ``PROJECT_ROOT`` apontando para
    ``tmp_path`` (isolamento), stub ``subprocess.run`` e ``subprocess.Popen``
    via ``monkeypatch``, captura ``args``, valida que inclui o novo path.
    """
    from unittest.mock import MagicMock

    mod = _load(".opencode/hooks/_lib/learning.py", "learning_for_spawn")
    monkeypatch.setattr(mod, "PROJECT_ROOT", tmp_path)
    (tmp_path / ".opencode" / "rag" / "knowledge").mkdir(parents=True, exist_ok=True)

    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        '{"role":"assistant","content":"' + ("x" * 100) + '"}\n',
        encoding="utf-8",
    )

    summarize_proc = MagicMock()
    summarize_proc.returncode = 0
    summarize_proc.stdout = b"# Aprendizado\nconteudo\n"
    summarize_proc.stderr = b""

    run_calls: list[list[str]] = []

    def fake_run(args: list[str], **_kw: object) -> MagicMock:
        run_calls.append([str(a) for a in args])
        return summarize_proc

    popen_calls: list[list[str]] = []

    def fake_popen(args: list[str], **_kw: object) -> MagicMock:
        popen_calls.append([str(a) for a in args])
        return MagicMock()

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    monkeypatch.setattr(mod.subprocess, "Popen", fake_popen)

    rc = mod.spawn_summarize_then_embed(  # type: ignore[attr-defined]
        transcript, "dev", "sess-spawn-sprint12-unique"
    )
    assert rc == 0

    assert len(run_calls) == 1, (
        f"summarize deveria ser chamado 1x; obtido {len(run_calls)}"
    )
    summarize_argv_str = " ".join(run_calls[0])
    assert ".opencode/rag/summarize.ts" in summarize_argv_str, (
        f"summarize_args deve conter '.opencode/rag/summarize.ts' "
        f"(Sprint 12); argv={run_calls[0]}"
    )
    assert ".claude/scripts/" not in summarize_argv_str, (
        f"summarize_args NAO deve conter '.claude/scripts/' "
        f"(path legado); argv={run_calls[0]}"
    )

    assert len(popen_calls) == 1, (
        f"embed deveria ser spawn 1x; obtido {len(popen_calls)}"
    )
    embed_argv_str = " ".join(popen_calls[0])
    assert ".opencode/rag/embed.ts" in embed_argv_str, (
        f"embed_args deve conter '.opencode/rag/embed.ts' "
        f"(Sprint 12); argv={popen_calls[0]}"
    )
    assert ".claude/scripts/" not in embed_argv_str, (
        f"embed_args NAO deve conter '.claude/scripts/' "
        f"(path legado); argv={popen_calls[0]}"
    )


# ---------------------------------------------------------------------------
# Smoke: novos paths dos hooks existem
# ---------------------------------------------------------------------------


def test_opencode_hooks_dev_dir_exists() -> None:
    """Diretorio canonico ``.opencode/hooks/dev/`` deve existir."""
    dev_dir = PROJECT_ROOT / ".opencode" / "hooks" / "dev"
    assert dev_dir.is_dir(), f"{dev_dir} nao existe (unificacao incompleta)"


def test_opencode_hooks_code_reviewer_dir_exists() -> None:
    """Diretorio canonico ``.opencode/hooks/code-reviewer/`` deve existir."""
    cr_dir = PROJECT_ROOT / ".opencode" / "hooks" / "code-reviewer"
    assert cr_dir.is_dir(), f"{cr_dir} nao existe (unificacao incompleta)"


def test_opencode_hooks_lib_dir_exists() -> None:
    """Diretorio canonico ``.opencode/hooks/_lib/`` deve existir."""
    lib_dir = PROJECT_ROOT / ".opencode" / "hooks" / "_lib"
    assert lib_dir.is_dir(), f"{lib_dir} nao existe (unificacao incompleta)"
