"""Demo CLI canonico do DFe-Agent (scripts/demo_cli.py).

Uso:
    python scripts/demo_cli.py

Executa uma sequencia de consultas demonstrando os principais fluxos
do CLI ``python -m src.query`` (Sprint 1/2). Equivalente em Python
aos scripts shell ``demo_sprint2.sh``/``.ps1``.

Pre-Sprint 11: este arquivo existia desde Sprint 1 e era o unico
``.py`` canonico em ``scripts/``. Foi removido acidentalmente em
Sprint 11 e restaurado neste commit.

Sprint 11 F.2 (SUGESTAO S1): C.6 sugere mover ``.claude/scripts/
test_hooks.py`` e ``demo_agent_hooks.py`` para ``scripts/`` raiz com
sufixo ``_smoke_legacy.py``. Nao aplicado nesta sprint (decisao
pendente em Apêndice B).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]


def _run(cmd: list[str]) -> None:
    """Roda comando no cwd do projeto. Falha nao derruba o demo."""
    print(f"\n$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=False)
    if result.returncode != 0:
        print(f"  (exit {result.returncode}; demo segue)")


def main() -> int:
    print("=" * 60)
    print("  DFe-Agent demo CLI (Sprint 1/2)")
    print("=" * 60)

    question = "Como cancelar NF-e apos a NT 2019.001?"

    print("\n[1] Query semantica (default)")
    _run([sys.executable, "-m", "src.query", question])

    print("\n[2] Query hibrida (RRF + BM25)")
    _run([sys.executable, "-m", "src.query", "--hybrid", question])

    print("\n[3] Cache de embedding (2a chamada deve ser hit)")
    cache_q = "cache hit NF-e 2019 cancelamento"
    _run([sys.executable, "-m", "src.query", cache_q])
    _run([sys.executable, "-m", "src.query", cache_q])

    print("\n[4] Stats do banco")
    _run([sys.executable, "-m", "src.ragctl", "stats"])

    print("\nDemo finalizado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
