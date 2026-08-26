"""Validacao estrutural do ``opencode.json`` (PLAN_SPRINT12 / Task 3.2).

Cobre:

- ``instructions`` lista apenas paths em ``.opencode/rules/`` e ``AGENTS.md``.
  Antes da Sprint 12 listava ``.claude/rules/*.md`` (mistura de namespace).
- ``plugin[0]`` aponta para o plugin TS canonico (``.opencode/plugin/...``).

Apos a unificacao, o opencode.json nao deve citar ``.claude/`` em
nenhum campo: o plugin TS ja' cuida de toda a logica de hooks via
``AGENTS`` map, e as rules vivem em ``.opencode/rules/``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
OPENCODE_JSON: Path = PROJECT_ROOT / "opencode.json"


@pytest.fixture(scope="module")
def config() -> dict:
    assert OPENCODE_JSON.exists(), f"{OPENCODE_JSON} nao existe"
    return json.loads(OPENCODE_JSON.read_text(encoding="utf-8"))


def test_opencode_json_loads(config: dict) -> None:
    """Arquivo parseia como JSON valido."""
    assert isinstance(config, dict), (
        f"opencode.json deve ser objeto JSON; obtido {type(config).__name__}"
    )


def test_instructions_references_opencode_rules_only(config: dict) -> None:
    """``instructions`` lista apenas ``.opencode/rules/*.md`` + ``AGENTS.md``.

    Antes (Sprints 4-11) listava ``.claude/rules/*.md`` (mistura de
    namespace). Sprint 12 (B12.3) unificou em ``.opencode/rules/``.
    """
    instructions = config.get("instructions")
    assert isinstance(instructions, list) and instructions, (
        f"`instructions` deve ser lista nao-vazia; obtido {instructions!r}"
    )
    for entry in instructions:
        assert isinstance(entry, str), (
            f"Cada item de `instructions` deve ser string; obtido {entry!r}"
        )
        assert not entry.startswith(".claude/"), (
            f"`instructions` NAO deve citar paths em `.claude/` "
            f"(unificacao Sprint 12); obtido {entry!r}"
        )
    rules_paths = [e for e in instructions if e.startswith(".opencode/rules/")]
    assert len(rules_paths) >= 1, (
        f"`instructions` deve listar ao menos 1 rule em `.opencode/rules/`; "
        f"obtido {instructions!r}"
    )
    assert "AGENTS.md" in instructions, (
        f"`instructions` deve listar `AGENTS.md` (contexto canonico do "
        f"projeto); obtido {instructions!r}"
    )


def test_plugin_path_references_opencode_plugin_only(config: dict) -> None:
    """``plugin[0]`` aponta para ``.opencode/plugin/agent-hooks.ts``.

    Antes (Sprint 4-11): instalado via CLI (``opencode plugin add``).
    Hoje (Sprint 11 C.1): explicitamente declarado em ``opencode.json``.
    """
    plugins = config.get("plugin")
    assert isinstance(plugins, list) and plugins, (
        f"`plugin` deve ser lista nao-vazia; obtido {plugins!r}"
    )
    first = plugins[0]
    assert isinstance(first, str), (
        f"Primeiro item de `plugin` deve ser string; obtido {first!r}"
    )
    assert first.startswith(".opencode/"), (
        f"`plugin[0]` deve apontar para `.opencode/...`; obtido {first!r}"
    )
    assert not first.startswith(".claude/"), (
        f"`plugin[0]` NAO deve apontar para `.claude/...` (unificacao "
        f"Sprint 12); obtido {first!r}"
    )


def test_no_dot_claude_reference_anywhere(config: dict) -> None:
    """Nenhum campo de ``opencode.json`` cita ``.claude/``.

    Gate anti-regressao: se um futuro dev adicionar ``.claude/`` de volta,
    o teste falha antes do opencode carregar.
    """
    raw = OPENCODE_JSON.read_text(encoding="utf-8")
    assert ".claude/" not in raw, (
        f"opencode.json NAO deve conter `.claude/` em nenhum campo "
        f"(Sprint 12 B12.3); conteudo:\n{raw}"
    )


def test_instructions_lists_dfe_rules(config: dict) -> None:
    """``instructions`` deve listar ``.opencode/rules/dfe-rules.md``.

    Regra canonica do DFe-Agent (4 guardrails inviolaveis: veracidade,
    ALLOWED_DOMAINS, Fontes, NO_EVIDENCE_MESSAGE). Vive no disco desde
    Sprint 4-7; Sprint 13 B13.1 adicionou ao ``instructions`` para que
    o opencode runtime a carregue.

    Anti-regressao: se um futuro dev remover ``dfe-rules.md`` do
    ``instructions``, o teste falha antes do opencode carregar.

    Smoke test manual (NAO automatizado — exige runtime do opencode CLI):
    ``opencode run --agent dfe-agent "cite a regra de veracidade"`` deve
    retornar resposta citando literalmente as 4 regras de ``dfe-rules.md``.
    """
    instructions = config.get("instructions")
    assert isinstance(instructions, list), (
        f"`instructions` deve ser lista; obtido {instructions!r}"
    )
    assert ".opencode/rules/dfe-rules.md" in instructions, (
        "`instructions` deve listar `.opencode/rules/dfe-rules.md` "
        "(B13.1, gate anti-regressao); obtido "
        f"{instructions!r}"
    )


def test_tsx_is_devdependency() -> None:
    """``tsx`` deve estar em ``devDependencies``, nao ``dependencies``.

    Justificativa: ``tsx`` e' usado apenas em runtime de dev/test
    (smoke test E2E do RAG meta-cognitivo via ``npx tsx``). Pertence
    a ``devDependencies`` por semantica npm.

    Sprint 13 I13.1 canonicalizou a posicao. Anti-regressao: se um
    futuro dev mover ``tsx`` de volta para ``dependencies``, o teste
    falha.
    """
    pkg_json = (PROJECT_ROOT / ".opencode" / "package.json").read_text(
        encoding="utf-8"
    )
    pkg = json.loads(pkg_json)
    deps = pkg.get("dependencies", {})
    dev_deps = pkg.get("devDependencies", {})
    assert "tsx" not in deps, (
        f"`tsx` deve estar em `devDependencies`, nao `dependencies`; "
        f"obtido dependencies={list(deps.keys())}"
    )
    assert "tsx" in dev_deps, (
        f"`tsx` deve estar pinned em `devDependencies`; "
        f"obtido devDependencies={list(dev_deps.keys())}"
    )