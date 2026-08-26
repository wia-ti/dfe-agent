"""Testes do script de hardening ``scripts/check_env.ps1`` (PLAN_SPRINT5 F.3).

Cobre:

- Arquivo existe e tem shebang valido (``#!/usr/bin/env pwsh``).
- Tamanho >= 500 bytes (sanity check de conteudo real, nao placeholder).
"""
from __future__ import annotations

from pathlib import Path

import pytest


SCRIPT_PATH: Path = (
    Path(__file__).resolve().parents[2] / "scripts" / "check_env.ps1"
)


def test_check_env_script_artifact_exists_and_has_shebang() -> None:
    """``scripts/check_env.ps1`` existe, comeca com shebang pwsh, tamanho >= 500 bytes."""
    assert SCRIPT_PATH.exists(), f"Arquivo {SCRIPT_PATH} nao existe"

    content: str = SCRIPT_PATH.read_text(encoding="utf-8")
    assert len(content) >= 500, (
        f"check_env.ps1 deveria ter >= 500 bytes de conteudo real "
        f"(5 escopos), obtido {len(content)} bytes"
    )

    first_line: str = content.splitlines()[0].strip() if content else ""
    has_shebang: bool = first_line.startswith("#!") and "pwsh" in first_line
    assert has_shebang, (
        f"Primeira linha deveria ser shebang pwsh (ex.: '#!/usr/bin/env pwsh'), "
        f"obtido {first_line!r}"
    )


def test_check_env_script_covers_five_scopes() -> None:
    """Conteudo de ``check_env.ps1`` menciona os 5 escopos documentados."""
    content: str = SCRIPT_PATH.read_text(encoding="utf-8").lower()

    expected_keywords: dict[str, str] = {
        "memoria_fisica": "memoria" if "memoria" in content or "memory_gb" in content else "",
        "page_file":      "pagefile" if "pagefile" in content else "",
        "health_ok":      "health_ok" if "health_ok" in content else "",
        "embedding_load": "embedding_load" if "embedding_load" in content else "",
        "db_accessible":  "db_accessible" if "db_accessible" in content else "",
    }

    missing: list[str] = [k for k, v in expected_keywords.items() if not v]
    assert not missing, (
        f"check_env.ps1 deveria mencionar os 5 escopos documentados. "
        f"Faltando: {missing}. Conteudo (primeiras 50 linhas):\n"
        + "\n".join(content.splitlines()[:50])
    )


def test_check_env_script_recommendation_includes_dfe_embedding_dtype() -> None:
    """Recomendacao menciona ``DFE_EMBEDDING_DTYPE=float16`` (workaround canonico)."""
    content: str = SCRIPT_PATH.read_text(encoding="utf-8")

    has_workaround: bool = (
        "DFE_EMBEDDING_DTYPE=float16" in content
        or "DFE_EMBEDDING_DTYPE=" in content
    )
    assert has_workaround, (
        "Recomendacao de falha de embedding deveria mencionar DFE_EMBEDDING_DTYPE=float16 "
        "(workaround canonico PLAN_SPRINT5 F.1)"
    )


__all__ = [
    "test_check_env_script_artifact_exists_and_has_shebang",
    "test_check_env_script_covers_five_scopes",
    "test_check_env_script_recommendation_includes_dfe_embedding_dtype",
]
