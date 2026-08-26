"""Validacao estrutural da skill dfe-fiscal."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_FILE: Path = (
    Path(__file__).resolve().parents[2]
    / ".opencode" / "skills" / "dfe-fiscal" / "SKILL.md"
)


@pytest.fixture(scope="module")
def skill_text() -> str:
    assert SKILL_FILE.exists(), f"Arquivo {SKILL_FILE} nao existe"
    return SKILL_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def frontmatter(skill_text: str) -> str:
    parts = skill_text.split("---", 2)
    assert len(parts) >= 3, "Arquivo deve ter frontmatter YAML entre ---"
    return parts[1]


def test_skill_file_exists():
    assert SKILL_FILE.exists()


def test_frontmatter_contains_name_dfe_fiscal(frontmatter: str):
    assert re.search(r"^name:\s*dfe-fiscal\s*$", frontmatter, re.MULTILINE), \
        f"frontmatter deve conter 'name: dfe-fiscal'. Recebido:\n{frontmatter}"


def test_frontmatter_yaml_is_valid(skill_text: str):
    import yaml
    parts = skill_text.split("---", 2)
    parsed = yaml.safe_load(parts[1])
    assert parsed["name"] == "dfe-fiscal"
    assert "description" in parsed


def test_body_cites_required_classes_and_modules(skill_text: str):
    required = ["DocumentCollector", "RagIndexer", "QueryEngine", "src.collector", "src.indexer.ingest", "src.query"]
    for s in required:
        assert s in skill_text, f"Corpo deve citar '{s}'"


def test_each_documented_command_imports_without_error():
    """Cada comando documentado existe como entry-point."""
    for module in ["src.collector.__main__", "src.indexer.ingest", "src.query.__main__"]:
        result = subprocess.run(
            [sys.executable, "-c", f"import {module}"],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0, (
            f"import {module} falhou (exit={result.returncode}). "
            f"stderr:\n{result.stderr}"
        )