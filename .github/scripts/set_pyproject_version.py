"""Atualiza ``[project].version`` do pyproject.toml (prepareCmd do semantic-release).

Uso: python .github/scripts/set_pyproject_version.py 1.3.0
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PYPROJECT: Path = Path(__file__).resolve().parents[2] / "pyproject.toml"
_SEMVER: re.Pattern[str] = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
_VERSION_LINE: re.Pattern[str] = re.compile(r'(?m)^(version\s*=\s*")[^"]*(")')
_PROJECT_TABLE: re.Pattern[str] = re.compile(r"(?ms)^\[project\]\s*$(.*?)(?=^\[|\Z)")


def set_version(text: str, version: str) -> str:
    """Troca ``version = "..."`` dentro da tabela ``[project]``."""
    if not _SEMVER.match(version):
        raise ValueError(f"versao invalida: {version!r}")
    table = _PROJECT_TABLE.search(text)
    if table is None:
        raise ValueError("tabela [project] nao encontrada no pyproject.toml")
    body, n = _VERSION_LINE.subn(rf"\g<1>{version}\g<2>", table.group(1), count=1)
    if n != 1:
        raise ValueError("linha `version = \"...\"` nao encontrada em [project]")
    return text[: table.start(1)] + body + text[table.end(1):]


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    PYPROJECT.write_text(set_version(PYPROJECT.read_text(encoding="utf-8"), argv[0]), encoding="utf-8")
    print(f"pyproject.toml -> {argv[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
