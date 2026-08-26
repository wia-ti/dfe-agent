"""Validacao estrutural do agent ``code-reviewer`` (PLAN_SPRINT9 / Fase A / I9.1 + PLAN_SPRINT11 D).

Analogia a ``tests/unit/test_dfe_agent_definition.py``: garante que a
definicao do code-reviewer em ``.opencode/agent/code-reviewer.md``
mantem invariantes estruturais sem os quais o opencode nao expoe o
agent como subagent read-only invocavel:

- Arquivo existe.
- Frontmatter YAML valido entre ``---``.
- Campos canonicos: ``name: code-reviewer`` e ``mode: primary``.
- ``model: PROVIDER/MiniMax-M3`` (Sprint 11 B11.5; sem prefixo quebra Task tool).
- ``permission.edit: deny`` (read-only - barreira principal).
- ``permission.task/skill/todowrite: deny`` (delega/interage/salva).
- Corpo contem as 3 classes canonicas do relatorio
  (BLOQUEANTE / IMPORTANTE / SUGESTAO) e a restricao read-only.

Sprint 11 D.1: arquivo movido de ``.opencode/agents/`` (plural) para
``.opencode/agent/`` (singular) — path canonico do opencode CLI.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

AGENT_FILE: Path = (
    Path(__file__).resolve().parents[2]
    / ".opencode"
    / "agent"
    / "code-reviewer.md"
)


@pytest.fixture(scope="module")
def agent_text() -> str:
    assert AGENT_FILE.exists(), f"Arquivo {AGENT_FILE} nao existe"
    return AGENT_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def frontmatter(agent_text: str) -> str:
    parts = agent_text.split("---", 2)
    assert len(parts) >= 3, (
        "Arquivo deve ter frontmatter YAML entre '---'; "
        f"obtido {len(parts)} secoes"
    )
    return parts[1]


def test_agent_file_exists() -> None:
    assert AGENT_FILE.exists(), (
        f"Definicao do code-reviewer esperada em {AGENT_FILE}; nao encontrada."
    )


def test_frontmatter_contains_name_code_reviewer(frontmatter: str) -> None:
    assert re.search(
        r"^name:\s*code-reviewer\s*$", frontmatter, re.MULTILINE,
    ), f"frontmatter deve conter 'name: code-reviewer'. Recebido:\n{frontmatter}"


def test_frontmatter_yaml_is_valid(agent_text: str) -> None:
    import yaml

    parts = agent_text.split("---", 2)
    yaml.safe_load(parts[1])


def test_frontmatter_has_model_field(frontmatter: str) -> None:
    """Frontmatter deve declarar ``model: PROVIDER/MiniMax-M3``.

    O formato ``PROVIDER/<modelo>`` e' obrigatorio desde a Sprint 11
    (B11.5): sem o prefixo do provider, a Task tool do opencode
    retorna ``Model not found: MiniMax-M3/.`` e o reviewer nao pode
    ser invocado na Fase 4 do ``/feature``. Precedente:
    ``test_dfe_agent_definition.py::test_frontmatter_contains_model_minimax``
    e ``test_dev_agent_definition.py::test_frontmatter_model_is_declared``.
    """
    assert re.search(
        r"^model:\s*\S+/\S+", frontmatter, re.MULTILINE,
    ), (
        "frontmatter deve conter 'model: PROVIDER/MiniMax-M3' "
        "(formato com prefixo de provider, obrigatorio desde Sprint 11 B11.5). "
        f"Recebido:\n{frontmatter}"
    )


def test_frontmatter_has_mode_primary(frontmatter: str) -> None:
    """``mode: primary`` expoe o code-reviewer no menu principal (Sprint 14+).

    Antes da Sprint 14, era ``mode: subagent`` (invisivel no menu primario).
    Promovido a primary em 2026-08-26 para que usuarios possam invocar
    `@code-reviewer` diretamente via TUI. Slash commands (`/feature`, `/bug`)
    continuam invocando via Task tool sem quebra de pipeline.
    """
    assert re.search(
        r"^mode:\s*primary\s*$", frontmatter, re.MULTILINE,
    ), (
        f"frontmatter deve conter 'mode: primary' (Sprint 14). "
        f"Recebido:\n{frontmatter}"
    )


def test_frontmatter_denies_edit(frontmatter: str) -> None:
    """``permission.edit: deny`` e' a barreira principal do read-only."""
    assert re.search(
        r"^permission:\s*$", frontmatter, re.MULTILINE,
    ), f"frontmatter deve ter bloco 'permission:'. Recebido:\n{frontmatter}"
    assert re.search(
        r"^\s*edit:\s*deny\s*$", frontmatter, re.MULTILINE,
    ), (
        f"permission.edit deve ser 'deny' (read-only). "
        f"Recebido:\n{frontmatter}"
    )


def test_frontmatter_denies_task(frontmatter: str) -> None:
    """``permission.task: deny`` impede o reviewer de delegar a outro subagent."""
    assert re.search(
        r"^\s*task:\s*deny\s*$", frontmatter, re.MULTILINE,
    ), (
        f"permission.task deve ser 'deny' (reviewer nao delega). "
        f"Recebido:\n{frontmatter}"
    )


def test_frontmatter_denies_skill(frontmatter: str) -> None:
    """``permission.skill: deny`` impede o reviewer de carregar skill domain."""
    assert re.search(
        r"^\s*skill:\s*deny\s*$", frontmatter, re.MULTILINE,
    ), (
        f"permission.skill deve ser 'deny'. Recebido:\n{frontmatter}"
    )


def test_frontmatter_denies_todowrite(frontmatter: str) -> None:
    """``permission.todowrite: deny`` impede o reviewer de criar TODOs."""
    assert re.search(
        r"^\s*todowrite:\s*deny\s*$", frontmatter, re.MULTILINE,
    ), (
        f"permission.todowrite deve ser 'deny'. Recebido:\n{frontmatter}"
    )


def test_frontmatter_allows_read(frontmatter: str) -> None:
    """``permission.read: allow`` confirma que o agent pode ler (escopo principal)."""
    assert re.search(
        r"^\s*read:\s*allow\s*$", frontmatter, re.MULTILINE,
    ), (
        f"permission.read deve ser 'allow'. Recebido:\n{frontmatter}"
    )


def test_body_mentions_classification(agent_text: str) -> None:
    """Corpo deve descrever as 3 classes canonicas do relatorio."""
    for klass in ("BLOQUEANTE", "IMPORTANTE", "SUGESTAO"):
        assert klass in agent_text, (
            f"Corpo do code-reviewer deve mencionar a classe '{klass}' "
            "no template do relatorio."
        )


def test_body_mentions_read_only(agent_text: str) -> None:
    """Corpo deve declarar explicitamente o escopo read-only."""
    assert "read-only" in agent_text.lower(), (
        "Corpo deve conter 'read-only' (escopo inegociavel do agent)."
    )


def test_body_references_hooks(agent_text: str) -> None:
    """Corpo deve apontar para os 2 hooks em ``.opencode/hooks/code-reviewer/``.

    Documentacao canonica em ``AGENTS.md`` (Sprint 4) lista:
    - ``pre_tool_use.py`` (bloqueia Write/Edit).
    - ``pre_tool_use_bash.py`` (bloqueia Bash destrutivo).

    Sprint 12 (B12.1): hooks migraram de ``.claude/hooks/code-reviewer/``
    para ``.opencode/hooks/code-reviewer/``.
    """
    assert ".opencode/hooks/code-reviewer/pre_tool_use.py" in agent_text, (
        "Corpo deve referenciar o hook pre_tool_use.py do code-reviewer "
        "(path canonico pos-Sprint 12 B12.1)."
    )
    assert ".opencode/hooks/code-reviewer/pre_tool_use_bash.py" in agent_text, (
        "Corpo deve referenciar o hook pre_tool_use_bash.py do code-reviewer "
        "(path canonico pos-Sprint 12 B12.1)."
    )
