"""Migrations do schema relacional do DFe-Agent (Sprint 2+, Fase 9).

Cada nova versao do schema vive em uma funcao ``_apply_vN(conn)`` que recebe
uma conexao aberta e aplica a migration de forma idempotente
(``ADD COLUMN`` via ``PRAGMA table_info`` + ``CREATE INDEX IF NOT EXISTS``).

Estrategia de upgrade:
    1. ``SqliteStorage.init_schema()`` aplica ``schema.sql`` (baseline v1).
    2. Em seguida, chama :func:`apply_pending` que executa
       ``_apply_vN(conn)`` para cada versao ``N > user_version``.
    3. Cada ``_apply_vN`` checa PRAGMA table_info para garantir
       idempotencia sem depender de ``ALTER TABLE ADD COLUMN IF NOT EXISTS``
       (sintaxe nao suportada pela versao do SQLite bundled com Python).

Adicionar uma nova migration:
    1. Incrementar ``CURRENT_VERSION``.
    2. Adicionar ``def _apply_vN(conn)`` que aplica o delta de forma
       idempotente.
    3. Adicionar ``(N, _apply_vN)`` em ``_MIGRATIONS``.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

CURRENT_VERSION: int = 6
MIGRATIONS_DIR: Path = Path(__file__).resolve().parent / "schema_migrations"


__all__ = ["CURRENT_VERSION", "MIGRATIONS_DIR", "apply_pending", "read_user_version"]


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Retorna o conjunto de colunas ja presentes na ``table``."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def _ensure_column(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    ddl: str,
    existing: set[str] | None = None,
) -> None:
    """Adiciona coluna a ``table`` apenas se ainda nao existir.

    ``ddl`` deve ser o fragmento apos o nome da coluna, ex:
    ``"TEXT"`` ou ``"INTEGER REFERENCES documents(id)"``.

    Args:
        conn: Conexao SQLite.
        table: Nome da tabela alvo.
        column: Nome da coluna a adicionar.
        ddl: Tipo/DDL da coluna (apos o nome).
        existing: Conjunto pre-computado de colunas ja presentes em
            ``table`` (cache de ``PRAGMA table_info``). Quando ``None``
            (default), ``_ensure_column`` faz a query (caso nao
            otimizado). Quando informado, NAO chama PRAGMA — uso
            recomendado dentro de loops/migrations que checam
            multiplas colunas (PLAN_SPRINT4 E.1).
    """
    cols: set[str] = (
        existing if existing is not None else _existing_columns(conn, table)
    )
    if column in cols:
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def _apply_v2(conn: sqlite3.Connection) -> None:
    """Sprint 2 / Fase 9.1: metadados estruturados em ``documents``.

    Adiciona as colunas ``nt_number``, ``version``, ``replaces_doc_id`` e
    ``language``, alem de 3 indices para acelerar busca por NT/tipo/data.
    Idempotente.

    Otimizacao (PLAN_SPRINT4 E.1 / IMPORTANTE #4): ``PRAGMA table_info(documents)``
    e' chamado apenas 1 vez por execution; o resultado e' passado para
    as 4 chamadas a ``_ensure_column`` via parametro ``existing``.
    """
    existing: set[str] = _existing_columns(conn, "documents")
    _ensure_column(
        conn, "documents", "nt_number", "TEXT", existing=existing
    )
    _ensure_column(
        conn, "documents", "version", "TEXT", existing=existing
    )
    _ensure_column(
        conn,
        "documents",
        "replaces_doc_id",
        "INTEGER REFERENCES documents(id)",
        existing=existing,
    )
    _ensure_column(
        conn, "documents", "language", "TEXT DEFAULT 'pt-BR'", existing=existing
    )

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_documents_nt_number "
        "ON documents(nt_number)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_documents_doc_type "
        "ON documents(doc_type)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_documents_published_at "
        "ON documents(published_at)"
    )


def _apply_v3(conn: sqlite3.Connection) -> None:
    """Sprint 2 / Fase 10.1: sidecar ``chunk_metadata`` para chunking estrutural.

    Cria a tabela ``chunk_metadata(document_id, chunk_index, section_path,
    section_level)`` com PK composta ``(document_id, chunk_index)``. Usada
    por :class:`src.db.vector_store.VectorStore` para fazer LEFT JOIN
    sobre ``vec_chunks`` e devolver o contexto de secao NT nos
    resultados de busca sem precisar reconstruir o ``vec0`` table
    existente (que nao suporta ALTER ADD COLUMN no SQLite bundled).

    Compatibilidade retroativa: chunks pre-Fase-10 NAO tem entrada em
    ``chunk_metadata``; o LEFT JOIN produz NULL/empty e o ScoredChunk
    sai com ``section_path=""`` e ``section_level=0``. Nao exige
    reindexacao.

    Idempotente.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chunk_metadata (
            document_id   INTEGER NOT NULL,
            chunk_index   INTEGER NOT NULL,
            section_path  TEXT NOT NULL DEFAULT '',
            section_level INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (document_id, chunk_index)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunk_metadata_section_path "
        "ON chunk_metadata(section_path)"
    )


def _apply_v4(conn: sqlite3.Connection) -> None:
    """Sprint 2 / Fase 11.1: indice FTS5 para busca textual (BM25).

    Cria a virtual table ``fts_chunks`` indexando os textos dos chunks
    ja persistidos em ``vec_chunks``. Campos UNINDEXED sao apenas
    metadados retornados junto com o hit; nao influenciam o ranking.

    Tokenizer ``unicode61 remove_diacritics 2``: normaliza acentos no
    indice (busca por ``cancelamento`` acha tanto ``cancelamento`` quanto
    ``cancelamênto``), util para documentos fiscais em PT-BR com
    inconsistencias de encoding.

    Backfill: o populate do indice a partir de vec_chunks pre-existentes
    NAO e parte desta migration (idempotencia). Quem chama
    ``FtsStore.init_schema`` dispara :func:`FtsStore.rebuild_from_db`
    se a tabela FTS estiver vazia.

    Idempotente.
    """
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS fts_chunks USING fts5(
            text,
            section_path,
            document_id UNINDEXED,
            chunk_index UNINDEXED,
            source_url UNINDEXED,
            doc_title UNINDEXED,
            tokenize = 'unicode61 remove_diacritics 2'
        )
        """
    )


def _apply_v5(conn: sqlite3.Connection) -> None:
    """Sprint 2 / Fase 12.1: tabela ``doc_summaries`` para retrieval hierarquico.

    Cria a tabela ``doc_summaries(document_id, summary, embedding, created_at)``
    com PK em ``document_id`` (FK para ``documents.id``, nao declarada
    para evitar dependencias de migracao). Armazena o resumo deterministico
    (gerado por :func:`src.indexer.summarizer.summarize`) e seu embedding
    para uso no primeiro estagio de :meth:`QueryEngine.search_hierarchical`.

    Decisao de escala: como ``documents`` tera <= milhares de linhas,
    o brute-force cosine sobre ``doc_summaries`` e aceitavel e mais
    simples do que uma segunda vec0 virtual table. Para escala maior,
    a migration pode ser estendida para apontar para um vec0 proprio.

    Idempotente. Backfill de summaries pre-existentes NAO e parte desta
    migration — quem chama :meth:`RagIndexer.ingest_*` gera o sumario
    para novos docs; backfill retroativo pode ser disparado manualmente
    (nao escopo da Sprint 2 / Fase 12.1).
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS doc_summaries (
            document_id INTEGER PRIMARY KEY,
            summary TEXT NOT NULL,
            embedding BLOB,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_doc_summaries_created_at "
        "ON doc_summaries(created_at)"
    )


def _apply_v6(conn: sqlite3.Connection) -> None:
    """Sprint 2 / Fase 14.1: parent-document retrieval em ``chunk_metadata``.

    Adiciona colunas ``kind`` e ``parent_chunk_id`` ao sidecar
    ``chunk_metadata``. Cada chunk pode ser:
        ``'detail'``   — pedaco pequeno (chunk normal).
        ``'parent'``   — paragrafo inteiro (contexto).
        ``'summary'``  — representacao per-document (cross-link).

    ``parent_chunk_id`` aponta (quando ``kind='detail'``) para o row de
    ``chunk_metadata`` cujo ``kind='parent'`` cobre o detalhe. Permite
    que o retrieval devolva o parent (paragraph inteiro) quando so
    detalhes batem no top-K.

    Migracao aditiva (nao toca ``vec_chunks`` vec0). Idempotente.

    Otimizacao (PLAN_SPRINT4 E.1 / IMPORTANTE #4): ``PRAGMA table_info(chunk_metadata)``
    e' chamado apenas 1 vez por execution; o resultado e' reusado
    nas 2 checagens de ``kind`` e ``parent_chunk_id``.
    """
    existing_chunk_meta: set[str] = {
        row[1] for row in conn.execute("PRAGMA table_info(chunk_metadata)")
    }
    if "kind" not in existing_chunk_meta:
        conn.execute(
            "ALTER TABLE chunk_metadata ADD COLUMN kind TEXT NOT NULL DEFAULT 'detail'"
        )
    if "parent_chunk_id" not in existing_chunk_meta:
        conn.execute(
            "ALTER TABLE chunk_metadata ADD COLUMN parent_chunk_id INTEGER"
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunk_metadata_kind "
        "ON chunk_metadata(kind)"
    )


# Mapeamento versao -> funcao de aplicacao. Adicionar (7, _apply_v7) no
# futuro quando uma nova migration for introduzida.
_MIGRATIONS: dict[int, callable] = {
    2: _apply_v2,
    3: _apply_v3,
    4: _apply_v4,
    5: _apply_v5,
    6: _apply_v6,
}


def read_user_version(db_path: Path) -> int:
    """Le ``PRAGMA user_version`` do banco; retorna 0 se nao aplicavel."""
    with sqlite3.connect(db_path) as conn:
        row: tuple[int] | None = conn.execute("PRAGMA user_version").fetchone()
    if row is None:
        return 0
    return int(row[0])


def _set_user_version(conn: sqlite3.Connection, version: int) -> None:
    """Atualiza ``PRAGMA user_version``."""
    conn.execute(f"PRAGMA user_version = {int(version)}")


def _expected_tables(version: int) -> list[str]:
    """Tabelas/indices que devem existir apos a migration ``version``."""
    return {
        3: ["chunk_metadata"],
        4: ["fts_chunks"],
        6: ["chunk_metadata", "fts_chunks"],  # combina v3+v6
    }.get(version, [])


def _is_table_missing(conn: sqlite3.Connection, table: str) -> bool:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table') AND name = ?",
        (table,),
    ).fetchall()
    return len(rows) == 0


def apply_pending(db_path: Path, target_version: int = CURRENT_VERSION) -> int:
    """Aplica migrations com ``version > current`` ate ``target_version``.

    Idempotente contra execucoes repetidas. TAMBEM detecta tabelas
    dropadas manualmente (ex: ``DROP TABLE`` em cmd_reindex) e
    reaplica as migrations correspondentes para recriar a tabela —
    desde que sua versao esteja dentro de ``[current, target]``.

    Args:
        db_path: Caminho do banco de dados (sera criado se nao existir).
        target_version: Versao alvo. Defaults to ``CURRENT_VERSION``.

    Returns:
        Versao apos aplicacao (igual a ``max(read_user_version(), target_version)``
        ou igual a ``CURRENT_VERSION`` se nenhum delta foi necessario).
    """
    current: int = read_user_version(db_path)
    pending_versions: list[int] = sorted(
        version for version in _MIGRATIONS if current < version <= target_version
    )

    # Detecta tabelas dropadas manualmente (DROP TABLE explcito em
    # cmd_reindex) e reaplica as migrations correspondentes para
    # recria-las, mesmo com user_version ja em target.
    rebuild_versions: list[int] = []
    if current >= target_version:
        with sqlite3.connect(db_path) as conn:
            for version in sorted(_MIGRATIONS.keys()):
                if version > target_version:
                    break
                for table in _expected_tables(version):
                    if _is_table_missing(conn, table):
                        if version not in rebuild_versions:
                            rebuild_versions.append(version)
        if not rebuild_versions:
            return current
        pending_versions = rebuild_versions

    if not pending_versions:
        return current

    with sqlite3.connect(db_path) as conn:
        for version in pending_versions:
            _MIGRATIONS[version](conn)
            _set_user_version(conn, version)
        conn.commit()

    return read_user_version(db_path)
