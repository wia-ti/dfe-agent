"""Validacao estrutural do papel ``@dev`` no Claude Code.

No Claude Code o ``@dev`` e' a sessao principal (subagents nao podem delegar
ao ``code-reviewer``), documentada em ``CLAUDE.md`` > "Agente padrao". Cobre:

- ``CLAUDE.md`` existe e tem a secao do ``@dev``.
- A secao documenta os 3 slash commands, RAG antes/depois, sub-delegacao ao
  ``code-reviewer`` e as invariantes "Nunca fazer".
- Nao existe subagent ``dev`` concorrente em ``.claude/agents/``.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT: Path = Path(__file__).resolve().parents[2]
CLAUDE_MD: Path = ROOT / "CLAUDE.md"


@pytest.fixture(scope="module")
def claude_text() -> str:
    assert CLAUDE_MD.exists(), f"{CLAUDE_MD} nao existe"
    return CLAUDE_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def dev_section(claude_text: str) -> str:
    match = re.search(r"^## Agente padrao \(`@dev`\)\n(.*?)(?=^## )", claude_text, re.MULTILINE | re.DOTALL)
    assert match, "CLAUDE.md deve ter a secao '## Agente padrao (`@dev`)'."
    return match.group(1)


def test_no_competing_dev_subagent() -> None:
    assert not (ROOT / ".claude" / "agents" / "dev.md").exists(), (
        "@dev e' a sessao principal; um subagent `dev` nao conseguiria delegar ao code-reviewer."
    )


def test_section_mentions_all_three_slash_commands(claude_text: str) -> None:
    for cmd in ("/feature", "/bug", "/duvida"):
        assert cmd in claude_text, f"CLAUDE.md deve mencionar `{cmd}`."


def test_section_mentions_rag_before_and_after(dev_section: str) -> None:
    assert re.search(r"RAG\s+antes", dev_section, re.IGNORECASE)
    assert re.search(r"RAG\s+depois", dev_section, re.IGNORECASE)


def test_section_mentions_subagent_code_reviewer(dev_section: str) -> None:
    assert "code-reviewer" in dev_section


def test_section_commits_but_does_not_push(dev_section: str) -> None:
    """Sprint 20: o `@dev` commita (Conventional Commits); push e' do `/deploy`."""
    text = dev_section.lower()
    assert "conventional commits" in text
    assert "nao faz push" in text


def test_claude_md_mentions_never_make_invariants(claude_text: str) -> None:
    assert "Inventar informacao" in claude_text
    assert "ALLOWED_DOMAINS" in claude_text
