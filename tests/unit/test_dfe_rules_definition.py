"""Validacao estrutural das rules dfe-rules.

Pre-Sprint 11: 5 regras (a regra 3 era "Sempre executar
``python -m src.collector --once``"). Sprint 11 D.4 removeu essa regra
(contradizia gate em ``dev/pre_tool_use.py``). Hoje: 4 regras
numeradas; nota explicativa menciona a regra removida.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

RULES_FILE: Path = Path(__file__).resolve().parents[2] / ".opencode" / "rules" / "dfe-rules.md"


@pytest.fixture(scope="module")
def rules_text() -> str:
    assert RULES_FILE.exists(), f"Arquivo {RULES_FILE} nao existe"
    return RULES_FILE.read_text(encoding="utf-8")


def test_rules_file_exists():
    assert RULES_FILE.exists()


def test_rules_has_exactly_4_ordered_items(rules_text: str):
    """Sprint 11 D.4: regra 3 ("collector --once") removida; 4 regras restantes."""
    items = re.findall(r"^\d+\.\s+\*\*", rules_text, re.MULTILINE)
    assert len(items) == 4, (
        f"Esperado 4 itens ordenados (1. a 4.); encontrado {len(items)}: {items}. "
        f"Regra 3 (collector --once) foi removida em Sprint 11 D.4."
    )


def test_each_item_has_bold_phrase(rules_text: str):
    bold_phrases = re.findall(r"\*\*[^*]+\*\*", rules_text)
    assert len(bold_phrases) >= 4, (
        f"Esperado >= 4 frases em negrito, encontrado {len(bold_phrases)}: {bold_phrases}"
    )


def test_rules_contains_required_literals(rules_text: str):
    required = [
        "ALLOWED_DOMAINS",
        "has_sufficient_evidence",
        "Nao encontrei base para responder",
        "Fontes:",
    ]
    for s in required:
        assert s in rules_text, f"Arquivo deve conter '{s}'"


def test_rules_no_longer_mandates_collector_invocation(rules_text: str) -> None:
    """Sprint 11 D.4: regra "Sempre executar collector --once" foi removida.

    A regra continua documentada em ``.opencode/skills/dfe-fiscal/SKILL.md``
    (Passo 2 do workflow canonico), mas NAO como regra obrigatoria
    pre-resposta (contradizia o gate ``dev/pre_tool_use.py``).
    """
    assert "Sempre executar" not in rules_text or "PLAN_SPRINT11" in rules_text, (
        "Regra 'Sempre executar' deve aparecer apenas em nota historica "
        "(PLAN_SPRINT11), nao como regra obrigatoria."
    )
