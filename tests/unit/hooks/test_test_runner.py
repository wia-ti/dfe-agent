"""Testes do helper `.opencode/hooks/_lib/test_runner.py` (PLAN_SPRINT10 B.4 + PLAN_SPRINT11 C + Sprint 12 B12.1).

Cobre `suites_for_path(rel_path, agent)`:

- ``agent="dev"`` (Sprint 10) retorna TODAS as suites aplicaveis (uniao de
  backend + ml) para qualquer path do projeto.
- Slugs legacy (``backend-engineer``, ``ml-engineer``) retornam suite vazia
  (removidos em Sprint 11 C.2; cobertura anti-regressao).
- Paths desconhecidos retornam lista vazia.
- `run_pytest` retorna `(0, "[skip] nenhuma suite aplicavel")` quando a
  lista de suites e' vazia.

> **Sprint 12 (B12.1)**: helper movido de ``.claude/hooks/_lib/`` para
> ``.opencode/hooks/_lib/``.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]
TEST_RUNNER: Path = PROJECT_ROOT / ".opencode" / "hooks" / "_lib" / "test_runner.py"


def _load():
    spec = importlib.util.spec_from_file_location("test_runner_loaded", TEST_RUNNER)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def tr():
    return _load()


def test_test_runner_module_imports(tr) -> None:
    assert hasattr(tr, "suites_for_path")
    assert hasattr(tr, "run_pytest")


@pytest.mark.parametrize(
    "path,expected_suite",
    [
        ("src/collector/downloader.py", "tests/unit/collector"),
        ("src/parser/pdf_parser.py", "tests/unit/parser"),
        ("src/db/sqlite_storage.py", "tests/unit/db"),
        ("src/query/query_engine.py", "tests/unit/query"),
        ("src/utils/throttler.py", "tests/unit/utils"),
        ("src/ragctl.py", "tests/unit/test_ragctl.py tests/unit/test_ragctl_backfill.py"),
        ("src/indexer/chunker.py", "tests/unit/indexer"),
    ],
)
def test_dev_maps_path_to_applicable_suite(
    tr, path: str, expected_suite: str
) -> None:
    """Sprint 10 B.4: `@dev` em qualquer path do projeto retorna a suite
    pytest correspondente (uniao das tabelas backend + ml)."""
    suites = tr.suites_for_path(path, agent="dev")
    assert expected_suite in suites, (
        f"@dev editou `{path}`; suite esperada `{expected_suite}` "
        f"ausente de {suites}"
    )


@pytest.mark.parametrize("legacy_slug", ["backend-engineer", "ml-engineer"])
def test_legacy_agent_returns_empty(tr, legacy_slug: str) -> None:
    """Sprint 11 C.2: agents legacy removidos nao recebem suite alguma."""
    suites = tr.suites_for_path("src/collector/downloader.py", agent=legacy_slug)
    assert suites == [], (
        f"agent legacy `{legacy_slug}` deveria retornar suite vazia "
        f"(removido em Sprint 11); obtido {suites}"
    )


def test_dev_returns_empty_for_unmatched_path(tr) -> None:
    """Path fora de qualquer tabela (ex.: `.opencode/agent/dev.md`) -> []."""
    suites = tr.suites_for_path(".opencode/agent/dev.md", agent="dev")
    assert suites == [], (
        f"Path fora do escopo de pytest deveria retornar []; obtido {suites}"
    )


def test_dev_dedups_suites(tr) -> None:
    """Mesmo path nao deve retornar a mesma suite 2x (idempotente)."""
    suites = tr.suites_for_path("src/parser/foo.py", agent="dev")
    assert len(suites) == len(set(suites)), (
        f"suites_for_path retornou duplicatas: {suites}"
    )


def test_run_pytest_with_empty_suites_returns_skip(tr) -> None:
    rc, output = tr.run_pytest([])
    assert rc == 0
    assert "skip" in output.lower()
