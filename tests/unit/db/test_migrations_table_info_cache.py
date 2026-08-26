"""Testes do cache de ``PRAGMA table_info`` em migrations (PLAN_SPRINT4 E.1 / IMPORTANTE #4).

Garante que:

- ``_apply_v2`` chama ``PRAGMA table_info(documents)`` exatamente 1 vez
  por execution (pre-computa as colunas existentes e reusa nas 4
  chamadas a ``_ensure_column``).
- ``_apply_v6`` chama ``PRAGMA table_info(chunk_metadata)`` exatamente
  1 vez por execution (reusa nas 2 checagens de ``kind`` e
  ``parent_chunk_id``).

Implementacao: usa ``sqlite3.Connection.set_trace_callback`` (hook
nativo do sqlite3) para contar chamadas a ``PRAGMA table_info(<table>)``
sem depender de mock em atributo read-only.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.db import migrations


class _TraceCounter:
    """Conta chamadas a ``PRAGMA table_info(<table>)`` via trace callback."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, sql: str) -> None:
        normalized: str = " ".join(sql.split()).lower()
        if normalized.startswith("pragma table_info("):
            table_name: str = sql.split("(", 1)[1].split(")", 1)[0].strip()
            self.calls.append(table_name)

    def matches(self, table: str) -> int:
        return sum(1 for c in self.calls if c == table)


def test_apply_v2_calls_table_info_documents_once(tmp_path: Path) -> None:
    """``_apply_v2`` chama ``PRAGMA table_info(documents)`` exatamente 1 vez."""
    db_path: Path = tmp_path / "test.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                source_domain TEXT NOT NULL,
                doc_type TEXT NOT NULL,
                title TEXT NOT NULL,
                file_path TEXT,
                content_hash TEXT,
                published_at TEXT,
                fetched_at TEXT NOT NULL,
                ingested_at TEXT,
                status TEXT NOT NULL
            );
            """
        )

    counter: _TraceCounter = _TraceCounter()

    with sqlite3.connect(db_path) as conn:
        conn.set_trace_callback(counter)
        try:
            migrations._apply_v2(conn)
            conn.commit()
        finally:
            conn.set_trace_callback(None)

    assert counter.matches("documents") == 1, (
        f"Esperado 1 chamada a PRAGMA table_info(documents); "
        f"obtido {counter.matches('documents')}. Calls: {counter.calls}"
    )


def test_apply_v6_calls_table_info_chunk_metadata_once(tmp_path: Path) -> None:
    """``_apply_v6`` chama ``PRAGMA table_info(chunk_metadata)`` exatamente 1 vez."""
    db_path: Path = tmp_path / "test.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE documents (id INTEGER PRIMARY KEY);
            CREATE TABLE chunk_metadata (
                document_id INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                section_path TEXT NOT NULL DEFAULT '',
                section_level INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (document_id, chunk_index)
            );
            """
        )

    counter: _TraceCounter = _TraceCounter()

    with sqlite3.connect(db_path) as conn:
        conn.set_trace_callback(counter)
        try:
            migrations._apply_v6(conn)
            conn.commit()
        finally:
            conn.set_trace_callback(None)

    assert counter.matches("chunk_metadata") == 1, (
        f"Esperado 1 chamada a PRAGMA table_info(chunk_metadata); "
        f"obtido {counter.matches('chunk_metadata')}. Calls: {counter.calls}"
    )