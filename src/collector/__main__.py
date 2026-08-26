"""CLI: ``python -m src.collector [--once] [--dry-run] [--diagnose-net]``.

- ``--once``: instancia ``SqliteStorage`` + ``Throttler`` + ``DocumentCollector``,
  executa ``discover_and_register()`` e ``download_pending()`` e imprime resumo.
- ``--dry-run``: para cada ``source`` conhecida, chama ``discover_documents`` e
  imprime as URLs. NAO acessa o banco, NAO faz download.
- ``--diagnose-net`` (PLAN_SPRINT7 C.1): para cada host em ``ALLOWED_DOMAINS``,
  tenta resolver (DNS) e fazer ``GET https://<host>/`` com ``timeout=5s``.
  Emite JSON com status por host + summary. Exit code: 0 se todos OK, 1 senao.
- sem argumentos: imprime o help e sai com codigo 0.
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import time
import traceback
from pathlib import Path

import requests

from src.collector.downloader import DocumentCollector
from src.collector.portal_index import PORTAL_URLS, discover_documents
from src.db.sqlite_storage import SqliteStorage
from src.utils.throttler import Throttler

_DEFAULT_DB_PATH: Path = Path("storage") / "dfe.db"
_DEFAULT_DATA_DIR: Path = Path("data")
_PROBE_TIMEOUT_S: float = 5.0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dfe-collector",
        description="Coletor de documentacao fiscal eletronica oficial.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Executa uma varredura completa: descoberta + download dos pendentes.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Apenas descobre URLs e imprime. Nao insere no banco nem baixa arquivos.",
    )
    parser.add_argument(
        "--diagnose-net",
        action="store_true",
        help=(
            "Sonda cada host em ALLOWED_DOMAINS (DNS + GET https://<host>/) "
            "e imprime JSON com status por host. Exit 0 senao todos OK."
        ),
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=_DEFAULT_DB_PATH,
        help="Caminho do arquivo SQLite (default: storage/dfe.db).",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=_DEFAULT_DATA_DIR,
        help="Diretorio para arquivos baixados (default: data/).",
    )
    return parser


def _probe_host(host: str, *, timeout_s: float = _PROBE_TIMEOUT_S) -> dict:
    """Sonda DNS + GET em ``host``; retorna dict canonico."""
    started = time.monotonic()
    try:
        socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        return {
            "host": host,
            "resolves": False,
            "reachable": False,
            "latency_ms": 0,
            "error": f"{type(exc).__name__}: {exc}",
        }
    url = f"https://{host}/"
    try:
        response = requests.get(url, timeout=timeout_s, allow_redirects=True)
        latency_ms = int((time.monotonic() - started) * 1000)
        ok = response.status_code < 500
        return {
            "host": host,
            "resolves": True,
            "reachable": ok,
            "latency_ms": latency_ms,
            "error": None if ok else f"HTTP {response.status_code}",
        }
    except requests.RequestException as exc:
        latency_ms = int((time.monotonic() - started) * 1000)
        return {
            "host": host,
            "resolves": True,
            "reachable": False,
            "latency_ms": latency_ms,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _run_diagnose_net() -> int:
    """Itera ``ALLOWED_DOMAINS`` e imprime JSON com status por host.

    Exit: 0 se todos reachable, 1 senao. Saida em UTF-8 explicito via
    ``sys.stdout.reconfigure`` quando suportado (cp1252 em PowerShell
    quebraria a impressao de acentos em mensagens de erro).
    """
    from hooks.allowed_domains import ALLOWED_DOMAINS

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    try:
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

    hosts = list(ALLOWED_DOMAINS)
    entries = [_probe_host(h) for h in hosts]
    summary = {
        "total": len(entries),
        "resolves": sum(1 for e in entries if e["resolves"]),
        "reachable": sum(1 for e in entries if e["reachable"]),
    }
    payload = {"hosts": entries, "summary": summary}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if summary["reachable"] == summary["total"] else 1


def _categorize_request_error(exc: BaseException) -> str:
    """Traduz uma excecao de rede para uma string canonica por host.

    Usado em ``discover_and_register`` (origem: PLAN_SPRINT7 C.2) para que
    erros de DNS / timeout / 403 sejam distinguiveis na saida do CLI
    em vez de um traceback urllib3 generico.
    """
    name = type(exc).__name__
    text = str(exc)
    if (
        "NameResolutionError" in text
        or "getaddrinfo failed" in text
        or "Name or service not known" in text
    ):
        return f"NameResolutionError: host nao resolve no DNS publico ({name})"
    if "ConnectTimeout" in name or "timeout" in text.lower():
        return f"Timeout: host nao respondeu em <= 5s ({name})"
    if "ConnectionRefused" in name or "Connection refused" in text:
        return f"ConnectionRefused: porta 443 fechada ({name})"
    return f"{name}: {text}"


def _run_dry_run(throttler: Throttler) -> int:
    """Para cada source conhecida, descobre URLs e imprime. Sem I/O em banco/arquivo."""
    total: int = 0
    for source in PORTAL_URLS:
        try:
            docs = discover_documents(source, throttler)
        except requests.RequestException as exc:
            print(
                f"[{source}] erro HTTP: {_categorize_request_error(exc)}",
                file=sys.stderr,
            )
            continue
        for doc in docs:
            print(f"[{source}] {doc['url']} :: {doc['title']}")
            total += 1
    print(f"# dry-run: {total} documento(s) listado(s).")
    return 0


def _run_once(db_path: Path, data_dir: Path) -> int:
    """Descoberta + download com persistencia no SQLite."""
    storage = SqliteStorage(db_path)
    storage.init_schema()
    throttler = Throttler()
    collector = DocumentCollector(storage, throttler, data_dir)

    registered = collector.discover_and_register()
    print(f"# registrados: {registered}")

    downloaded = collector.download_pending()
    print(f"# baixados: {downloaded}")

    pending_left = sum(1 for _ in storage.list_pending())
    print(f"# pendentes restantes: {pending_left}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada. Retorna o codigo de saida do processo."""
    # Lazy import (mesma razao do query.__main__: nao regredir testes que
    # importam o modulo sem ``.opencode`` em PYTHONPATH).
    from src.utils.http_guard_bootstrap import install_guard_once

    install_guard_once()
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.diagnose_net:
            return _run_diagnose_net()
        if args.dry_run:
            throttler = Throttler()
            return _run_dry_run(throttler)
        if args.once:
            return _run_once(args.db, args.data_dir)
        parser.print_help()
        return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
