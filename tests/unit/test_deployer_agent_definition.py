"""Validacao estrutural do subagent ``deployer`` (Claude Code).

Cobre:

- Arquivo existe em ``.claude/agents/deployer.md`` com frontmatter valido.
- ``name: deployer`` + ``description``.
- ``tools:`` contem apenas leitura + ``Bash`` (deployer NAO edita, NAO delega,
  NAO consulta web) - substitui o ``permission.*`` do OpenCode.
- Corpo declara escopo canonico (git push/tag/pull/remote, npm publish/login/
  dist-tag, gh release), gate humano e os 3 hooks em ``.claude/hooks/deployer/``.
- ``.claude/settings.json`` exige aprovacao humana (``permissions.ask``) para
  as acoes destrutivas.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT: Path = Path(__file__).resolve().parents[2]
AGENT_FILE: Path = ROOT / ".claude" / "agents" / "deployer.md"
SETTINGS_FILE: Path = ROOT / ".claude" / "settings.json"


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


def _tools(frontmatter: dict[str, Any]) -> list[str]:
    raw = frontmatter.get("tools", "")
    items = raw if isinstance(raw, list) else str(raw).split(",")
    return [t.strip() for t in items if t.strip()]


def test_agent_file_exists() -> None:
    assert AGENT_FILE.exists(), f"Definicao do deployer esperada em {AGENT_FILE}."


def test_frontmatter_has_name_and_description(frontmatter: dict[str, Any]) -> None:
    assert frontmatter.get("name") == "deployer"
    assert str(frontmatter.get("description", "")).strip()


def test_frontmatter_tools_include_bash(frontmatter: dict[str, Any]) -> None:
    assert "Bash" in _tools(frontmatter), "deployer roda git/npm/gh via Bash."


@pytest.mark.parametrize(
    "tool", ["Write", "Edit", "MultiEdit", "NotebookEdit", "Agent", "Skill", "TodoWrite", "WebFetch", "WebSearch"]
)
def test_frontmatter_excludes_tool(frontmatter: dict[str, Any], tool: str) -> None:
    assert tool not in _tools(frontmatter), f"deployer nao pode ter `{tool}`."


@pytest.mark.parametrize("term", ["git push", "git tag", "git pull", "git remote", "npm publish", "npm login", "npm dist-tag", "gh release"])
def test_body_declares_scope(agent_text: str, term: str) -> None:
    assert term in agent_text, f"Corpo do deployer deve mencionar '{term}'."


def test_body_documents_human_gate(agent_text: str) -> None:
    text_lower = agent_text.lower()
    assert "humano" in text_lower
    assert "confirm" in text_lower or "aprov" in text_lower


@pytest.mark.parametrize("hook", ["pre_tool_use.py", "post_tool_use.py", "stop.py"])
def test_body_references_hook(agent_text: str, hook: str) -> None:
    assert f".claude/hooks/deployer/{hook}" in agent_text


def test_body_states_only_deployer_can_push(agent_text: str) -> None:
    text_lower = agent_text.lower()
    assert "unico agente autorizado" in text_lower or "unico autorizado" in text_lower


@pytest.mark.parametrize(
    "rule",
    ["Bash(git push:*)", "Bash(git tag:*)", "Bash(npm publish:*)", "Bash(gh release:*)"],
)
def test_settings_requires_human_approval(rule: str) -> None:
    """O gate humano do `/deploy` e' o prompt de permissao do Claude Code."""
    settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    assert rule in settings["permissions"]["ask"], f"{rule} deve estar em permissions.ask"
