"""Testes de integracao do plugin TS para o agent code-reviewer (PLAN_SPRINT9 / I9.4 + D.1).

Cobre:

- O map ``AGENTS`` em ``.opencode/plugin/agent-hooks.ts`` contem o
  slug ``code-reviewer`` com os hooks corretos (``preToolUse`` +
  ``preToolUseBash``) e **sem** ``postToolUse`` / ``stop`` (read-only).
- O helper ``detectAgentFromSession`` retorna ``code-reviewer`` quando
  o env var ``DFE_ACTIVE_AGENT=code-reviewer`` esta' presente (gate
  do dispatch CLI / @-mention).
- O comando ``/feature`` (em ``.opencode/command/feature.md``) Fase 4
  referencia ``subagent_type: code-reviewer`` (caminho canonico de
  invocacao do reviewer dentro do pipeline).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
PLUGIN_TS: Path = PROJECT_ROOT / ".opencode" / "plugin" / "agent-hooks.ts"
NODE_MODULES: Path = PROJECT_ROOT / "node_modules"
TSX_BIN: Path = (
    NODE_MODULES / ".bin" / ("tsx.cmd" if sys.platform == "win32" else "tsx")
)
FEATURE_MD: Path = PROJECT_ROOT / ".opencode" / "command" / "feature.md"


# ---- Profile code-reviewer no plugin TS ----

@pytest.fixture(scope="module")
def plugin_source() -> str:
    return PLUGIN_TS.read_text(encoding="utf-8")


def test_plugin_ts_exists() -> None:
    """Pre-requisito: plugin TS deve existir."""
    assert PLUGIN_TS.exists(), f"Plugin TS nao encontrado em {PLUGIN_TS}"


def test_agent_map_contains_code_reviewer(plugin_source: str) -> None:
    """Map ``AGENTS`` deve ter entrada com slug ``code-reviewer``."""
    match = re.search(
        r'"code-reviewer"\s*:\s*\{[^}]*\}',
        plugin_source,
        re.DOTALL,
    )
    assert match, (
        "agent-hooks.ts deve ter entrada `\"code-reviewer\": { ... }` "
        "no map AGENTS."
    )


def test_code_reviewer_profile_has_pre_tool_use(plugin_source: str) -> None:
    """Profile code-reviewer deve referenciar ``pre_tool_use.py``.

    Sprint 12 (B12.1): hook movido de ``.claude/hooks/code-reviewer/``
    para ``.opencode/hooks/code-reviewer/``.
    """
    match = re.search(
        r'"code-reviewer"\s*:\s*\{(?P<body>.*?)\n\s*\},',
        plugin_source,
        re.DOTALL,
    )
    assert match, "Perfil code-reviewer nao encontrado no map AGENTS."
    body = match.group("body")
    assert "preToolUse" in body, (
        f"Profile code-reviewer deve ter preToolUse; body: {body!r}"
    )
    assert ".opencode/hooks/code-reviewer/pre_tool_use.py" in body, (
        f"preToolUse deve apontar para `.opencode/hooks/code-reviewer/pre_tool_use.py` "
        f"(Sprint 12 B12.1); body: {body!r}"
    )


def test_code_reviewer_profile_has_pre_tool_use_bash(plugin_source: str) -> None:
    """Profile code-reviewer deve referenciar ``pre_tool_use_bash.py``.

    Sprint 12 (B12.1): hook movido de ``.claude/hooks/code-reviewer/``
    para ``.opencode/hooks/code-reviewer/``.
    """
    match = re.search(
        r'"code-reviewer"\s*:\s*\{(?P<body>.*?)\n\s*\},',
        plugin_source,
        re.DOTALL,
    )
    assert match, "Perfil code-reviewer nao encontrado no map AGENTS."
    body = match.group("body")
    assert "preToolUseBash" in body, (
        f"Profile code-reviewer deve ter preToolUseBash; body: {body!r}"
    )
    assert ".opencode/hooks/code-reviewer/pre_tool_use_bash.py" in body, (
        f"preToolUseBash deve apontar para `.opencode/hooks/code-reviewer/pre_tool_use_bash.py` "
        f"(Sprint 12 B12.1); body: {body!r}"
    )


def test_code_reviewer_profile_has_no_post_tool_use(plugin_source: str) -> None:
    """Profile code-reviewer NAO deve ter ``postToolUse`` (read-only)."""
    match = re.search(
        r'"code-reviewer"\s*:\s*\{(?P<body>.*?)\n\s*\},',
        plugin_source,
        re.DOTALL,
    )
    assert match
    body = match.group("body")
    assert "postToolUse" not in body, (
        f"code-reviewer NAO deve ter postToolUse (read-only); body: {body!r}"
    )


def test_code_reviewer_profile_has_no_stop(plugin_source: str) -> None:
    """Profile code-reviewer NAO deve ter ``stop`` (sem pytest no fim)."""
    match = re.search(
        r'"code-reviewer"\s*:\s*\{(?P<body>.*?)\n\s*\},',
        plugin_source,
        re.DOTALL,
    )
    assert match
    body = match.group("body")
    assert re.search(r"\bstop\s*:", body) is None, (
        f"code-reviewer NAO deve ter hook stop.py (read-only); "
        f"body: {body!r}"
    )


# ---- Sanity do /feature Fase 4 ----

# Nota: a propagacao do env var ``DFE_ACTIVE_AGENT=code-reviewer`` para
# subprocessos e o reconhecimento pelo hook ``code-reviewer/pre_tool_use.py``
# ja' estao cobertos por ``tests/integration/test_agent_dispatch.py``
# (3 testes: ``test_dfe_active_agent_env_propagates_to_subprocess``,
# ``test_code_reviewer_blocks_edit_in_subprocess``,
# ``test_no_agent_logs_warning_and_runs_permissive``).
# Nao duplicamos aqui para evitar drift.

@pytest.fixture(scope="module")
def feature_md_text() -> str:
    return FEATURE_MD.read_text(encoding="utf-8")


def test_feature_command_phase4_references_code_reviewer(
    feature_md_text: str,
) -> None:
    """``/feature`` Fase 4 deve disparar o subagent via ``subagent_type: code-reviewer``.

    Este e' o unico caminho canonico pelo qual o pipeline ``/feature``
    invoca o code-reviewer. Se esta string mudar, o reviewer para de
    ser chamado nas sprints.
    """
    assert "subagent_type: code-reviewer" in feature_md_text, (
        ".opencode/command/feature.md deve conter "
        "'subagent_type: code-reviewer' na Fase 4 (code review)."
    )


def test_feature_command_phase4_references_agent_definition(
    feature_md_text: str,
) -> None:
    """Template da Fase 4 deve apontar para a definicao canonica do agent.

    Sprint 11 D.1: path canônico e' singular (``.opencode/agent/``),
    nao plural (``.opencode/agents/``).
    """
    assert ".opencode/agent/code-reviewer.md" in feature_md_text, (
        "feature.md deve referenciar .opencode/agent/code-reviewer.md "
        "na instrucao ao code-reviewer (template). Path canonico "
        "consolidado em Sprint 11."
    )


# ---- Comportamento runtime do plugin ----

def test_plugin_skips_stop_event_for_code_reviewer(
    plugin_source: str,
) -> None:
    """Plugin NAO deve chamar stop hook para code-reviewer.

    O guard em ``agent-hooks.ts:284`` (``if (!profile || !profile.stop) return;``)
    garante que ``code-reviewer`` (read-only, sem ``stop.py``) sai sem
    chamar subprocess. Valida o guard por inspecao do source (padrao
    ja' usado em ``test_agent_hooks_plugin_loads.py``).

    > **Sprint 11**: ``qa-engineer`` nao e' mais mencionada porque foi
    > REMOVIDA em C.1 (consolidacao em `@dev`). Apenas2 agents sao
    > roteados pelo plugin TS (`code-reviewer` + `dev`).
    """
    pattern = re.compile(
        r"event[\s\S]*?if\s*\(\s*!profile\s*\|\|\s*!profile\.stop\s*\)\s*return",
        re.MULTILINE,
    )
    assert pattern.search(plugin_source), (
        "agent-hooks.ts deve ter guard `if (!profile || !profile.stop) return;` "
        "dentro do handler de event/Stop, para que code-reviewer (que nao "
        "tem stop.py) saia sem chamar subprocess (graceful no-op)."
    )


def test_code_reviewer_profile_post_tool_use_word_boundary(
    plugin_source: str,
) -> None:
    """Profile code-reviewer NAO deve ter ``postToolUse`` como token autonomo.

    Invariante ortogonal a ``test_code_reviewer_profile_has_no_post_tool_use``
    (que usa substring ``"postToolUse" not in body`` — captura ate aliases
    hipoteticos como ``postToolUseHandler``). Aqui usamos word-boundary
    ``\bpostToolUse\b`` para confirmar que a chave NAO aparece como token
    autonomo (forma canonica). As duas verificacoes se reforcam: substring
    cobre "tem a string em qualquer lugar", word-boundary cobre "tem a
    chave como token independente". Ambas devem ser verdes.
    """
    match = re.search(
        r'"code-reviewer"\s*:\s*\{(?P<body>.*?)\n\s*\},',
        plugin_source,
        re.DOTALL,
    )
    assert match, "Perfil code-reviewer nao encontrado."
    body = match.group("body")
    assert not re.search(r"\bpostToolUse\b", body), (
        f"code-reviewer NAO deve ter chave 'postToolUse' como token autonomo "
        f"(read-only); body: {body!r}"
    )
