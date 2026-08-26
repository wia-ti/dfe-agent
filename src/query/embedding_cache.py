"""Cache persistente de embeddings de query (Sprint 2, Fase 13.1).

Guarda pares (texto-normalizado, vetor) em tabela SQLite ``query_cache``,
com chave ``query_hash = sha256(texto_normalizado)``. Hits repetidos
nao recalculam o embedding.

Performance:
    - Cache hit: <1ms (single-row SELECT).
    - Cache miss: ``embedder.embed([query])`` (lento no CPU).

Normalizacao:
    - Texto passa por ``text.strip().lower()`` antes de hash.
    - ``"NF-e"`` == ``"nf-e "`` == ``"  NF-e  "`` mesmo hash.

Idempotencia / seguranca:
    - ``INSERT OR REPLACE`` no ``put``: regravar mesmo query substitui.
    - ``UPDATE`` no ``get``: incrementa ``hit_count`` e atualiza
      ``last_used_at`` (metricas para analise de padroes de uso).
"""
from __future__ import annotations

import hashlib
import sqlite3
import struct
from datetime import datetime, timezone
from pathlib import Path


def _hash_query(query: str) -> str:
    """Hash SHA-256 do texto normalizado (lowercase + strip)."""
    normalized = query.strip().lower().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


class QueryEmbeddingCache:
    """Cache persistente em SQLite, isolado do DB principal.

    O cache e intencionalmente separado do ``storage/dfe.db``:
    - Conteudo e' volatil (nao precisa estar na mesma base da RAG).
    - Permite regeneracao do DB RAG sem perder o cache.
    - Permite WORM-style backup separado do RAG.
    """

    def __init__(self, db_path: Path, dim: int) -> None:
        if dim <= 0:
            raise ValueError(f"dim deve ser positivo, recebido {dim}")
        self._db_path: Path = Path(db_path)
        self._dim: int = dim

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def init_schema(self) -> None:
        """Cria a tabela ``query_cache`` (idempotente)."""
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS query_cache (
                    query_hash TEXT PRIMARY KEY,
                    query_text TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    hit_count INTEGER NOT NULL DEFAULT 0,
                    last_used_at TEXT
                )
                """
            )
            conn.commit()

    def _hash(self, query: str) -> str:
        return _hash_query(query)

    def get(self, query: str) -> list[float] | None:
        """Retorna o embedding cacheado para ``query`` ou ``None``.

        Em caso de hit, atualiza ``hit_count`` e ``last_used_at``.
        Levanta ``RuntimeError`` se o blob recuperado tiver dim
        diferente de ``self._dim`` (cache corrompido).
        """
        h: str = self._hash(query)
        ts: str = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT embedding, hit_count FROM query_cache WHERE query_hash = ?",
                (h,),
            ).fetchone()
            if row is None:
                return None
            blob, _ = row
            expected_bytes: int = self._dim * 4  # float32 = 4 bytes
            if len(blob) != expected_bytes:
                raise RuntimeError(
                    f"cache corrompido: dim do blob={len(blob) // 4} != esperado={self._dim}"
                )
            # Hit registrado atomicamente com a leitura.
            conn.execute(
                "UPDATE query_cache SET hit_count = hit_count + 1, "
                "last_used_at = ? WHERE query_hash = ?",
                (ts, h),
            )
            conn.commit()
        return list(struct.unpack(f"{self._dim}f", blob))

    def put(self, query: str, embedding: list[float]) -> None:
        """Persiste ``(query, embedding)``. Idempotente (INSERT OR REPLACE)."""
        if len(embedding) != self._dim:
            raise ValueError(
                f"embedding dim {len(embedding)} != esperado {self._dim}"
            )
        h: str = self._hash(query)
        blob: bytes = struct.pack(f"{self._dim}f", *embedding)
        ts: str = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO query_cache("
                "query_hash, query_text, embedding, hit_count, last_used_at"
                ") VALUES (?, ?, ?, 0, ?)",
                (h, query.strip(), blob, ts),
            )
            conn.commit()

    def stats(self) -> dict[str, int]:
        """Metricas uteis para debug e telemetria."""
        with self._connect() as conn:
            n_entries = conn.execute(
                "SELECT COUNT(*) FROM query_cache"
            ).fetchone()[0]
            n_hits = conn.execute(
                "SELECT COALESCE(SUM(hit_count), 0) FROM query_cache"
            ).fetchone()[0]
        return {
            "total_entries": int(n_entries),
            "total_hits": int(n_hits),
        }


__all__ = ["QueryEmbeddingCache"]
