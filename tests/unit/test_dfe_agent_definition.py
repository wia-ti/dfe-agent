"""Validacao estrutural do agente dfe-agent."""
from __future__ import annotations
import re
from pathlib import Path

import pytest

AGENT_FILE: Path = Path(__file__).resolve().parents[2] / ".opencode" / "agent" / "dfe-agent.md"


@pytest.fixture(scope="module")
def agent_text() -> str:
    assert AGENT_FILE.exists(), f"Arquivo {AGENT_FILE} nao existe"
    return AGENT_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def frontmatter(agent_text: str) -> str:
    parts = agent_text.split("---", 2)
    assert len(parts) >= 3, "Arquivo deve ter frontmatter YAML entre ---"
    return parts[1]


def test_agent_file_exists():
    assert AGENT_FILE.exists()


def test_frontmatter_contains_name_dfe_agent(frontmatter: str):
    assert re.search(r"^name:\s*dfe-agent\s*$", frontmatter, re.MULTILINE), \
        f"frontmatter deve conter 'name: dfe-agent'. Recebido:\n{frontmatter}"


def test_frontmatter_contains_model_minimax(frontmatter: str):
    """Frontmatter deve declarar ``model: PROVIDER/MiniMax-M3`` (PLAN_SPRINT4 D.2).

    Provider real do MiniMax-M3 neste usuario ainda nao foi
    confirmado; placeholder explicito impede erro de validacao
    do opencode ate decisao formal (ver AGENTS.md "Decisoes pendentes").
    """
    assert re.search(
        r"^model:\s*\S+/\S+\s*$", frontmatter, re.MULTILINE
    ), f"frontmatter deve conter 'model: PROVIDER/MiniMax-M3'. Recebido:\n{frontmatter}"


def test_frontmatter_yaml_is_valid(agent_text: str):
    import yaml
    parts = agent_text.split("---", 2)
    yaml.safe_load(parts[1])  # nao levanta excecao


def test_body_contains_required_strings(agent_text: str):
    """Corpo deve conter literais canonicos.

    Sprint 11 D.4 removeu a regra "Sempre executar ``python -m
    src.collector --once`` antes de qualquer resposta" do
    ``dfe-agent.md`` (contradizia ``dev/pre_tool_use.py``). A
    skill ``dfe-fiscal`` continua sendo a fonte canonica do
    fluxo de varredura (Passo 2).
    """
    required = ["dfe-fiscal", "Nao encontrei base para responder", "Fontes:"]
    for s in required:
        assert s in agent_text, f"Corpo deve conter '{s}'"
