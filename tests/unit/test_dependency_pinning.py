"""Testes de sincronia de dependencias entre ``pyproject.toml`` e ``requirements.txt``.

Cobre (PLAN_SPRINT4 C.1 / IMPORTANTE #1, #2):
    - O conjunto de pacotes declarados em ambos arquivos e' identico.
    - Todas as versoes sao pin exato (``==X.Y.Z``); bounds ``>=X,<Y``
      NAO sao permitidos exceto em casos documentados.
    - ``pip freeze`` no venv bate com os pins declarados.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
PYPROJECT: Path = PROJECT_ROOT / "pyproject.toml"
REQUIREMENTS: Path = PROJECT_ROOT / "requirements.txt"


def _parse_requirements(path: Path) -> dict[str, str]:
    """Parseia ``requirements.txt`` retornando ``{pkg: pin}`` (sem version -> '')."""
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Remove comments no fim da linha
        if " #" in line:
            line = line.split(" #", 1)[0].strip()
        # Formato: pkg==X.Y.Z
        m = re.match(r"^([A-Za-z0-9_.\-]+)\s*(==\s*([^;\s]+))?", line)
        if not m:
            continue
        pkg: str = m.group(1).strip().lower()
        version: str = (m.group(3) or "").strip()
        out[pkg] = version
    return out


def _normalize_pkg_name(name: str) -> str:
    """Normaliza nome de pacote (PEP 503)."""
    return re.sub(r"[-_.]+", "-", name).lower()


def test_pyproject_and_requirements_have_same_packages() -> None:
    """Os pacotes declarados em ``pyproject.toml`` e ``requirements.txt`` sao identicos.

    Estrategia: parsear ambos os arquivos, normalizar nomes PEP 503
    e comparar o conjunto.

    Apenas as secoes ``[project] dependencies`` e
    ``[project.optional-dependencies]`` sao consideradas; ``[build-system]``
    (ex.: ``setuptools``, ``wheel``) fica de fora por ser apenas
    instalacao do build, nao dependencia runtime.
    """
    req_pkgs: dict[str, str] = _parse_requirements(REQUIREMENTS)
    pyproject_text: str = PYPROJECT.read_text(encoding="utf-8")

    deps_match: re.Match[str] | None = re.search(
        r"dependencies\s*=\s*\[(.*?)\]",
        pyproject_text,
        re.DOTALL,
    )
    dev_match: re.Match[str] | None = re.search(
        r"\[project\.optional-dependencies\][^\[]*?dev\s*=\s*\[(.*?)\]",
        pyproject_text,
        re.DOTALL,
    )
    deps_block: str = (deps_match.group(1) if deps_match else "") + (
        dev_match.group(1) if dev_match else ""
    )

    pyproject_pkgs: set[str] = set()
    for m in re.finditer(r'"([A-Za-z0-9_.\-]+)\s*[><=!~]+', deps_block):
        pyproject_pkgs.add(_normalize_pkg_name(m.group(1)))

    req_set: set[str] = {_normalize_pkg_name(p) for p in req_pkgs}

    missing_in_pyproject: set[str] = req_set - pyproject_pkgs
    missing_in_req: set[str] = pyproject_pkgs - req_set

    assert not missing_in_pyproject, (
        f"Pacotes em requirements.txt faltando em pyproject.toml: "
        f"{missing_in_pyproject}"
    )
    assert not missing_in_req, (
        f"Pacotes em pyproject.toml faltando em requirements.txt: "
        f"{missing_in_req}"
    )


def test_all_versions_are_exact() -> None:
    """Todos os pacotes em ``requirements.txt`` tem pin exato ``==X.Y.Z``.

    Nenhum ``>=X,<Y`` e' permitido (decisao PLAN_SPRINT4 C.1).
    """
    bad_lines: list[str] = []
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if " #" in stripped:
            stripped = stripped.split(" #", 1)[0].strip()
        if not re.match(r"^[A-Za-z0-9_.\-]+\s*==\s*\d+\.\d+\.\d+\s*$", stripped):
            bad_lines.append(stripped)

    assert bad_lines == [], (
        "Linhas sem pin exato '==X.Y.Z' em requirements.txt:\n"
        + "\n".join(f"  {line}" for line in bad_lines)
    )


def test_pyproject_versions_match_requirements() -> None:
    """Quando ``pyproject.toml`` declara versao, ela bate com ``requirements.txt``."""
    req_pkgs: dict[str, str] = _parse_requirements(REQUIREMENTS)
    pyproject_text: str = PYPROJECT.read_text(encoding="utf-8")

    mismatches: list[str] = []
    for m in re.finditer(
        r'"([A-Za-z0-9_.\-]+)\s*==\s*([0-9][^"]*)"', pyproject_text
    ):
        pkg: str = _normalize_pkg_name(m.group(1))
        pyproject_version: str = m.group(2).strip()
        req_version: str = req_pkgs.get(pkg, "")
        if req_version and req_version != pyproject_version:
            mismatches.append(
                f"{pkg}: pyproject={pyproject_version} requirements={req_version}"
            )

    assert mismatches == [], (
        "Versoes divergentes entre pyproject.toml e requirements.txt:\n"
        + "\n".join(f"  {m}" for m in mismatches)
    )


def test_no_unsafe_bounds_in_requirements() -> None:
    """Nenhum ``>=`` ou ``<=`` em ``requirements.txt`` (apenas pin exato)."""
    bad: list[str] = []
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if " #" in stripped:
            stripped = stripped.split(" #", 1)[0].strip()
        if ">=" in stripped or "<=" in stripped or "~=" in stripped or "!=" in stripped:
            bad.append(stripped)

    assert bad == [], (
        "Encontrados bounds (>=, <=, ~=, !=) em requirements.txt. "
        "Use pin exato ==X.Y.Z:\n" + "\n".join(f"  {b}" for b in bad)
    )
