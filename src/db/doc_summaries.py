"""DAO para ``doc_summaries`` (Sprint 2, Fase 12.1).

Tabela mantida pela migration 0005 em :mod:`src.db.migrations`.
Persistida por :class:`src.indexer.rag_indexer.RagIndexer` apos
extracao via :func:`src.indexer.summarizer.summarize`.

Usada por :meth:`src.query.query_engine.QueryEngine.search_hierarchical`
para o primeiro estagio (filtro coarse por similaridade do resumo) do
two-stage retrieval. Para o caso do corpus crescer significativamente
(>10k docs), considere substituir a tabela por uma vec0 virtual table;
hoje fica como brute-force (escala O(n docs) por query, aceitavel ate
milhares).
"""
from __future__ import annotations

import sqlite3
import struct
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import sqlite_vec


@dataclass
class DocSummary:
    """Snapshot de uma linha de ``doc_summaries``.

    ``embedding`` fica como None quando o sumario ainda nao foi
    embedado (ex: doc ingerido antes da Fase 12.1 mas com resumo
    gerado retroativamente).
    """

    document_id: int
    summary: str
    embedding: list[float] | None
    created_at: datetime


@dataclass
class ScoredSummary:
    """Resultado de :meth:`DocSummaryStore.find_similar_summaries`."""

    document_id: int
    summary: str
    score: float


class DocSummaryStore:
    """DAO simples sobre ``doc_summaries``.

    O construtor recebe ``db_path``; cada metodo abre/fecha conexao
    via ``with sqlite3.connect`` (consistente com o padrao do projeto).
    """

    def __init__(self, db_path: Path, dim: int) -> None:
        if dim <= 0:
            raise ValueError(f"dim deve ser positivo, recebido {dim}")
        self._db_path: Path = Path(db_path)
        self._dim: int = dim

    def init_schema(self) -> None:
        """Aplica migration 0005 (cria ``doc_summaries``); idempotente."""
        from src.db.migrations import apply_pending

        apply_pending(self._db_path)

    def upsert_summary(
        self,
        document_id: int,
        summary: str,
        embedding: list[float],
        now: datetime | None = None,
    ) -> None:
        """Insere ou substitui o sumario de ``document_id``.

        Idempotente: regravar com o mesmo texto+embedding NAO causa
        duplicacao (PK = document_id).
        """
        from src.db.migrations import read_user_version  # noqa: F401

        if not summary:
            raise ValueError("summary nao pode ser vazio")
        if len(embedding) != self._dim:
            raise ValueError(
                f"embedding dim {len(embedding)} != esperado {self._dim}"
            )
        ts: datetime = now or datetime.now(__import__("datetime").timezone.utc).replace(tzinfo=None)
        blob: bytes = struct.pack(f"{self._dim}f", *embedding)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO doc_summaries("
                "document_id, summary, embedding, created_at"
                ") VALUES (?, ?, ?, ?)",
                (
                    document_id,
                    summary,
                    blob,
                    ts.isoformat(),
                ),
            )
            conn.commit()

    def has_summary(self, document_id: int) -> bool:
        """Indica se o doc ja tem sumario persistido."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM doc_summaries WHERE document_id = ?",
                (document_id,),
            ).fetchone()
        return row is not None

    def list_summaries(self) -> list[DocSummary]:
        """Retorna todos os summaries; usado por :func:`search_hierarchical`
        para fazer brute-force cosine."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT document_id, summary, embedding, created_at "
                "FROM doc_summaries"
            ).fetchall()
        results: list[DocSummary] = []
        for doc_id, summary, blob, created_at in rows:
            emb: list[float] | None = (
                list(struct.unpack(f"{self._dim}f", blob)) if blob else None
            )
            results.append(
                DocSummary(
                    document_id=int(doc_id),
                    summary=summary,
                    embedding=emb,
                    created_at=datetime.fromisoformat(created_at)
                    if created_at
                    else datetime.now(),
                )
            )
        return results

    def find_similar_summaries(
        self,
        query_embedding: list[float],
        top_k: int = 10,
    ) -> list[ScoredSummary]:
        """Retorna os top-K summaries mais similares a ``query_embedding``.

        Como decidido na Fase 12, brute-force O(N) no corpus de summaries.
        Para escala maior, substituir por vec0 search em uma futura
        migration.
        """
        if not query_embedding:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT document_id, summary, embedding "
                "FROM doc_summaries"
            ).fetchall()
        if not rows:
            return []

        scored: list[ScoredSummary] = []
        for doc_id, summary, blob in rows:
            if not blob:
                continue
            emb: list[float] = list(struct.unpack(f"{self._dim}f", blob))
            score: float = _cosine_similarity(query_embedding, emb)
            scored.append(
                ScoredSummary(
                    document_id=int(doc_id),
                    summary=summary,
                    score=score,
                )
            )
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:top_k]

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        return conn


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosseno puro entre dois vetores (sem usar numpy)."""
    if len(a) != len(b):
        return 0.0
    dot: float = 0.0
    na: float = 0.0
    nb: float = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / ((na ** 0.5) * (nb ** 0.5))


__all__ = ["DocSummary", "DocSummaryStore", "ScoredSummary"]
