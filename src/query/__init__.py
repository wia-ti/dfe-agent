"""Camada de Consulta do DFe-Agent."""
from __future__ import annotations

import sys
from pathlib import Path

# Bootstrap: garante que .opencode/ esteja no sys.path para imports da skill
_QUERY_PARENT: Path = Path(__file__).resolve().parents[1]
_OPENCODE_DIR: Path = _QUERY_PARENT / ".opencode"
if str(_OPENCODE_DIR) not in sys.path:
    sys.path.insert(0, str(_OPENCODE_DIR))

# Re-export de QueryEngine com fallback resiliente (Task 6.1 paralela).
# Se query_engine.py ainda nao foi entregue, QueryEngine fica None; apos a entrega
# da Task 6.1, este modulo passa a oferecer QueryEngine normalmente.
try:
    from src.query.query_engine import QueryEngine
except ImportError:  # pragma: no cover - coexistencia com Task 6.1
    QueryEngine = None  # type: ignore[assignment,misc]

from src.query.context_builder import (  # noqa: E402
    NO_EVIDENCE_MESSAGE,
    build_context,
    has_sufficient_evidence,
)

__all__ = [
    "QueryEngine",
    "build_context",
    "has_sufficient_evidence",
    "NO_EVIDENCE_MESSAGE",
]
