"""DAO de busca textual via FTS5: complemento BM25 do vetorial (Sprint 2, Fase 11).

A virtual table ``fts_chunks`` e criada pela migration 0004
(:mod:`src.db.migrations`). Para um banco recem-migrado de versao
anterior, ``FtsStore.rebuild_from_db`` popula o indice a partir de
``vec_chunks`` + ``chunk_metadata``.

Operacoes:
    - ``init_schema()``: idempotente.
    - ``insert_chunk(chunk)``: insere um chunk no indice FTS5. Em
      geral usado pelo :class:`VectorStore` via sincronia automatica.
    - ``rebuild_from_db()``: ``INSERT INTO fts_chunks SELECT ... FROM
      vec_chunks`` (apenas registros ainda nao presentes). Idempotente.
    - ``search_fts(query, top_k=30)``: BM25 nativo do FTS5, retorna
      :class:`FtsHit`.

Quando usar:
    - ``QueryEngine.search_hybrid`` faz fusao RRF (BM25 + cosseno).
    - O fallback para query SO com FTS esta' disponivel diretamente
      (:func:`search_fts`).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import sqlite_vec

if TYPE_CHECKING:
    from src.db.vector_store import ChunkRecord


@dataclass
class FtsHit:
    """Hit de busca textual BM25."""

    document_id: int
    chunk_index: int
    text: str
    source_url: str
    doc_title: str
    section_path: str = ""
    section_level: int = 0
    bm25_score: float = 0.0


class FtsStore:
    """Wrapper leve sobre a virtual table ``fts_chunks``."""

    def __init__(self, db_path: Path) -> None:
        """Configura o DAO FTS5.

        Args:
            db_path: Caminho do banco SQLite (mesmo usado por
                ``VectorStore`` e ``SqliteStorage``). A sincronia com
                ``VectorStore`` e feita passando o ``FtsStore`` no
                ``VectorStore.__init__(fts_store=this)``.
        """
        self._db_path: Path = Path(db_path)

    def init_schema(self) -> None:
        """Aplica a migration 0004 (cria ``fts_chunks``); idempotente."""
        from src.db.migrations import apply_pending

        apply_pending(self._db_path)

    def _connect(self) -> sqlite3.Connection:
        """Abre conexao com a extensao ``sqlite-vec`` carregada.

        A extensao nao e' estritamente necessaria para queries FTS5,
        mas mantemos a carga para permitir ``SELECT`` que facam LEFT JOIN
        com ``vec_chunks`` (caso a aplicacao queira).
        """
        conn = sqlite3.connect(self._db_path)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        return conn

    def insert_chunk(self, chunk: "ChunkRecord") -> None:
        """Insere um chunk no indice FTS5. Idempotente por (doc, idx)."""
        self.insert_chunks([chunk])

    def insert_chunks(self, chunks: "list[ChunkRecord] | list") -> None:
        """Insere multiplos chunks via ``executemany``."""
        if not chunks:
            return
        rows: list[tuple[str, str, int, int, str, str]] = [
            (
                chunk.text,
                chunk.section_path,
                chunk.document_id,
                chunk.chunk_index,
                chunk.source_url,
                chunk.doc_title,
            )
            for chunk in chunks
        ]
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO fts_chunks("
                "text, section_path, document_id, chunk_index, "
                "source_url, doc_title"
                ") VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()

    def rebuild_from_db(self) -> int:
        """Backfilla ``fts_chunks`` a partir de ``vec_chunks`` + ``chunk_metadata``.

        Insere apenas chunks ainda nao presentes (idempotencia por
        ``document_id, chunk_index``). Chunks legados ficam com
        ``section_path=""``.

        Returns:
            Numero de linhas inseridas nesta chamada.
        """
        with self._connect() as conn:
            existing: set[tuple[int, int]] = {
                (r[0], r[1])
                for r in conn.execute(
                    "SELECT document_id, chunk_index FROM fts_chunks"
                ).fetchall()
            }
            rows = conn.execute(
                """
                SELECT
                    vc.text,
                    COALESCE(cm.section_path, '') AS section_path,
                    vc.document_id,
                    vc.chunk_index,
                    vc.source_url,
                    vc.doc_title,
                    COALESCE(cm.section_level, 0) AS section_level
                FROM vec_chunks vc
                LEFT JOIN chunk_metadata cm
                    ON cm.document_id = vc.document_id
                   AND cm.chunk_index = vc.chunk_index
                """
            ).fetchall()

            inserted: int = 0
            for text, section_path, doc_id, chunk_idx, url, title, sec_lvl in rows:
                if (doc_id, chunk_idx) in existing:
                    continue
                conn.execute(
                    "INSERT INTO fts_chunks("
                    "text, section_path, document_id, chunk_index, "
                    "source_url, doc_title"
                    ") VALUES (?, ?, ?, ?, ?, ?)",
                    (text, section_path, doc_id, chunk_idx, url, title),
                )
                inserted += 1
            conn.commit()
            return inserted

    def search_fts(self, query: str, top_k: int = 30) -> list[FtsHit]:
        """Busca textual via BM25.

        Args:
            query: string com a consulta. Tokens sao normalizados pelo
                tokenizer (``unicode61 remove_diacritics``); use aspas
                para forcas match exato (ex: ``"'Convenio 123/2024'"``).
            top_k: limite de resultados.

        Returns:
            Lista de :class:`FtsHit` ordenada por BM25 (mais relevante
            primeiro). Lista vazia em caso de query vazia / invalida /
            sem matches.
        """
        if not query or not query.strip():
            return []

        with self._connect() as conn:
            try:
                rows = conn.execute(
                    """
                    SELECT
                        document_id,
                        chunk_index,
                        text,
                        source_url,
                        doc_title,
                        COALESCE(section_path, '') AS section_path,
                        bm25(fts_chunks) AS bm
                    FROM fts_chunks
                    WHERE fts_chunks MATCH ?
                    ORDER BY bm
                    LIMIT ?
                    """,
                    (query, top_k),
                ).fetchall()
            except sqlite3.OperationalError:
                # Query FTS5 invalida (sintaxe); retorna vazio.
                return []

        hits: list[FtsHit] = []
        for doc_id, chunk_idx, text, url, title, section_path, bm in rows:
            hits.append(
                FtsHit(
                    document_id=int(doc_id),
                    chunk_index=int(chunk_idx),
                    text=text,
                    source_url=url,
                    doc_title=title,
                    section_path=section_path or "",
                    bm25_score=float(bm),
                )
            )
        return hits


__all__ = ["FtsHit", "FtsStore"]
