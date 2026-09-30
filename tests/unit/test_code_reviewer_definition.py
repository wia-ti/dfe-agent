"""Validacao estrutural do subagent ``code-reviewer`` (Claude Code).

Garante que ``.claude/agents/code-reviewer.md`` mantem os invariantes sem os
quais o Claude Code nao expoe o reviewer como subagent read-only:

- Arquivo existe e tem frontmatter YAML valido.
- ``name: code-reviewer`` + ``description`` (obrigatorios em subagents).
- ``tools:`` sem ferramentas de escrita/delegacao (``Write``, ``Edit``,
  ``NotebookEdit``, ``Agent``, ``Skill``, ``TodoWrite``) - barreira principal
  do read-only (substitui o ``permission.*: deny`` do OpenCode).
- Corpo contem as 3 classes canonicas do relatorio e a restricao read-only.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

AGENT_FILE: Path = (
    Path(__file__).resolve().parents[2] / ".claude" / "agents" / "code-reviewer.md"
)
FORBIDDEN_TOOLS: tuple[str, ...] = ("Write", "Edit", "MultiEdit", "NotebookEdit", "Agent", "Skill", "TodoWrite")


@pytest.fixture(scope="module")
def agent_text() -> str:
    assert AGENT_FILE.exists(), f"Arquivo {AGENT_FILE} nao existe"
    return AGENT_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def frontmatter(agent_text: str) -> dict[str, Any]:
    parts = agent_text.split("---", 2)
    assert len(parts) >= 3, "Arquivo deve ter frontmatter YAML entre '---'"
    data = yaml.safe_load(parts[1])
    assert isinstance(data, dict)
    return data


def _tools(frontmatter: dict[str, Any]) -> list[str]:
    raw = frontmatter.get("tools", "")
    items = raw if isinstance(raw, list) else str(raw).split(",")
    return [t.strip() for t in items if t.strip()]


def test_agent_file_exists() -> None:
    assert AGENT_FILE.exists(), f"Definicao do code-reviewer esperada em {AGENT_FILE}."


def test_frontmatter_has_name_and_description(frontmatter: dict[str, Any]) -> None:
    assert frontmatter.get("name") == "code-reviewer"
    assert str(frontmatter.get("description", "")).strip()


def test_frontmatter_declares_tools_allowlist(frontmatter: dict[str, Any]) -> None:
    """Sem ``tools:`` o subagent herda todas as ferramentas (inclusive Edit)."""
    assert _tools(frontmatter), "code-reviewer deve declarar `tools:` explicito."


@pytest.mark.parametrize("tool", FORBIDDEN_TOOLS)
def test_frontmatter_excludes_write_tools(frontmatter: dict[str, Any], tool: str) -> None:
    assert tool not in _tools(frontmatter), f"code-reviewer nao pode ter `{tool}` (read-only)."


@pytest.mark.parametrize("tool", ["Read", "Grep", "Glob", "Bash"])
def test_frontmatter_allows_read_tools(frontmatter: dict[str, Any], tool: str) -> None:
    assert tool in _tools(frontmatter), f"code-reviewer precisa de `{tool}`."


def test_body_mentions_classification(agent_text: str) -> None:
    for klass in ("BLOQUEANTE", "IMPORTANTE", "SUGESTAO"):
        assert klass in agent_text, f"Corpo deve mencionar a classe '{klass}'."


def test_body_mentions_read_only(agent_text: str) -> None:
    assert "read-only" in agent_text.lower()


def test_body_references_hooks(agent_text: str) -> None:
    """Corpo aponta para os 2 hooks em ``.claude/hooks/code-reviewer/``."""
    assert ".claude/hooks/code-reviewer/pre_tool_use.py" in agent_text
    assert ".claude/hooks/code-reviewer/pre_tool_use_bash.py" in agent_text
