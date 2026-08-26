"""Testes da whitelist de scripts canonicos (PLAN_SPRINT5 F.2).

Garante que:

- ``.gitignore`` bloqueia ``scripts/*.py`` por default.
- ``.gitignore`` permite explicitamente apenas ``scripts/demo_cli.py``
  (whitelist para impedir scripts ad-hoc futuros).
- Diretorio ``scripts/`` contem APENAS o canonico ``demo_cli.py``
  (sem ad-hoc residuais como ``answer_nf_e_10_2026.py``,
  ``buscar_dfereferenciado.py``, ``demo_query.py``,
  ``demo_query_2026.py``, descartados em F.2).

Origem do problema (achado da revisao de 2026-08-25):
    4 scripts ad-hoc foram gerados pelo proprio agente LLM apos o
    CLI ``python -m src.query`` retornar ``NO_EVIDENCE_MESSAGE`` em
    razao de ``OSError 1455`` no load do embedding (ver F.1). O
    agente interpretou "sem evidencia" como "CLI quebrado" e escreveu
    SQL raw no DB, contornando o guardrail de veracidade. O
    whitelist no ``.gitignore`` impede reincidencia.
"""
from __future__ import annotations

from pathlib import Path

import pytest


PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
GITIGNORE_PATH: Path = PROJECT_ROOT / ".gitignore"
SCRIPTS_DIR: Path = PROJECT_ROOT / "scripts"


def test_gitignore_blocks_adhoc_scripts() -> None:
    """.gitignore contem regra ``scripts/*.py`` + whitelist ``!scripts/demo_cli.py``."""
    content: str = GITIGNORE_PATH.read_text(encoding="utf-8")

    has_block: bool = any(
        line.strip() == "scripts/*.py" or line.strip() == "scripts/*.py "
        for line in content.splitlines()
    )
    assert has_block, (
        f".gitignore deveria conter regra 'scripts/*.py' (bloqueio default). "
        f"Conteudo relevante: {[l for l in content.splitlines() if 'scripts' in l]}"
    )

    has_whitelist: bool = any(
        line.strip() == "!scripts/demo_cli.py" or line.strip() == "!scripts/demo_cli.py "
        for line in content.splitlines()
    )
    assert has_whitelist, (
        ".gitignore deveria conter whitelist '!scripts/demo_cli.py' "
        "(permitir apenas o canonico)"
    )


def test_scripts_dir_only_canonics() -> None:
    """Diretorio ``scripts/`` contem APENAS ``demo_cli.py`` (sem ad-hoc residuais)."""
    if not SCRIPTS_DIR.exists():
        pytest.skip("Diretorio scripts/ nao existe")

    py_files: list[Path] = sorted(SCRIPTS_DIR.glob("*.py"))
    py_names: list[str] = [p.name for p in py_files]

    assert py_names == ["demo_cli.py"], (
        f"scripts/ deveria conter apenas 'demo_cli.py'. Encontrado: {py_names}. "
        f"Os 4 scripts ad-hoc (answer_nf_e_10_2026.py, buscar_dfereferenciado.py, "
        f"demo_query.py, demo_query_2026.py) foram descartados em F.2."
    )


def test_no_adhoc_scripts_referenced_in_repo() -> None:
    """Nenhum dos 4 scripts ad-hoc descartados e' referenciado em codigo/docs."""
    forbidden_names: set[str] = {
        "answer_nf_e_10_2026.py",
        "buscar_dfereferenciado.py",
        "demo_query.py",
        "demo_query_2026.py",
    }

    py_files: list[Path] = sorted(SCRIPTS_DIR.glob("*.py")) if SCRIPTS_DIR.exists() else []
    for p in py_files:
        assert p.name not in forbidden_names, (
            f"Script ad-hoc descartado em F.2 nao deveria existir: {p.name}"
        )


__all__ = [
    "test_gitignore_blocks_adhoc_scripts",
    "test_scripts_dir_only_canonics",
    "test_no_adhoc_scripts_referenced_in_repo",
]
