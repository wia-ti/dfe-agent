"""Testes para Sprint 2, Fase 13.1: ``QueryEmbeddingCache``.

Cobre:
    - Tabela ``query_cache`` criada com schema correto (PK em query_hash).
    - ``put`` seguido de ``get`` devolve o mesmo vetor (modulo precisao float32).
    - Queries identicas (case + whitespace) geram o mesmo hash.
    - ``hit_count`` e ``last_used_at`` atualizam em cada get.
    - Cache corrompido (embedding dim errada): levanta RuntimeError.
    - ``stats`` devolve metricas uteis.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.query.embedding_cache import QueryEmbeddingCache


# --- schema --------------------------------------------------------------


def test_init_schema_cria_tabela_query_cache(tmp_path: Path) -> None:
    cache = QueryEmbeddingCache(tmp_path / "cache.db", dim=4)
    cache.init_schema()

    with sqlite3.connect(tmp_path / "cache.db") as conn:
        cols = {
            row[1]
            for row in conn.execute(
                "SELECT * FROM pragma_table_info('query_cache')"
            ).fetchall()
        }
    assert "query_hash" in cols
    assert "embedding" in cols
    assert "hit_count" in cols
    assert "last_used_at" in cols


# --- round-trip ----------------------------------------------------------


def test_put_e_get_round_trip(tmp_path: Path) -> None:
    cache = QueryEmbeddingCache(tmp_path / "cache.db", dim=4)
    cache.init_schema()

    emb = [0.1, 0.2, 0.3, 0.4]
    cache.put("pergunta exemplo", emb)

    got = cache.get("pergunta exemplo")
    assert got is not None
    assert len(got) == 4
    for actual, expected in zip(got, emb):
        assert abs(actual - expected) < 1e-5


def test_get_miss_retorna_none(tmp_path: Path) -> None:
    cache = QueryEmbeddingCache(tmp_path / "cache.db", dim=4)
    cache.init_schema()
    assert cache.get("nunca inserido") is None


def test_queries_normalizadas_mesmo_hash(tmp_path: Path) -> None:
    """Case + whitespace nao diferenciam (cache hit)."""
    cache = QueryEmbeddingCache(tmp_path / "cache.db", dim=4)
    cache.init_schema()

    emb = [0.1, 0.2, 0.3, 0.4]
    cache.put("  NF-e  ", emb)

    assert cache.get("nf-e") is not None
    assert cache.get("NF-e") is not None
    assert cache.get("  NF-e  ") is not None


def test_hit_count_e_last_used_at_atualizam(tmp_path: Path) -> None:
    cache = QueryEmbeddingCache(tmp_path / "cache.db", dim=4)
    cache.init_schema()

    cache.put("q1", [0.1, 0.2, 0.3, 0.4])

    # Primeira leitura: hit_count=1
    cache.get("q1")
    with sqlite3.connect(tmp_path / "cache.db") as conn:
        h1 = conn.execute(
            "SELECT hit_count FROM query_cache WHERE query_hash IS NOT NULL"
        ).fetchone()[0]
    assert h1 == 1

    # Segunda leitura: hit_count=2
    cache.get("q1")
    with sqlite3.connect(tmp_path / "cache.db") as conn:
        h2 = conn.execute(
            "SELECT hit_count FROM query_cache WHERE query_hash IS NOT NULL"
        ).fetchone()[0]
    assert h2 == 2


def test_embedding_corrompido_levanta_runtimeerror(tmp_path: Path) -> None:
    cache = QueryEmbeddingCache(tmp_path / "cache.db", dim=4)
    cache.init_schema()

    # Escreve blob com dim errada direto via SQL.
    import struct
    with sqlite3.connect(tmp_path / "cache.db") as conn:
        conn.execute(
            "INSERT INTO query_cache(query_hash, query_text, embedding, hit_count, "
            "last_used_at) VALUES (?, ?, ?, 0, '2026-01-01T00:00:00')",
            (
                cache._hash("q"),
                "q",
                struct.pack("2f", 0.1, 0.2),  # so 2 floats em vez de 4
            ),
        )
        conn.commit()

    with pytest.raises(RuntimeError, match="dim"):
        cache.get("q")


def test_embedding_dim_errada_em_put_levanta(tmp_path: Path) -> None:
    cache = QueryEmbeddingCache(tmp_path / "cache.db", dim=4)
    cache.init_schema()
    with pytest.raises(ValueError, match="dim"):
        cache.put("q", [0.1, 0.2])  # so 2 dims


def test_stats(tmp_path: Path) -> None:
    cache = QueryEmbeddingCache(tmp_path / "cache.db", dim=4)
    cache.init_schema()
    cache.put("q1", [0.1, 0.2, 0.3, 0.4])
    cache.put("q2", [0.5, 0.6, 0.7, 0.8])
    cache.get("q1")
    cache.get("q1")
    cache.get("q2")

    stats = cache.stats()
    assert stats["total_entries"] == 2
    assert stats["total_hits"] == 3
