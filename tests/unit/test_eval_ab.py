"""Testes para ``src.eval.runner`` estendido com A/B chunker (Sprint 3, Iter 3).

Cobre:
    - ``run_benchmark`` aceita ``chunker: str = "flat"`` (default).
    - ``chunker_mode="structural"`` produz o mesmo schema de report
      (recall_at_5 / MRR / citation_rate), apenas o caminho de execucao
      no CLI difere.
"""
from __future__ import annotations

from src.eval.runner import BenchmarkReport, EvalSample, EvalResult, run_benchmark


def test_run_benchmark_sem_db_retorna_zeros() -> None:
    """Sem o DB de producao, todas as metricas sao zero (comportamento defensivo)."""
    samples: list[EvalSample] = [
        EvalSample(
            question="Q1",
            expected_doc_url="https://example.com/x",
        ),
        EvalSample(
            question="Q2",
            expected_doc_url="https://example.com/y",
        ),
    ]
    report: BenchmarkReport = run_benchmark(samples, db_path=None)
    assert report.eval_set_size == 2
    assert report.recall_at_5 == 0.0
    assert report.mrr == 0.0
    assert report.citation_rate == 0.0
    assert report.per_question == []


def test_run_benchmark_aceita_parametros_de_chunker() -> None:
    """A/B chunker flag e propagada para o runner (mesmo sem DB)."""
    samples: list[EvalSample] = [EvalSample(question="Q", expected_doc_url="u")]
    for chunker in ("flat", "structural"):
        report: BenchmarkReport = run_benchmark(samples, db_path=None, chunker=chunker)
        assert report.eval_set_size == 1