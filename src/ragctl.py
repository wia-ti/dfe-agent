"""CLI administrativo do DFe-Agent (Sprint 2, Fase 17).

Sub-comandos:
    - migrate: aplica migrations pendentes e reporta user_version.
    - benchmark: roda eval_set e grava report JSON (chama ``src.eval``).
    - reindex: dropa vec_chunks + sidecars (chunk_metadata/fts_chunks/
      doc_summaries de detalhe) e dispara ``python -m src.indexer.ingest``.
    - stats: imprime contadores da base (docs, chunks, summaries, etc.).

Uso:
    $ python -m src.ragctl migrate
    $ python -m src.ragctl benchmark --eval-set path/to/eval.json
    $ python -m src.ragctl reindex --chunker=flat
    $ python -m src.ragctl stats
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import sqlite_vec

from src.db.migrations import CURRENT_VERSION, apply_pending, read_user_version
from src.db.sqlite_storage import SqliteStorage

DEFAULT_STORAGE_DIR: Path = Path("./storage")
DEFAULT_DB_PATH: Path = DEFAULT_STORAGE_DIR / "dfe.db"


def _connect_with_vec(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    return conn


def cmd_migrate(args: argparse.Namespace) -> int:
    db_path: Path = args.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    storage = SqliteStorage(db_path)
    storage.init_schema()
    new_version = apply_pending(db_path)
    print(
        json.dumps(
            {
                "db_path": str(db_path),
                "current_version": new_version,
                "target_version": CURRENT_VERSION,
            },
            indent=2,
        )
    )
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    """Delega para ``python -m src.eval`` (CLI canonica)."""
    cmd: list[str] = [
        sys.executable,
        "-m",
        "src.eval",
        "--eval-set",
        str(args.eval_set),
        "--report",
        str(args.report),
        "--chunker",
        args.chunker,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.returncode


def cmd_reindex(args: argparse.Namespace) -> int:
    """Dropa vetores/indices e dispara ``src.indexer.ingest``.

    Tambem reseta ``documents.status`` para ``nao_ingerido`` para todos
    os docs que possuem ``file_path`` (i.e., podem ser re-ingeridos),
    ja que o ``RagIndexer.ingest_pending`` so processa pendentes.
    Apos o DROP, recria as tabelas de sidecar (vec_chunks vec0,
    chunk_metadata, fts_chunks) para que a ingestao as re-popule.
    """
    db_path: Path = args.db_path
    if not db_path.exists():
        print(f"# DB nao encontrado: {db_path}", file=sys.stderr)
        return 1
    with _connect_with_vec(db_path) as conn:
        try:
            n_reset = conn.execute(
                "UPDATE documents SET status='nao_ingerido', ingested_at=NULL, "
                "content_hash=NULL WHERE file_path IS NOT NULL"
            ).rowcount
            print(f"# Reset: {n_reset} documentos marcados como pendentes.")
        except sqlite3.OperationalError as exc:
            print(f"# Aviso: reset falhou ({exc})", file=sys.stderr)
        # DROP vec_chunks (vec0) e sidecars.
        for table in ("vec_chunks", "chunk_metadata", "fts_chunks"):
            try:
                conn.execute(f"DROP TABLE IF EXISTS {table}")
            except sqlite3.OperationalError:
                pass
        conn.commit()

    # Recria as tabelas dropadas para o ingest poder re-popular.
    from src.db.vector_store import VectorStore
    vs = VectorStore(db_path, dim=384)
    vs.init_schema()

    cmd = [
        sys.executable,
        "-m",
        "src.indexer.ingest",
        "--chunker",
        args.chunker,
    ]
    result = subprocess.run(cmd, check=False)
    return result.returncode


def cmd_stats(args: argparse.Namespace) -> int:
    db_path: Path = args.db_path
    if not db_path.exists():
        print(f"# DB nao encontrado: {db_path}", file=sys.stderr)
        return 1
    with _connect_with_vec(db_path) as conn:
        stats: dict[str, int] = {
            "schema_version": read_user_version(db_path),
        }
        for table in (
            "documents",
            "vec_chunks",
            "chunk_metadata",
            "fts_chunks",
            "doc_summaries",
            "query_cache",
        ):
            try:
                n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                stats[table] = int(n)
            except sqlite3.OperationalError:
                stats[table] = -1
    print(json.dumps(stats, indent=2))
    return 0


def cmd_backfill_summaries(args: argparse.Namespace) -> int:
    """Reseta status para ``nao_ingerido`` em docs sem entry em ``doc_summaries``.

    Utilizado apos o reindex para regerar summaries de docs que falharam
    parse ou foram adicionados antes da Fase 12.1. Nao re-ingeri
    imediatamente (use ``reindex`` ou rode ``src.indexer.ingest``
    depois deste comando).
    """
    db_path: Path = args.db_path
    if not db_path.exists():
        print(f"# DB nao encontrado: {db_path}", file=sys.stderr)
        return 1
    with _connect_with_vec(db_path) as conn:
        try:
            n_reset = conn.execute(
                "UPDATE documents SET status='nao_ingerido', ingested_at=NULL, "
                "content_hash=NULL "
                "WHERE file_path IS NOT NULL "
                "AND id NOT IN (SELECT document_id FROM doc_summaries)"
            ).rowcount
            conn.commit()
            print(
                f"# Backfill: {n_reset} documento(s) sem summary marcados "
                "como pendentes (rode `python -m src.indexer.ingest`)."
            )
        except sqlite3.OperationalError as exc:
            print(f"# Aviso: backfill falhou ({exc})", file=sys.stderr)
            return 1
    return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="python -m src.ragctl",
        description="CLI administrativo do DFe-Agent (migrate, benchmark, reindex, stats).",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Caminho do banco SQLite (default: storage/dfe.db).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub_migrate = sub.add_parser("migrate", help="Aplica migrations pendentes.")
    sub_migrate.set_defaults(func=cmd_migrate)

    sub_benchmark = sub.add_parser("benchmark", help="Roda eval_set + reporta metricas.")
    sub_benchmark.add_argument(
        "--eval-set",
        type=Path,
        default=Path("tests/fixtures/eval_set.json"),
    )
    sub_benchmark.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_STORAGE_DIR / "benchmark_report.json",
    )
    sub_benchmark.add_argument(
        "--chunker",
        type=str,
        default="flat",
        choices=["flat", "structural"],
        help=(
            "Apenas metadata. Para comparar A/B real, rode "
            "`ragctl reindex --chunker=flat` + `ragctl benchmark --chunker=flat` "
            "e depois repita com `structural`."
        ),
    )
    sub_benchmark.set_defaults(func=cmd_benchmark)

    sub_reindex = sub.add_parser(
        "reindex", help="Dropa chunks e dispara ingest novamente."
    )
    sub_reindex.add_argument(
        "--chunker",
        type=str,
        default="flat",
        choices=["flat", "structural"],
    )
    sub_reindex.set_defaults(func=cmd_reindex)

    sub_stats = sub.add_parser("stats", help="Imprime contadores.")
    sub_stats.set_defaults(func=cmd_stats)

    sub_backfill = sub.add_parser(
        "backfill-summaries",
        help=(
            "Reseta status para os docs que nao tem summary "
            "(re-ingerir depois)."
        ),
    )
    sub_backfill.set_defaults(func=cmd_backfill_summaries)

    return parser


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "main",
    "cmd_migrate",
    "cmd_benchmark",
    "cmd_reindex",
    "cmd_stats",
    "cmd_backfill_summaries",
]
