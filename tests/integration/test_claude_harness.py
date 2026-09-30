"""Gate estrutural do harness Claude Code (substitui o harness OpenCode).

Sucede ``test_unified_harness.py``, ``test_no_legacy_agents.py``,
``test_opencode_config.py``, ``test_gitignore_opencode.py`` e
``test_agent_hooks_plugin_loads.py`` (todos especificos do OpenCode).

Cobre:
- O harness OpenCode (``.opencode/``, ``opencode.json``) foi removido.
- ``.claude/`` tem exatamente os agents, commands, skills e rules canonicos.
- Hooks Python e scripts do RAG meta-cognitivo existem e compilam.
- ``.claude/settings.json`` liga os 4 eventos ao ``dispatch.py``.
- Nenhum arquivo ativo do harness cita ``.opencode/`` (historico em
  ``.claude/rag/knowledge/`` e AGENTS.md e' permitido).
- Slugs legacy nao voltam (payload/test_runner/knowledge).
"""
from __future__ import annotations

import importlib.util
import json
import py_compile
import re
from pathlib import Path
from types import ModuleType

import pytest

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
HARNESS: Path = PROJECT_ROOT / ".claude"
LEGACY_SLUGS: frozenset[str] = frozenset(
    {"backend-engineer", "ml-engineer", "prompt-engineer", "qa-engineer", "build", "plan"}
)


def _load(rel: str, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, HARNESS / rel)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- harness OpenCode removido ------------------------------------------------


def test_opencode_harness_removed() -> None:
    assert not (PROJECT_ROOT / ".opencode").exists(), ".opencode/ deve ter sido removido."
    assert not (PROJECT_ROOT / "opencode.json").exists(), "opencode.json deve ter sido removido."


def test_claude_md_exists() -> None:
    assert (PROJECT_ROOT / "CLAUDE.md").is_file()


# --- inventario canonico -------------------------------------------------------


def test_only_canonical_agents() -> None:
    names = {p.stem for p in (HARNESS / "agents").glob("*.md")}
    assert names == {"code-reviewer", "deployer", "dfe-agent"}


def test_only_canonical_commands() -> None:
    names = {p.stem for p in (HARNESS / "commands").glob("*.md")}
    assert names == {"feature", "bug", "duvida"}


def test_only_canonical_skills() -> None:
    names = {p.parent.name for p in (HARNESS / "skills").glob("*/SKILL.md")}
    assert names == {"deploy", "dfe-fiscal"}


def test_rules_count_is_5() -> None:
    names = {p.stem for p in (HARNESS / "rules").glob("*.md")}
    assert names == {"seguranca", "convencoes-gerais", "src", "tests", "dfe-rules"}


@pytest.mark.parametrize("rule, glob", [("src", "src/**/*.py"), ("tests", "tests/**/*.py")])
def test_path_scoped_rules(rule: str, glob: str) -> None:
    text = (HARNESS / "rules" / f"{rule}.md").read_text(encoding="utf-8")
    assert re.search(rf"^paths:\s*{re.escape(glob)}\s*$", text, re.MULTILINE)


HOOK_SCRIPTS: tuple[str, ...] = (
    "dispatch.py",
    "domain_guard.py",
    "allowed_domains.py",
    "_lib/payload.py",
    "_lib/learning.py",
    "_lib/test_runner.py",
    "dev/pre_tool_use.py",
    "dev/post_tool_use.py",
    "dev/stop.py",
    "code-reviewer/pre_tool_use.py",
    "code-reviewer/pre_tool_use_bash.py",
    "deployer/pre_tool_use.py",
    "deployer/post_tool_use.py",
    "deployer/stop.py",
)


@pytest.mark.parametrize("rel", HOOK_SCRIPTS)
def test_hook_script_exists_and_compiles(rel: str) -> None:
    path = HARNESS / "hooks" / rel
    assert path.is_file(), f"{path} ausente"
    py_compile.compile(str(path), doraise=True)


def test_rag_has_5_scripts_and_4_lib() -> None:
    scripts = {p.name for p in (HARNESS / "rag").glob("*.ts")}
    libs = {p.name for p in (HARNESS / "rag" / "lib").glob("*.ts")}
    assert scripts == {"embed.ts", "init_db.ts", "search.ts", "smoke_test.ts", "summarize.ts"}
    assert libs == {"chunker.ts", "classifier.ts", "db.ts", "embedder.ts"}
    assert (HARNESS / "rag" / "schema.sql").is_file()


# --- settings.json -------------------------------------------------------------


@pytest.mark.parametrize(
    "event, arg",
    [("PreToolUse", "pre"), ("PostToolUse", "post"), ("Stop", "stop"), ("SubagentStop", "subagent-stop")],
)
def test_settings_wires_event_to_dispatcher(event: str, arg: str) -> None:
    settings = json.loads((HARNESS / "settings.json").read_text(encoding="utf-8"))
    commands = [h["command"] for group in settings["hooks"][event] for h in group["hooks"]]
    assert any(".claude/hooks/dispatch.py" in c and c.endswith(f" {arg}") for c in commands), commands


def test_gitignore_covers_local_artifacts() -> None:
    text = (HARNESS / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("settings.local.json", "node_modules/", "rag/rag.db"):
        assert pattern in text


# --- sem referencias ativas ao OpenCode ----------------------------------------


def test_active_harness_files_do_not_reference_opencode() -> None:
    offenders: list[str] = []
    for path in HARNESS.rglob("*"):
        rel = path.relative_to(HARNESS).as_posix()
        if not path.is_file() or rel.startswith(("node_modules/", "rag/knowledge/")) or "__pycache__" in rel:
            continue
        if path.suffix not in {".md", ".py", ".ts", ".json", ".sql"}:
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"\.opencode/(agent|command|rules|skills|rag|plugin)\b", text):
            offenders.append(rel)
    assert not offenders, f"Arquivos ativos citando .opencode/: {offenders}"


def test_learning_helper_paths_use_claude_rag() -> None:
    mod = _load("hooks/_lib/learning.py", "learning_for_harness_test")
    assert mod.KNOWLEDGE_DIR == PROJECT_ROOT / ".claude" / "rag" / "knowledge"


# --- slugs legacy ---------------------------------------------------------------


def test_agent_hints_have_no_legacy() -> None:
    mod = _load("hooks/_lib/payload.py", "payload_for_harness_test")
    assert {slug for slug, _ in mod._AGENT_HINTS} == {"code-reviewer", "deployer", "dev"}


def test_dispatcher_profiles_are_canonical() -> None:
    mod = _load("hooks/dispatch.py", "dispatch_for_harness_test")
    assert set(mod.PROFILES) == {"code-reviewer", "deployer", "dev", "dfe-agent"}


def test_rag_knowledge_no_legacy_slugs() -> None:
    offenders = [
        p.name
        for p in (HARNESS / "rag" / "knowledge").glob("*.md")
        if any(re.match(rf"^\d{{4}}-\d{{2}}-\d{{2}}-{re.escape(s)}(-|\.md$)", p.name) for s in LEGACY_SLUGS)
    ]
    assert not offenders, offenders
