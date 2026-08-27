"""Testes unit dos helpers ``_lib/payload.py::_AGENT_HINTS`` e ``_lib/test_runner.py::suites_for_path``
para o agent `deployer` (PLAN_SPRINT18 / Task 2.5).

Cobre:

- `_AGENT_HINTS` reconhece `deployer` no payload.
- Lookahead negativo evita match em `deployed`/`deploying`.
- `suites_for_path("packages/dfe-agent/src/foo.ts", agent="deployer")` retorna [].
- `suites_for_path("src/foo.py", agent="deployer")` retorna [] (deployer
  NAO roda pytest).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]

# Adiciona path para _lib
sys.path.insert(
    0,
    str(PROJECT_ROOT / ".opencode" / "hooks"),
)

from _lib.payload import detect_active_agent  # type: ignore[no-redef]
from _lib.test_runner import suites_for_path  # type: ignore[no-redef]


# ============================================================
# _AGENT_HINTS — deteccao de slug
# ============================================================


def test_detect_deployer_from_env() -> None:
    """`DFE_ACTIVE_AGENT=deployer` deve fazer detect_active_agent retornar deployer."""
    old_env = os.environ.get("DFE_ACTIVE_AGENT")
    os.environ["DFE_ACTIVE_AGENT"] = "deployer"
    try:
        agent = detect_active_agent({}, hook_dir_name="dev")
        assert agent == "deployer", (
            f"Esperado 'deployer'; obtido {agent!r}"
        )
    finally:
        if old_env is None:
            os.environ.pop("DFE_ACTIVE_AGENT", None)
        else:
            os.environ["DFE_ACTIVE_AGENT"] = old_env


def test_detect_deployer_from_payload_agent_field() -> None:
    """Campo `agent: deployer` no payload tem precedencia sobre env."""
    agent = detect_active_agent({"agent": "deployer"}, hook_dir_name="dev")
    assert agent == "deployer"


def test_detect_deployer_lookahead_negative_deployed() -> None:
    """Heuristica NAO deve matchar `deployed` (lookahead evita)."""
    # Le _AGENT_HINTS via introspection
    from _lib.payload import _AGENT_HINTS  # type: ignore[attr-defined]

    deployer_pattern = next(
        (p for slug, p in _AGENT_HINTS if slug == "deployer"), None
    )
    if deployer_pattern is None:
        pytest.fail("deployer nao esta' em _AGENT_HINTS")
    assert not deployer_pattern.search("deployed"), (
        "Pattern deployer NAO deve matchar 'deployed' (lookahead negativo)."
    )
    assert not deployer_pattern.search("deploying"), (
        "Pattern deployer NAO deve matchar 'deploying' (lookahead negativo)."
    )
    assert not deployer_pattern.search("deployment"), (
        "Pattern deployer NAO deve matchar 'deployment' (lookahead negativo)."
    )


def test_detect_deployer_lookahead_negative_matches_correctly() -> None:
    """Heuristica DEVE matchar `deployer` puro."""
    from _lib.payload import _AGENT_HINTS  # type: ignore[attr-defined]

    deployer_pattern = next(
        (p for slug, p in _AGENT_HINTS if slug == "deployer"), None
    )
    if deployer_pattern is None:
        pytest.fail("deployer nao esta' em _AGENT_HINTS")
    assert deployer_pattern.search("deployer"), (
        "Pattern deployer DEVE matchar 'deployer'."
    )
    assert deployer_pattern.search("the deployer agent"), (
        "Pattern deployer DEVE matchar em contexto."
    )


# ============================================================
# suites_for_path — branch deployer
# ============================================================


def test_suites_for_path_deployer_returns_empty_for_packages_dfe_agent() -> None:
    """deployer NAO roda pytest em packages/dfe-agent/src/foo.ts."""
    suites = suites_for_path(
        "packages/dfe-agent/src/query/index.ts", agent="deployer"
    )
    assert suites == [], (
        f"deployer deveria retornar suite vazia; obtido {suites}"
    )


def test_suites_for_path_deployer_returns_empty_for_src() -> None:
    """deployer NAO roda pytest em src/foo.py."""
    suites = suites_for_path("src/indexer/foo.py", agent="deployer")
    assert suites == [], (
        f"deployer deveria retornar suite vazia; obtido {suites}"
    )


def test_suites_for_path_deployer_returns_empty_for_tests() -> None:
    """deployer NAO roda pytest em tests/ mesmo."""
    suites = suites_for_path("tests/unit/foo.py", agent="deployer")
    assert suites == [], (
        f"deployer deveria retornar suite vazia; obtido {suites}"
    )


def test_suites_for_path_dev_still_returns_all_suites() -> None:
    """Sanity: dev continua retornando suites (gate anti-regressao)."""
    suites = suites_for_path("src/indexer/foo.py", agent="dev")
    assert len(suites) > 0, (
        f"dev deveria retornar suites para src/indexer/; obtido {suites}"
    )
    assert any("indexer" in s for s in suites), (
        f"dev deveria incluir suite indexer; obtido {suites}"
    )