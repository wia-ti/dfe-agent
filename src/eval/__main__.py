"""CLI ``python -m src.eval``: roda o eval_set contra a base RAG local e
reporta ``recall@5``, ``MRR`` e ``citation_rate``.

Uso:
    $ python -m src.eval --report storage/benchmark_report.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.eval.runner import (
    DEFAULT_EVAL_SET_PATH,
    DEFAULT_REPORT_PATH,
    EvalSample,
    load_eval_set,
    run_benchmark,
)


def main(argv: list[str] | None = None) -> int:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="python -m src.eval",
        description=(
            "Roda o eval_set contra a base RAG e devolve "
            "recall@5 / MRR / citation_rate."
        ),
    )
    parser.add_argument(
        "--eval-set",
        type=str,
        default=str(DEFAULT_EVAL_SET_PATH),
        help="Caminho para eval_set.json (default: tests/fixtures/eval_set.json).",
    )
    parser.add_argument(
        "--report",
        type=str,
        default=str(DEFAULT_REPORT_PATH),
        help="Caminho para gravar o JSON de saida (default: storage/benchmark_report.json).",
    )
    parser.add_argument(
        "--chunker",
        type=str,
        default="flat",
        choices=["flat", "structural"],
        help=(
            "Apenas metadata no report (o chunker e fixado no momento do "
            "ingest). Use o ragctl reindex para comparar A/B."
        ),
    )
    args = parser.parse_args(argv)

    from src.eval.runner import to_dict

    eval_set_path: Path = Path(args.eval_set)
    report_path: Path = Path(args.report)
    eval_set: list[EvalSample] = load_eval_set(eval_set_path)
    report = run_benchmark(eval_set, chunker=args.chunker)
    payload: dict = to_dict(report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


__all__ = ["main"]

if __name__ == "__main__":
    import sys

    sys.exit(main())
