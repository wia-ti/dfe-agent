"""Gate anti-regressao: agents/hooks legacy NAO voltam (PLAN_SPRINT11 C.5 + Sprint 12 B12.1 + Sprint 18).

Garante que apos a Sprint 18:

- Apenas ``dev.md``, ``code-reviewer.md``, ``dfe-agent.md``, ``deployer.md``
  existem em ``.opencode/agent/`` (canonical agents; Sprint 11 D.1 + Sprint 12
  B12.2 + Sprint 18 B18.2).
- Apenas ``dev/``, ``code-reviewer/``, ``deployer/``, ``_lib/`` existem em
  ``.opencode/hooks/`` (alem de arquivos soltos canonicos como
  ``domain_guard.py``, ``allowed_domains.py``, ``__init__.py``,
  ``README.md``) - Sprint 12 B12.1 + Sprint 18 B18.2.
- ``.claude/hooks/`` e ``.claude/agents/`` estao vazios (Sprint 12 Fases
  1 + 3); serao removidos completamente na Fase 5.
- O plugin TS ``agent-hooks.ts`` roteia para 3 slugs canonicos
  (``dev`` + ``code-reviewer`` + ``deployer``; Sprint 18 D18.7).
- ``_lib/payload.py::_AGENT_HINTS`` reconhece esses 3 slugs.
- ``_lib/test_runner.py::suites_for_path`` nao tem mais branch para
  ``backend-engineer`` ou ``ml-engineer``.

> **Sprint 12 (B12.1 + B12.2 + B12.3)**: harness consolidado em
> ``.opencode/``. Os 2 agents stub em ``.claude/agents/`` foram
> removidos (canonical em ``.opencode/agent/``).
>
> **Sprint 18 (B18.2)**: agent ``deployer`` adicionado para substituir o CI
> (3 workflows `.github/workflows/*.yml` foram removidos na mesma sprint).
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest


PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]


# Slugs canonicos apos Sprint 18 (3 slugs: dev, code-reviewer, deployer).
CANONICAL_SLUGS: frozenset[str] = frozenset({"dev", "code-reviewer", "deployer"})

# Slugs que devem ter sido removidos (anti-regressao explicita).
LEGACY_SLUGS: frozenset[str] = frozenset({
    "backend-engineer",
    "ml-engineer",
    "prompt-engineer",
    "qa-engineer",
})


# ---------------------------------------------------------------------------
# .opencode/agent/ (canonical; substituiu .claude/agents/)
# ---------------------------------------------------------------------------


def test_only_canonical_agents_in_opencode_agent_dir() -> None:
    """Apenas ``dev.md``, ``code-reviewer.md``, ``dfe-agent.md`` em ``.opencode/agent/``."""
    agent_dir = PROJECT_ROOT / ".opencode" / "agent"
    md_files = {p.stem for p in agent_dir.glob("*.md") if p.stem not in {"README"}}
    expected = CANONICAL_SLUGS | {"dfe-agent"}
    assert md_files == expected, (
        f"Esperava apenas {expected}; obtido {md_files}. "
        f"Agents legacy NAO devem voltar."
    )


def test_no_legacy_slug_in_opencode_agent_md() -> None:
    """Nenhum ``.opencode/agent/<slug>.md`` referencia slug legacy no corpo.

    Exclui ``README.md`` (pode mencionar slugs legacy em contexto historico).
    """
    agent_dir = PROJECT_ROOT / ".opencode" / "agent"
    for md_file in agent_dir.glob("*.md"):
        if md_file.stem == "README":
            continue
        text = md_file.read_text(encoding="utf-8")
        for legacy in LEGACY_SLUGS:
            assert legacy not in text, (
                f"{md_file.name} contem referencia ao slug legacy "
                f"'{legacy}' (Sprint 11 removeu)"
            )


# ---------------------------------------------------------------------------
# .claude/agents/ (apagado na Fase 3, deve estar vazio)
# ---------------------------------------------------------------------------


def test_claude_agents_dir_is_empty() -> None:
    """``.claude/agents/`` deve estar vazio (removidos na Fase 3)."""
    agents_dir = PROJECT_ROOT / ".claude" / "agents"
    if not agents_dir.exists():
        return
    contents = list(agents_dir.iterdir())
    assert contents == [], (
        f".claude/agents/ deve estar vazio; obtido {[c.name for c in contents]}"
    )


# ---------------------------------------------------------------------------
# .opencode/hooks/ (canonical; substituiu .claude/hooks/)
# ---------------------------------------------------------------------------


_OPENCODE_HOOKS_FORBIDDEN: frozenset[str] = frozenset({
    "backend",
    "ml",
    "prompt",
    "qa",
    "qa-engineer",
    "backend-engineer",
    "ml-engineer",
    "prompt-engineer",
})


def test_only_canonical_hooks_in_opencode_hooks_dir() -> None:
    """Apenas diretorios ``dev/``, ``code-reviewer/``, ``_lib/`` + arquivos canonicos.

    Tolerancias:
    - ``__pycache__/`` (bytecode Python gerado em runtime; limpeza
      automatica via ``python -m compileall`` / ``pytest``).
    - Diretorios com nomes que NAO correspondem a slugs legacy.

    O foco deste gate e' anti-regressao: nenhum subdiretorio de agent
    legacy (``backend/``, ``ml/``, etc.) deve voltar.
    """
    hooks_dir = PROJECT_ROOT / ".opencode" / "hooks"
    actual = {p.name for p in hooks_dir.iterdir() if p.is_dir()}
    legacy_dirs = actual & _OPENCODE_HOOKS_FORBIDDEN
    assert not legacy_dirs, (
        f".opencode/hooks/ tem diretorios legacy: {legacy_dirs}. "
        f"Sprint 11/12 removeram backend-engineer/ml-engineer/"
        f"prompt-engineer/qa-engineer."
    )


def test_opencode_hooks_required_directories_exist() -> None:
    """Diretorios canonicos ``dev/``, ``code-reviewer/``, ``deployer/``, ``_lib/`` existem."""
    hooks_dir = PROJECT_ROOT / ".opencode" / "hooks"
    for name in ("dev", "code-reviewer", "deployer", "_lib"):
        assert (hooks_dir / name).is_dir(), (
            f".opencode/hooks/{name}/ deve existir "
            f"(unificacao Sprint 12 + Sprint 18 deployer)"
        )


# ---------------------------------------------------------------------------
# .claude/hooks/ (apagado na Fase 1, deve estar vazio)
# ---------------------------------------------------------------------------


def test_claude_hooks_dir_is_empty() -> None:
    """``.claude/hooks/`` deve estar vazio (movido para ``.opencode/hooks/``)."""
    hooks_dir = PROJECT_ROOT / ".claude" / "hooks"
    if not hooks_dir.exists():
        return
    contents = list(hooks_dir.iterdir())
    assert contents == [], (
        f".claude/hooks/ deve estar vazio; obtido {[c.name for c in contents]}"
    )


# ---------------------------------------------------------------------------
# .opencode/plugin/agent-hooks.ts
# ---------------------------------------------------------------------------


def _read_plugin_ts() -> str:
    return (PROJECT_ROOT / ".opencode" / "plugin" / "agent-hooks.ts").read_text(
        encoding="utf-8"
    )


def test_plugin_ts_only_routes_to_canonical_agents() -> None:
    """Plugin TS roteia apenas para ``dev``, ``code-reviewer``, ``deployer``."""
    src = _read_plugin_ts()
    for legacy in LEGACY_SLUGS:
        assert f'"{legacy}"' not in src, (
            f"agent-hooks.ts ainda roteia para slug legacy '{legacy}'; "
            f"removido em Sprint 11 C.3"
        )


def test_plugin_ts_recognized_agent_slugs_reduced() -> None:
    """Set ``RECOGNIZED_AGENT_SLUGS`` contem apenas os 2 slugs canonicos."""
    src = _read_plugin_ts()
    match = re.search(
        r"RECOGNIZED_AGENT_SLUGS[\s\S]*?new Set\(\[([^\]]+)\]\)",
        src,
    )
    assert match is not None, (
        "RECOGNIZED_AGENT_SLUGS nao encontrado em agent-hooks.ts"
    )
    slugs_str = match.group(1)
    found_slugs: set[str] = set()
    for slug_match in re.finditer(r'"([^"]+)"', slugs_str):
        found_slugs.add(slug_match.group(1))
    assert found_slugs == CANONICAL_SLUGS, (
        f"RECOGNIZED_AGENT_SLUGS deveria ser {CANONICAL_SLUGS}; "
        f"obtido {found_slugs}"
    )


def test_plugin_ts_hook_paths_use_opencode_prefix() -> None:
    """Sprint 12 (B12.1) + Sprint 18: o plugin TS aponta para ``.opencode/hooks/...``."""
    src = _read_plugin_ts()
    for legacy_path in (
        ".claude/hooks/code-reviewer/pre_tool_use.py",
        ".claude/hooks/code-reviewer/pre_tool_use_bash.py",
        ".claude/hooks/dev/pre_tool_use.py",
        ".claude/hooks/dev/post_tool_use.py",
        ".claude/hooks/dev/stop.py",
    ):
        assert legacy_path not in src, (
            f"agent-hooks.ts ainda aponta para path legado '{legacy_path}' "
            f"(Sprint 12 B12.1)"
        )
    canonical_count = src.count(".opencode/hooks/")
    # Sprint 18: 3 profiles (dev/code-reviewer/deployer) × 3 hooks = 9 paths
    # esperados. code-reviewer tem 2 hooks (pre_tool_use + pre_tool_use_bash),
    # deployer tem 3 hooks (pre_tool_use + post_tool_use + stop),
    # dev tem 3 hooks (pre_tool_use + post_tool_use + stop).
    # Total: 2 + 3 + 3 = 8 paths canonicos. Gate tolerante a >= 8.
    assert canonical_count >= 8, (
        f"agent-hooks.ts deveria apontar para >=8 paths `.opencode/hooks/...` "
        f"(3 profiles x 2-3 hooks); obtido {canonical_count}"
    )


# ---------------------------------------------------------------------------
# .opencode/hooks/_lib/payload.py
# ---------------------------------------------------------------------------


def _load_payload() -> object:
    script = PROJECT_ROOT / ".opencode" / "hooks" / "_lib" / "payload.py"
    spec = importlib.util.spec_from_file_location("payload_for_test", script)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_AGENT_HINTS_in_payload_has_no_legacy() -> None:
    """``_AGENT_HINTS`` em ``payload.py`` reduzido para 2 slugs."""
    mod = _load_payload()
    hint_slugs = {slug for slug, _ in mod._AGENT_HINTS}
    assert hint_slugs == CANONICAL_SLUGS, (
        f"_AGENT_HINTS deveria ser {CANONICAL_SLUGS}; obtido {hint_slugs}. "
        f"Agents legacy foram removidos em Sprint 11 C.2"
    )


# ---------------------------------------------------------------------------
# .opencode/hooks/_lib/test_runner.py
# ---------------------------------------------------------------------------


def _load_test_runner() -> object:
    script = PROJECT_ROOT / ".opencode" / "hooks" / "_lib" / "test_runner.py"
    spec = importlib.util.spec_from_file_location("test_runner_for_test", script)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_test_runner_no_legacy_agent_branches() -> None:
    """``suites_for_path`` nao tem branch code-level para slugs legacy.

    Apenas o codigo (nao docstring) e' checado: a docstring pode mencionar
    slugs legacy como contexto historico.
    """
    src = (PROJECT_ROOT / ".opencode" / "hooks" / "_lib" / "test_runner.py").read_text(
        encoding="utf-8"
    )
    # Remover docstrings (entre aspas triplas) para checar apenas codigo.
    code_only = re.sub(r'"""[\s\S]*?"""', "", src)
    for legacy in LEGACY_SLUGS:
        assert legacy not in code_only, (
            f"_lib/test_runner.py ainda referencia slug legacy '{legacy}' "
            f"em codigo (removido em Sprint 11 C.2)"
        )