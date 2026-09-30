"""Validacao estrutural do subagent ``dfe-agent`` (Claude Code)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

AGENT_FILE: Path = Path(__file__).resolve().parents[2] / ".claude" / "agents" / "dfe-agent.md"


@pytest.fixture(scope="module")
def agent_text() -> str:
    assert AGENT_FILE.exists(), f"Arquivo {AGENT_FILE} nao existe"
    return AGENT_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def frontmatter(agent_text: str) -> dict[str, Any]:
    parts = agent_text.split("---", 2)
    assert len(parts) >= 3, "Arquivo deve ter frontmatter YAML entre ---"
    data = yaml.safe_load(parts[1])
    assert isinstance(data, dict)
    return data


def test_agent_file_exists() -> None:
    assert AGENT_FILE.exists()


def test_frontmatter_has_name_and_description(frontmatter: dict[str, Any]) -> None:
    assert frontmatter.get("name") == "dfe-agent"
    assert str(frontmatter.get("description", "")).strip()


def test_frontmatter_preloads_dfe_fiscal_skill(frontmatter: dict[str, Any]) -> None:
    assert "dfe-fiscal" in (frontmatter.get("skills") or [])


def test_frontmatter_has_no_web_tools(frontmatter: dict[str, Any]) -> None:
    """Sem WebFetch/WebSearch: toda resposta vem da base RAG (ALLOWED_DOMAINS)."""
    tools = str(frontmatter.get("tools", ""))
    assert tools, "dfe-agent deve declarar `tools:` explicito."
    assert "WebFetch" not in tools and "WebSearch" not in tools


def test_body_contains_required_strings(agent_text: str) -> None:
    """Corpo deve conter literais canonicos (skill, NO_EVIDENCE_MESSAGE, Fontes)."""
    for s in ("dfe-fiscal", "Nao encontrei base para responder", "Fontes:"):
        assert s in agent_text, f"Corpo deve conter '{s}'"
