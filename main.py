from __future__ import annotations

import argparse
import json
import platform
import sys
from importlib import import_module
from typing import TypedDict

PROJECT_NAME: str = "DFe-Agent"
PYTHON_MIN: tuple[int, int] = (3, 11)
HEALTHY_PACKAGES: tuple[str, ...] = (
    "src.collector",
    "src.parser",
    "src.indexer",
    "src.query",
    "src.db",
    "src.utils",
)


class HealthReport(TypedDict):
    status: str
    project: str
    python_version: str
    python_ok: bool
    packages: dict[str, str]


def _check_python_version() -> tuple[bool, str]:
    major, minor, _ = platform.python_version_tuple()
    current = (int(major), int(minor))
    version_str = f"{current[0]}.{current[1]}"
    return current >= PYTHON_MIN, version_str


def _check_package_imports() -> dict[str, str]:
    statuses: dict[str, str] = {}
    for package_name in HEALTHY_PACKAGES:
        try:
            import_module(package_name)
            statuses[package_name] = "ok"
        except Exception as exc:  # noqa: BLE001
            statuses[package_name] = f"error: {exc.__class__.__name__}"
    return statuses


def collect_health() -> HealthReport:
    python_ok, python_version = _check_python_version()
    packages = _check_package_imports()
    all_packages_ok = all(status == "ok" for status in packages.values())
    is_healthy = python_ok and all_packages_ok
    return HealthReport(
        status="healthy" if is_healthy else "unhealthy",
        project=PROJECT_NAME,
        python_version=python_version,
        python_ok=python_ok,
        packages=packages,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dfe-agent",
        description=(
            "DFe-Agent: ponto de entrada operacional. "
            "Use --health para verificar se o ambiente esta pronto."
        ),
    )
    parser.add_argument(
        "--health",
        action="store_true",
        help="Verifica versao do Python e importabilidade dos modulos do projeto.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emite o relatorio de saude em JSON (implicito com --health).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.health:
        parser.print_help()
        return 0

    report = collect_health()
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "healthy" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
