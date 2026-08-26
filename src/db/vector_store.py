"""DAO vetorial: persistencia e busca de chunks com embeddings via sqlite-vec.

Sprint 2:
    - Fase 10.1: alem de ``vec_chunks`` (vec0), busca e insercao fazem
      LEFT JOIN com a tabela relacional ``chunk_metadata`` (sidecar)
      para anotar contexto estrutural (``section_path``/
      ``section_level``) nos chunks retornados.
    - Fase 11.1: ``VectorStore.insert_chunks`` sincroniza com
      ``FtsStore`` (FTS5 + BM25) quando o caller fornece uma
      instancia. Mantem o indice textual em sincronia com o vetorial
      sem exigir trigger (cada novo chunk aparece nos dois backends
      atomicamente do ponto de vista do Python — em transacoes
      separadas).
    - Fase 14.1: ``kind`` e ``parent_chunk_id`` no sidecar.

Sprint 3 / Iter 5:
    - ``search`` foi quebrado em 2 queries (Fase 14.1 causa hang > 60s
      por causa de LEFT JOIN de vec_chunks sobre si mesmo em bases
      grandes — sqlite-vec nao otimiza o plano). Agora a Fase 2
      (parent lookup) e O(k) onde k = top-K.
"""
from __future__ import annotations

import sqlite3
import struct
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import sqlite_vec

if TYPE_CHECKING:
    from src.db.fts_store import FtsStore


@dataclass
class ChunkRecord:
    document_id: int
    chunk_index: int
    text: str
    embedding: list[float]
    source_url: str
    doc_title: str
    section_path: str = ""
    section_level: int = 0
    kind: str = "detail"  # 'detail' | 'parent' | 'summary'
    parent_chunk_id: int | None = None


@dataclass
class ScoredChunk:
    text: str
    source_url: str
    doc_title: str
    score: float
    document_id: int = 0
    published_at: datetime | None = None
    section_path: str = ""
    section_level: int = 0
    kind: str = "detail"
    parent_text: str | None = None


class VectorStore:
    def __init__(
        self,
        db_path: Path,
        dim: int,
        fts_store: "FtsStore | None" = None,
    ) -> None:
        if dim <= 0:
            raise ValueError(f"dim deve ser positivo, recebido {dim}")
        self._db_path: Path = Path(db_path)
        self._dim: int = dim
        self._fts_store: FtsStore | None = fts_store

    def init_schema(self) -> None:
        """Cria ``vec_chunks`` (vec0) e reaplica migrations para sidecars.

        Idempotente. Tambem aplica migrations 0003 (chunk_metadata) e
        0004 (fts_chunks) via ``apply_pending`` — util apos um DROP
        explicito (ex: ``ragctl reindex``) para recriar as tabelas
        sem ter que incrementar a versao do schema.
        """
        from src.db.migrations import apply_pending

        ddl = (
            "CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0("
            f"embedding float[{self._dim}], "
            "document_id INTEGER, "
            "chunk_index INTEGER, "
            "text TEXT, "
            "source_url TEXT, "
            "doc_title TEXT)"
        )
        with self._connect() as conn:
            conn.execute(ddl)
            conn.commit()
        apply_pending(self._db_path)

    def insert_chunks(self, chunks: list[ChunkRecord]) -> None:
        if not chunks:
            return
        vec_rows: list[tuple[bytes, int, int, str, str, str]] = [
            (
                struct.pack(f"{self._dim}f", *chunk.embedding),
                chunk.document_id,
                chunk.chunk_index,
                chunk.text,
                chunk.source_url,
                chunk.doc_title,
            )
            for chunk in chunks
        ]
        meta_rows: list[tuple[int, int, str, int, str, int | None]] = [
            (
                chunk.document_id,
                chunk.chunk_index,
                chunk.section_path,
                chunk.section_level,
                chunk.kind,
                chunk.parent_chunk_id,
            )
            for chunk in chunks
        ]
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO vec_chunks(embedding, document_id, chunk_index, "
                "text, source_url, doc_title) VALUES (?, ?, ?, ?, ?, ?)",
                vec_rows,
            )
            conn.executemany(
                "INSERT OR REPLACE INTO chunk_metadata("
                "document_id, chunk_index, section_path, section_level, "
                "kind, parent_chunk_id"
                ") VALUES (?, ?, ?, ?, ?, ?)",
                meta_rows,
            )
            conn.commit()

        # Sincronia com FTS5 (Fase 11.1).
        if self._fts_store is not None:
            self._fts_store.insert_chunks(chunks)

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        document_ids: list[int] | None = None,
    ) -> list[ScoredChunk]:
        """Busca os ``top_k`` chunks mais proximos no espaco vetorial.

        Implementacao em 2 queries (split):
          1. Query principal em ``vec_chunks`` com LEFT JOIN em
             ``documents`` e ``chunk_metadata`` (3-way). Segura para
             30k chunks (< 1s).
          2. Enriquecimento opcional com ``parent_text`` via query
             especifica (apenas para chunks retornados com parent).
             O LEFT JOIN inline de ``vec_chunks`` sobre si mesmo na
             query 1 travava o plano do sqlite-vec em bases >10k
             chunks (hang > 60s); a query alvo e O(k) onde k = top-K.

        Args:
            query_embedding: Vetor de dimensao ``self._dim`` da pergunta.
            top_k: Quantos chunks retornar.
            document_ids: Quando informado e nao vazio, restringe a busca
                a chunks desses documentos. ``None`` ou ``[]`` = sem restricao.
        """
        query_blob = struct.pack(f"{self._dim}f", *query_embedding)
        with self._connect() as conn:
            sql = """
                SELECT
                    vc.text,
                    vc.source_url,
                    vc.doc_title,
                    vc.document_id,
                    vc.chunk_index,
                    COALESCE(d.published_at, d.fetched_at) AS pub_at,
                    COALESCE(cm.section_path, '') AS section_path,
                    COALESCE(cm.section_level, 0) AS section_level,
                    COALESCE(cm.kind, 'detail') AS kind,
                    vec_distance_cosine(vc.embedding, ?) AS distance
                FROM vec_chunks vc
                LEFT JOIN documents d ON d.id = vc.document_id
                LEFT JOIN chunk_metadata cm
                    ON cm.document_id = vc.document_id
                   AND cm.chunk_index = vc.chunk_index
            """
            params: list[object] = [query_blob]
            if document_ids:
                placeholders: str = ",".join("?" * len(document_ids))
                sql += f" WHERE vc.document_id IN ({placeholders})"
                params.extend(int(d) for d in document_ids)
            sql += " ORDER BY distance ASC LIMIT ?"
            params.append(int(top_k))
            rows = conn.execute(sql, params).fetchall()

            # Fase 2: parent lookup O(k) sobre os chunks retornados.
            parent_lookup: dict[tuple[int, int], str] = self._fetch_parents_for(
                conn,
                [
                    (int(r[3]) if r[3] is not None else 0, int(r[4]))
                    for r in rows
                ],
            )

        results: list[ScoredChunk] = []
        for (
            text,
            url,
            title,
            doc_id,
            _chunk_idx,
            pub_at_str,
            section_path,
            section_level,
            kind,
            distance,
        ) in rows:
            pub_at = datetime.fromisoformat(pub_at_str) if pub_at_str else None
            results.append(
                ScoredChunk(
                    text=text,
                    source_url=url,
                    doc_title=title,
                    score=1.0 - distance,
                    document_id=int(doc_id) if doc_id is not None else 0,
                    published_at=pub_at,
                    section_path=section_path or "",
                    section_level=int(section_level) if section_level is not None else 0,
                    kind=kind or "detail",
                    parent_text=parent_lookup.get(
                        (int(doc_id) if doc_id is not None else 0, int(_chunk_idx))
                    ),
                )
            )
        return results

    def _fetch_parents_for(
        self,
        conn: sqlite3.Connection,
        chunk_keys: list[tuple[int, int]],
    ) -> dict[tuple[int, int], str]:
        """Para os chunks dados, devolve mapa ``(doc_id, chunk_index) -> parent_text``.

        Apenas os chunks com parent_chunk_id setado sao incluidos.
        A chave do mapa e o chunk FILHO (não o parent) — quem recebe o
        ``ScoredChunk`` com chave ``(doc_id, chunk_index)`` faz
        ``parent_lookup.get((self.document_id, self.chunk_index))``
        e recebe o texto do parent.

        Complexidade: O(k) onde k = len(chunk_keys).
        """
        if not chunk_keys:
            return {}

        unique_keys: list[tuple[int, int]] = list(set(chunk_keys))

        # 1. Descobre (child -> parent) para os chunks com parent setado.
        flat: list[int] = [v for pair in unique_keys for v in pair]
        placeholders: str = ",".join("(?,?)" for _ in range(len(unique_keys)))
        rows = conn.execute(
            f"""
            SELECT cm.document_id, cm.chunk_index, cm.parent_chunk_id
            FROM chunk_metadata cm
            WHERE (cm.document_id, cm.chunk_index) IN (VALUES {placeholders})
              AND cm.parent_chunk_id IS NOT NULL
            """,
            flat,
        ).fetchall()

        if not rows:
            return {}

        # 2. Para cada parent, busca o texto em vec_chunks.
        parent_keys: list[tuple[int, int]] = [
            (doc_id, parent_idx) for doc_id, _, parent_idx in rows
        ]
        flat2: list[int] = [v for pair in parent_keys for v in pair]
        placeholders2: str = ",".join(
            "(?,?)" for _ in range(len(parent_keys))
        )
        text_rows = conn.execute(
            f"""
            SELECT document_id, chunk_index, text
            FROM vec_chunks
            WHERE (document_id, chunk_index) IN (VALUES {placeholders2})
            """,
            flat2,
        ).fetchall()
        # text_map: parent_key -> parent_text
        parent_text_map: dict[tuple[int, int], str] = {
            (d, c): t for d, c, t in text_rows
        }

        # 3. Reverte o mapa: para cada child, encontre seu parent.
        # child -> parent via cm.parent_chunk_id.
        result: dict[tuple[int, int], str] = {}
        for doc_id, chunk_idx, parent_idx in rows:
            text: str | None = parent_text_map.get((doc_id, parent_idx))
            if text is not None:
                result[(doc_id, chunk_idx)] = text
        return result

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        return conn

    @property
    def db_path(self) -> Path:
        """Caminho do banco (util para DAOs vizinhos como ``DocSummaryStore``)."""
        return self._db_path


__all__ = [
    "ChunkRecord",
    "ScoredChunk",
    "VectorStore",
]