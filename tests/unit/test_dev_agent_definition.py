"""Validacao estrutural do agente @dev (PLAN_SPRINT10 A.1).

Cobre:

- Arquivo existe em ``.opencode/agent/dev.md`` (formato opencode CLI).
- Frontmatter YAML valido com campos canonicos.
- Frontmatter declara ``name: dev``, ``mode: subagent``, ``model``,
  ``permission.*`` (com ``edit: allow``, ``external_directory: deny``).
- Corpo contem as strings canonicas (slug `dev`, referencias a `/feature`,
  `/bug`, `/duvida`, RAG antes/depois).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

AGENT_FILE: Path = (
    Path(__file__).resolve().parents[2] / ".opencode" / "agent" / "dev.md"
)


@pytest.fixture(scope="module")
def agent_text() -> str:
    assert AGENT_FILE.exists(), f"Arquivo {AGENT_FILE} nao existe"
    return AGENT_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def frontmatter(agent_text: str) -> str:
    parts = agent_text.split("---", 2)
    assert len(parts) >= 3, "Arquivo deve ter frontmatter YAML entre ---"
    return parts[1]


def test_agent_file_exists() -> None:
    assert AGENT_FILE.exists(), (
        f"Arquivo {AGENT_FILE} nao existe; crie `.opencode/agent/dev.md` "
        "(PLAN_SPRINT10 A.1)."
    )


def test_frontmatter_contains_name_dev(frontmatter: str) -> None:
    assert re.search(r"^name:\s*dev\s*$", frontmatter, re.MULTILINE), (
        f"frontmatter deve conter 'name: dev'. Recebido:\n{frontmatter}"
    )


def test_frontmatter_contains_mode_primary(frontmatter: str) -> None:
    """`mode: primary` expoe `@dev` no menu principal do opencode (Sprint 14+).

    Antes da Sprint 14, `dev` era `mode: subagent` (invisivel no menu primario).
    Como usuarios podem preferir invocar `@dev` diretamente para tarefas fora do
    escopo de slash command, foi promovido a primary em 2026-08-26. Slash
    commands (`/feature`, `/bug`, `/duvida`) continuam invocando `dev`
    explicitamente via frontmatter, entao essa mudanca NAO quebra o pipeline.
    """
    assert re.search(r"^mode:\s*primary\s*$", frontmatter, re.MULTILINE), (
        f"frontmatter deve conter 'mode: primary' (Sprint 14). Recebido:\n{frontmatter}"
    )


def test_frontmatter_yaml_is_valid(agent_text: str) -> None:
    import yaml
    parts = agent_text.split("---", 2)
    yaml.safe_load(parts[1])


def test_frontmatter_model_is_declared(frontmatter: str) -> None:
    """Mesmo placeholder `PROVIDER/MiniMax-M3` e' aceitavel."""
    assert re.search(r"^model:\s*\S+/\S+\s*$", frontmatter, re.MULTILINE), (
        f"frontmatter deve conter 'model: PROVIDER/MiniMax-M3'. Recebido:\n{frontmatter}"
    )


def test_frontmatter_permission_allows_edit(frontmatter: str) -> None:
    """`permission.edit: allow` e' o que diferencia `@dev` do `code-reviewer`."""
    assert re.search(r"^\s+edit:\s*allow\s*$", frontmatter, re.MULTILINE), (
        f"frontmatter deve conter 'edit: allow' sob permission. "
        f"Recebido:\n{frontmatter}"
    )


def test_frontmatter_permission_denies_external_directory(frontmatter: str) -> None:
    """`external_directory: deny` impede escrita fora do workspace."""
    assert re.search(
        r"^\s+external_directory:\s*deny\s*$", frontmatter, re.MULTILINE
    ), (
        f"frontmatter deve conter 'external_directory: deny' sob permission. "
        f"Recebido:\n{frontmatter}"
    )


def test_body_mentions_all_three_slash_commands(agent_text: str) -> None:
    """Corpo documenta que `/feature`, `/bug`, `/duvida` invocam `@dev`."""
    for cmd in ("/feature", "/bug", "/duvida"):
        assert cmd in agent_text, (
            f"Corpo do agent deve mencionar o slash command `{cmd}` "
            "(owner). Recebido:\n" + agent_text[:1000]
        )


def test_body_mentions_rag_before_and_after(agent_text: str) -> None:
    """Corpo explica o padrao RAG antes/depois."""
    assert re.search(r"RAG\s+antes", agent_text, re.IGNORECASE), (
        "Corpo deve mencionar 'RAG antes' (Fase 0)."
    )
    assert re.search(r"RAG\s+depois", agent_text, re.IGNORECASE), (
        "Corpo deve mencionar 'RAG depois' (Fase final)."
    )


def test_body_mentions_subagent_code_reviewer(agent_text: str) -> None:
    """Corpo documenta que `@dev` sub-delega revisao para `code-reviewer`."""
    assert "code-reviewer" in agent_text, (
        "Corpo deve mencionar 'code-reviewer' (sub-delegacao de revisao)."
    )


def test_body_mentions_never_make_invariants(agent_text: str) -> None:
    """Corpo referencia as regras inegociaiveis (Nunca fazer)."""
    assert "Nunca inventar" in agent_text, (
        "Corpo deve referenciar 'Nunca inventar' (ver AGENTS.md)."
    )
    assert "ALLOWED_DOMAINS" in agent_text, (
        "Corpo deve referenciar 'ALLOWED_DOMAINS' (ver .opencode/rules/dfe-rules.md)."
    )
