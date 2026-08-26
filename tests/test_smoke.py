"""Smoke test de scaffold: verifica que o entry point sobe e os modulos importam.

Criterio de conclusao (Fase 1 do PLAN.md):
    `python -c "import src.collector, src.parser, src.indexer, src.query, src.db, src.utils"`
    retorna exit code 0.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
EXPECTED_PACKAGES: tuple[str, ...] = (
    "src.collector",
    "src.parser",
    "src.indexer",
    "src.query",
    "src.db",
    "src.utils",
)


def test_all_src_packages_importable() -> None:
    """Cada pacote de src/ deve ser importavel sem erro."""
    for package_name in EXPECTED_PACKAGES:
        __import__(package_name)


def test_health_endpoint_reports_healthy() -> None:
    """`python main.py --health` deve reportar status 'healthy' e exit code 0."""
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "main.py"), "--health"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        check=False,
    )

    assert result.returncode == 0, (
        f"main.py --health falhou (exit={result.returncode}).\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    payload = json.loads(result.stdout)
    assert payload["status"] == "healthy"
    assert payload["python_ok"] is True
    assert payload["project"] == "DFe-Agent"
    assert set(payload["packages"].keys()) == set(EXPECTED_PACKAGES)
    assert all(status == "ok" for status in payload["packages"].values())


def test_main_without_args_prints_help_and_exits_zero() -> None:
    """`python main.py` sem argumentos deve exibir ajuda e retornar exit 0."""
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "main.py")],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        check=False,
    )

    assert result.returncode == 0
    assert "usage" in result.stdout.lower() or "--health" in result.stdout


@pytest.mark.parametrize("package_name", EXPECTED_PACKAGES)
def test_each_package_has_init(package_name: str) -> None:
    """Cada pacote deve possuir __init__.py (regressao contra scaffold incompleto)."""
    package_path = PROJECT_ROOT / Path(*package_name.split(".")) / "__init__.py"
    assert package_path.is_file(), f"__init__.py ausente em {package_path}"
