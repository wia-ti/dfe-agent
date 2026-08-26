"""Runner de benchmark para o DFe-Agent (Sprint 2, Fase 16).

Usa ``tests/fixtures/eval_set.json`` como ground truth. Para cada
pergunta, executa ``QueryEngine.search`` e computa:

    - ``recall@5``: 1.0 se o doc esperado esta entre os top-5, 0.0 senao.
    - ``MRR``: 1/rank se o doc esperado aparece no top-K, 0.0 senao.
    - ``citation_rate``: 1.0 se o doc esperado esta em qualquer source
      da resposta final, 0.0 senao. Usado no guardrail do AGENTS.md.

O resultado e gravado em ``storage/benchmark_report.json``.

Politica de match (PLAN_SPRINT4 D.3 / IMPORTANTE #6):
    ``expected_doc_url`` e' tratado como **host + path-base** da URL
    esperada, NAO como URL exata. O match ocorre quando:
        1. O ``source.url`` tem o mesmo **hostname** (ex.: ``www.nfe.fazenda.gov.br``).
        2. O ``source.url`` compartilha pelo menos 1 ``expected_keywords``
           com o ``doc_title`` ou o ``source.url`` path.

    Isso permite que a URL real do doc (com tokens de sessao,
    IDs dinamicos, etc.) seja aceita sem quebrar o benchmark.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import sqlite_vec

DEFAULT_EVAL_SET_PATH: Path = Path("tests/fixtures/eval_set.json")
DEFAULT_REPORT_PATH: Path = Path("storage/benchmark_report.json")


@dataclass
class EvalSample:
    question: str
    expected_doc_url: str
    expected_keywords: list[str] = field(default_factory=list)


@dataclass
class EvalResult:
    question: str
    expected_doc_url: str
    found_doc_id: int | None
    rank: int | None
    recall_at_5: float
    mrr: float
    cited_in_answer: float


@dataclass
class BenchmarkReport:
    eval_set_size: int
    recall_at_5: float
    mrr: float
    citation_rate: float
    per_question: list[EvalResult]
    chunker: str = "flat"


def load_eval_set(path: Path) -> list[EvalSample]:
    raw: list[dict] = json.loads(path.read_text(encoding="utf-8"))
    return [
        EvalSample(
            question=item["question"],
            expected_doc_url=item["expected_doc_url"],
            expected_keywords=item.get("expected_keywords", []),
        )
        for item in raw
    ]


def _run_query_engine(
    question: str,
    chunker: str = "flat",
    hybrid: bool = True,
) -> list[dict]:
    """Roda CLI ``python -m src.query`` em subprocess; devolve ``sources``.

    Args:
        question: Texto da pergunta.
        chunker: ``"flat"`` (default) ou ``"structural"``.
        hybrid: Se True, ativa ``--hybrid`` no CLI (cobre todos os backends
            ja que FTS5+vec_chunks estao sempre sincronizados).
    """
    cmd: list[str] = [sys.executable, "-m", "src.query"]
    if hybrid:
        cmd.append("--hybrid")
    cmd.append(question)
    result = subprocess.run(
        cmd, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        return []
    payload: dict = json.loads(result.stdout)
    return payload.get("sources", [])


def _find_doc_id_by_url(db_path: Path, url: str) -> int | None:
    """Resolve URL -> documents.id."""
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM documents WHERE url = ?", (url,)
        ).fetchone()
    return int(row[0]) if row else None


def _hostname_of(url: str) -> str:
    """Extrai hostname (lower, sem ``www.``) ou string vazia."""
    try:
        host: str = (urlparse(url).hostname or "").strip().lower()
    except (ValueError, TypeError):
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def _matches_expected(
    source_url: str,
    source_title: str,
    expected_host: str,
    expected_keywords: list[str],
) -> bool:
    """Match por host + token compartilhado (PLAN_SPRINT4 D.3).

    Aceita o source se:
        1. ``source_url`` tem o mesmo hostname canonico que o esperado.
        2. Pelo menos 1 keyword de ``expected_keywords`` aparece em
           ``source_url`` (path) OU em ``source_title``.
    """
    src_host: str = _hostname_of(source_url)
    if src_host != expected_host:
        return False
    if not expected_keywords:
        return True
    haystacks: list[str] = [
        (source_url or "").lower(),
        (source_title or "").lower(),
    ]
    for kw in expected_keywords:
        kw_lower: str = kw.lower()
        if any(kw_lower in h for h in haystacks):
            return True
    return False


def evaluate_question(
    question: str,
    expected_doc_url: str,
    expected_keywords: list[str],
    sources: list[dict],
    rank_for: callable,  # type: ignore[type-arg]
) -> EvalResult:
    """Avalia uma unica pergunta usando match por dominio + token.

    Rank determinstico: o i-esimo source na lista da CLI e o rank i+1.
    O match NAO exige URL exata: aceita qualquer source com mesmo
    hostname e pelo menos 1 keyword compartilhada.
    """
    expected_host: str = _hostname_of(expected_doc_url)
    found_doc_id: int | None = None
    rank: int | None = None
    for i, src in enumerate(sources, start=1):
        src_url: str = src.get("url", "")
        src_title: str = src.get("title", "")
        if _matches_expected(src_url, src_title, expected_host, expected_keywords):
            found_doc_id = rank_for(src_url)
            rank = i
            break

    return EvalResult(
        question=question,
        expected_doc_url=expected_doc_url,
        found_doc_id=found_doc_id,
        rank=rank,
        recall_at_5=1.0 if (rank is not None and rank <= 5) else 0.0,
        mrr=(1.0 / rank) if rank else 0.0,
        cited_in_answer=1.0 if found_doc_id else 0.0,
    )


def run_benchmark(
    eval_set: list[EvalSample],
    db_path: Path | str | None = None,
    chunker: str = "flat",
) -> BenchmarkReport:
    """Executa o runner contra o DB e retorna ``BenchmarkReport``.

    Args:
        eval_set: Lista de :class:`EvalSample`.
        db_path: Path do banco. Quando ``None`` (default), retorna
            report vazio (todas as metricas 0.0). Para rodar contra a
            base de producao, passe explicitamente o caminho ou use a
            CLI ``python -m src.ragctl benchmark``.
        chunker: ``"flat"`` (default) ou ``"structural"`` (Sprint 2 / Fase 10.1).
            Apenas metadata no report; a selecao de chunker afeta o indice
            ja persistido em ``vec_chunks`` (definido no momento do ingest,
            nao do runner).
    """
    resolved_db: Path | None = (
        Path(db_path) if db_path is not None else None
    )
    if resolved_db is None or not resolved_db.exists():
        return BenchmarkReport(
            eval_set_size=len(eval_set),
            recall_at_5=0.0,
            mrr=0.0,
            citation_rate=0.0,
            per_question=[],
            chunker=chunker,
        )

    def rank_for(url: str) -> int | None:
        return _find_doc_id_by_url(resolved_db, url)

    per_question: list[EvalResult] = []
    for sample in eval_set:
        sources: list[dict] = _run_query_engine(
            sample.question, chunker=chunker, hybrid=True
        )
        per_question.append(
            evaluate_question(
                sample.question,
                sample.expected_doc_url,
                sample.expected_keywords,
                sources,
                rank_for,
            )
        )

    n: int = len(per_question)
    recall: float = (
        sum(r.recall_at_5 for r in per_question) / n if n else 0.0
    )
    mrr: float = sum(r.mrr for r in per_question) / n if n else 0.0
    citation: float = (
        sum(r.cited_in_answer for r in per_question) / n if n else 0.0
    )

    return BenchmarkReport(
        eval_set_size=n,
        recall_at_5=recall,
        mrr=mrr,
        citation_rate=citation,
        per_question=per_question,
        chunker=chunker,
    )


def to_dict(report: BenchmarkReport) -> dict:
    """Serializa o report em dict puro (dataclasses -> dict)."""
    return {
        "eval_set_size": report.eval_set_size,
        "recall_at_5": round(report.recall_at_5, 4),
        "mrr": round(report.mrr, 4),
        "citation_rate": round(report.citation_rate, 4),
        "chunker": report.chunker,
        "per_question": [asdict(r) for r in report.per_question],
    }


__all__ = [
    "BenchmarkReport",
    "DEFAULT_EVAL_SET_PATH",
    "DEFAULT_REPORT_PATH",
    "EvalResult",
    "EvalSample",
    "evaluate_question",
    "load_eval_set",
    "run_benchmark",
    "to_dict",
]
