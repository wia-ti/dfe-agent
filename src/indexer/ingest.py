"""CLI: ``python -m src.indexer.ingest``.

Indexa todos os documentos com ``status='nao_ingerido'`` na base RAG local,
executando o pipeline ``parser -> chunk -> embed -> persist``.

Sprint 2:
    - Fase 10.1: aceita ``--chunker={flat,structural}``.
    - Fase 11.1: sincroniza com FTS5 (BM25) — cada chunk persistido em
      vec_chunks tambem e inserido em fts_chunks.
    - Fase 12.1: persistencia automatica de ``doc_summaries``.

Uso:
    $ python -m src.indexer.ingest
    # ingestao: N documento(s) indexado(s).

    $ python -m src.indexer.ingest --chunker=structural
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.db.fts_store import FtsStore
from src.db.sqlite_storage import SqliteStorage
from src.db.vector_store import VectorStore
from src.indexer.embeddings import EmbeddingProvider
from src.indexer.rag_indexer import RagIndexer
from src.parser.pdf_parser import extract_text_from_pdf

STORAGE_DIR: Path = Path("./storage")
DB_PATH: Path = STORAGE_DIR / "dfe.db"
EMBEDDING_DIM: int = 384


def _build_arg_parser() -> argparse.ArgumentParser:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="python -m src.indexer.ingest",
        description=(
            "Indexa documentos nao-ingeridos na base RAG local. "
            "Suporta dois modos de chunking: flat (chunker plano) e "
            "structural (chunker ciente de secoes NT)."
        ),
    )
    parser.add_argument(
        "--chunker",
        type=str,
        default="flat",
        choices=["flat", "structural"],
        help=(
            "Modo de chunking. ``flat`` (default) usa o chunker plano; "
            "``structural`` preserva contexto de secao NT nos chunks."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Instancia componentes, executa ``ingest_pending`` e imprime resumo."""
    # Lazy import (mesma razao do query.__main__: nao regredir testes que
    # importam o modulo sem ``.opencode`` em PYTHONPATH).
    from src.utils.http_guard_bootstrap import install_guard_once

    install_guard_once()
    if argv is None:
        argv = sys.argv[1:]

    args = _build_arg_parser().parse_args(argv)
    chunker_mode: str = args.chunker

    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    storage = SqliteStorage(DB_PATH)
    storage.init_schema()

    # Fase 11.1: instancia FTS5 com auto-backfill (caso DB pre-Sprint2).
    fts_store = FtsStore(DB_PATH)
    fts_store.init_schema()
    fts_store.rebuild_from_db()

    vector_store = VectorStore(DB_PATH, dim=EMBEDDING_DIM, fts_store=fts_store)
    vector_store.init_schema()

    embedder = EmbeddingProvider()
    indexer = RagIndexer(
        storage=storage,
        vector_store=vector_store,
        embedder=embedder,
        parser=extract_text_from_pdf,
        chunker_mode=chunker_mode,  # type: ignore[arg-type]
    )

    indexed: int = indexer.ingest_pending()
    print(f"# ingestao: {indexed} documento(s) indexado(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["main"]