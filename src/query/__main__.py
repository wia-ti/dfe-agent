"""CLI: ``python -m src.query "pergunta em linguagem natural"``.

Imprime JSON com ``{"answer": str, "sources": list[dict]}``.

Comportamento:
    - Sem pergunta: imprime uso em stderr e retorna exit code 1.
    - ``storage/dfe.db`` nao existe: imprime JSON com ``NO_EVIDENCE_MESSAGE``
      e ``sources == []`` (exit 0). Nao imprime erro - a ausencia de base e
      uma resposta valida do agente.
    - Busca sem chunks relevantes (abaixo de ``MIN_RELEVANCE_SCORE``): mesma
      resposta de "sem base".
    - Busca com chunks relevantes: imprime JSON com ``answer`` (template com
      fontes citadas) e ``sources`` (lista de ``{title, url, score}``).

Sprint 2:
    - ``--hybrid`` (Fase 11): habilita busca hibrida (vetorial + FTS5/BM25 via RRF).
    - ``--hierarchical`` (Fase 12): two-stage retrieval via DocSummaryStore
      (corpus resumo -> top-K -> vec_chunks filtrado).
    - ``--rerank`` (Fase 15): aplica cross-encoder no top-K*5 candidatos.
    - Cache de embeddings (Fase 13) ativado por default; ``--no-cache`` desativa.
"""
from __future__ import annotations

# Mitiga o erro OpenBLAS "Memory allocation still failed after 10 retries"
# em subprocessos Windows (limita o numero de threads e portanto o
# footprint de memoria thread-local).
import os

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import argparse
import json
import sys
from pathlib import Path

from src.db.sqlite_storage import SqliteStorage
from src.db.vector_store import VectorStore
from src.indexer.embeddings import EmbeddingProvider
from src.query.constants import MIN_RELEVANCE_SCORE
from src.query.context_builder import (
    NO_EVIDENCE_MESSAGE,
    build_context,
    has_sufficient_evidence,
)


_DEFAULT_STORAGE_DIR: Path = Path("./storage")
_DEFAULT_DB_PATH: Path = _DEFAULT_STORAGE_DIR / "dfe.db"
_DEFAULT_CACHE_PATH: Path = _DEFAULT_STORAGE_DIR / "query_cache.db"
_EMBEDDING_DIM: int = 384


def _configure_utf8_stdout() -> None:
    """Garante que ``sys.stdout`` e ``sys.stderr`` operem em UTF-8.

    Necessario em Windows PowerShell, onde o default e' cp1252; chunks do
    RAG podem conter bullets (``•``), emojis ou caracteres acentuados que
    quebram o encode na hora de imprimir JSON (``UnicodeEncodeError:
    'charmap' codec can't encode character '\uf0b7'``).

    Estrategia: tenta ``stream.reconfigure(encoding="utf-8")`` (Python 3.7+
    em streams reconfiguraveis); se nao suportado, faz fallback via
    ``io.TextIOWrapper(sys.<stream>_buffer, encoding="utf-8")`` preservando
    o buffer original para nao perder redirecionamentos.
    """
    import io

    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
            continue
        except (AttributeError, ValueError):
            pass
        buf = getattr(sys, f"{stream_name}_buffer", None)
        if buf is not None:
            setattr(
                sys,
                stream_name,
                io.TextIOWrapper(buf, encoding="utf-8"),  # type: ignore[arg-type]
            )


def _format_sources(ranked: list) -> list[dict]:
    """Converte ``ScoredChunk`` list em lista de dicts para o JSON de saida."""
    return [
        {
            "title": c.doc_title,
            "url": c.source_url,
            "score": round(c.score, 4),
        }
        for c in ranked
    ]


def _build_answer(question: str, ranked: list) -> dict:
    """Constroi resposta JSON: usa template com fonte OU ``NO_EVIDENCE_MESSAGE``.

    Quando a busca retorna lista vazia ou abaixo de ``MIN_RELEVANCE_SCORE``,
    imprime uma linha em stderr com `count=0` (ou o tamanho real da lista).
    Justificativa (PLAN_SPRINT7 D.2): evita que o usuario confunda "sem chunks
    relevantes" com "CLI travou". Tambem ajuda debug em scripts que capturam
    ambos os streams separadamente.
    """
    if not has_sufficient_evidence(ranked):
        print(
            f"[query] sem chunks relevantes — count={len(ranked)}",
            file=sys.stderr,
        )
        return {"answer": NO_EVIDENCE_MESSAGE, "sources": []}

    context: str = build_context(ranked)
    answer_template: str = (
        f"Com base na documentacao disponivel, segue resposta para: {question}\n\n"
        f"{context}\n\n"
        "Esta resposta foi fundamentada nas fontes citadas acima."
    )
    return {"answer": answer_template, "sources": _format_sources(ranked)}


def _print_no_evidence_json() -> None:
    """Imprime JSON canonico de 'sem base' no stdout. Usado quando o banco nao existe."""
    print(
        json.dumps(
            {"answer": NO_EVIDENCE_MESSAGE, "sources": []},
            ensure_ascii=False,
            indent=2,
        )
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="python -m src.query",
        description=(
            "Consulta a base RAG local. Flags: --hybrid (RRF com BM25), "
            "--hierarchical (two-stage via DocSummaryStore), --rerank "
            "(cross-encoder opt-in), --no-cache (desativa cache)."
        ),
    )
    parser.add_argument(
        "question",
        nargs=argparse.REMAINDER,
        help="Pergunta em linguagem natural (palavras-chave).",
    )
    parser.add_argument(
        "--hybrid",
        dest="use_hybrid",
        action="store_true",
        help="Habilita busca hibrida (vetorial + FTS5/BM25 via RRF).",
    )
    parser.add_argument(
        "--hierarchical",
        dest="use_hierarchical",
        action="store_true",
        help=(
            "Two-stage retrieval: embedding -> top-K summaries -> "
            "vec_chunks filtrado. Requer summaries pre-ingeridos."
        ),
    )
    parser.add_argument(
        "--rerank",
        dest="enable_rerank",
        action="store_true",
        help=(
            "Aplica cross-encoder no top-5 candidatos (opt-in, adiciona "
            "latencia). Indicado apenas quando o benchmark Fase 16 "
            "mostrar ganho de MRR."
        ),
    )
    parser.add_argument(
        "--no-cache",
        dest="use_cache",
        action="store_false",
        help="Desativa o cache de embeddings de query (default: ON).",
    )
    parser.add_argument(
        "--hierarchical-top-docs",
        type=int,
        default=None,
        help=(
            "Quantos docs selecionar no coarse filter do --hierarchical "
            "(default: HIERARCHICAL_TOP_DOCS=10). Tambem via env "
            "DFE_HIERARCHICAL_TOP_DOCS."
        ),
    )
    parser.set_defaults(use_cache=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada. Retorna o codigo de saida do processo."""
    # PLAN_SPRINT7 B.1: reconfigura stdout/stderr para UTF-8 antes de
    # qualquer I/O. Necessario em Windows PowerShell (cp1252 default) para
    # nao quebrar a impressao do JSON quando chunks do RAG contem chars
    # fora do Latin-1 (bullets, emojis, etc).
    _configure_utf8_stdout()

    # Lazy import para conviver com testes que importam este modulo sem
    # ter ``.opencode`` em PYTHONPATH (ex.: test_each_documented_command_imports_without_error).
    from src.utils.http_guard_bootstrap import install_guard_once

    install_guard_once()
    if argv is None:
        argv = sys.argv[1:]

    args = _build_arg_parser().parse_args(argv)
    question: str = " ".join(args.question).strip()

    if not question:
        print(
            "Uso: python -m src.query "
            "[--hybrid|--hierarchical] [--rerank] [--no-cache] <pergunta>",
            file=sys.stderr,
        )
        return 1

    db_path: Path = _DEFAULT_DB_PATH
    if not db_path.exists():
        _print_no_evidence_json()
        return 0

    # Lazy imports para conviver com paralelismo intra-fase.
    from src.db.doc_summaries import DocSummaryStore
    from src.db.fts_store import FtsStore
    from src.query.embedding_cache import QueryEmbeddingCache
    from src.query.query_engine import QueryEngine
    from src.query.reranker import CrossEncoderReranker

    storage = SqliteStorage(db_path)
    storage.init_schema()

    fts_store: FtsStore | None = None
    if args.use_hybrid:
        fts_store = FtsStore(db_path)
        fts_store.init_schema()
        fts_store.rebuild_from_db()

    summary_store: DocSummaryStore | None = None
    if args.use_hierarchical:
        summary_store = DocSummaryStore(db_path, dim=_EMBEDDING_DIM)
        summary_store.init_schema()

    vector_store = VectorStore(db_path, dim=_EMBEDDING_DIM, fts_store=fts_store)
    vector_store.init_schema()

    embedding_cache: QueryEmbeddingCache | None = None
    if args.use_cache:
        embedding_cache = QueryEmbeddingCache(
            _DEFAULT_CACHE_PATH, dim=_EMBEDDING_DIM
        )
        embedding_cache.init_schema()

    reranker: CrossEncoderReranker | None = None
    if args.enable_rerank:
        reranker = CrossEncoderReranker()

    embedder = EmbeddingProvider()

    # Override do top-N hierarchical via CLI > env > constante.
    hierarchical_top_docs: int = (
        args.hierarchical_top_docs
        if args.hierarchical_top_docs is not None
        else int(os.environ.get("DFE_HIERARCHICAL_TOP_DOCS", "10"))
    )

    engine = QueryEngine(
        vector_store,
        embedder,
        fts_store=fts_store,
        summary_store=summary_store,
        embedding_cache=embedding_cache,
        reranker=reranker,
        enable_rerank=args.enable_rerank,
        hierarchical_top_docs=hierarchical_top_docs,
        min_score=MIN_RELEVANCE_SCORE,
    )

    if args.use_hierarchical:
        ranked = engine.search_hierarchical(question)
    else:
        ranked = engine.search(question)
    response: dict = _build_answer(question, ranked)
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "_DEFAULT_DB_PATH",
    "_DEFAULT_CACHE_PATH",
    "_EMBEDDING_DIM",
    "_build_answer",
    "_format_sources",
    "_print_no_evidence_json",
    "main",
]
