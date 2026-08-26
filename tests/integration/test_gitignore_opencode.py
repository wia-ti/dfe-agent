"""Gate anti-regressao: `.opencode/node_modules/` listado em `.gitignore` (PLAN_SPRINT11 E.2).

Pre-Sprint 11: `.gitignore` cobria `.claude/node_modules/` (linha 82) e
`node_modules/` na raiz, mas NAO `.opencode/node_modules/` (55 MB de
deps do SDK `@opencode-ai/plugin`). Latente ate inicializar git repo.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
GITIGNORE: Path = PROJECT_ROOT / ".gitignore"


@pytest.fixture(scope="module")
def gitignore_text() -> str:
    assert GITIGNORE.exists(), f"{GITIGNORE} nao encontrado"
    return GITIGNORE.read_text(encoding="utf-8")


def _pattern_matches(path_text: str, gitignore_text: str) -> bool:
    """Verifica se ``path_text`` casa com alguma regra do ``.gitignore``.

    Implementacao simplificada: ignora `.gitignore` patterns avancados
    (negacao `!`, escape `\\`, etc.) e usa busca por substring na linha
    (depois de strip do comentario trailing). Suficiente para o gate.
    """
    for raw_line in gitignore_text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line or line.startswith("!"):
            continue
        # Normalizar pattern: trim espacos, suportar prefixo `/`
        pattern = line.lstrip("/").rstrip("/")
        if not pattern:
            continue
        # Match exato ou como prefixo de diretorio (path acaba com `/`)
        if pattern == path_text or path_text.startswith(pattern + "/"):
            return True
    return False


def test_opencode_node_modules_ignored(gitignore_text: str) -> None:
    """Path ``.opencode/node_modules/foo`` deve casar com regra do .gitignore."""
    assert _pattern_matches(".opencode/node_modules", gitignore_text), (
        ".gitignore deve cobrir '.opencode/node_modules/' "
        "(PLAN_SPRINT11 B11.4). Sem isso, 55 MB de deps do SDK "
        "@opencode-ai/plugin seriao commitados."
    )


def test_opencode_package_lock_ignored(gitignore_text: str) -> None:
    """Path ``.opencode/package-lock.json`` deve casar com regra do .gitignore."""
    assert _pattern_matches(".opencode/package-lock.json", gitignore_text), (
        ".gitignore deve cobrir '.opencode/package-lock.json' "
        "(output de npm install; PLAN_SPRINT11 B11.4)."
    )


def test_gitignore_blocks_recursive_pattern(gitignore_text: str) -> None:
    """Pattern deve ser recursivo (cobre subpath, nao so o root)."""
    assert _pattern_matches(".opencode/node_modules/@opencode-ai/plugin/dist", gitignore_text), (
        "Pattern do .gitignore deve cobrir paths recursivos "
        "(ex.: `.opencode/node_modules/@opencode-ai/plugin/dist/...`)."
    )
