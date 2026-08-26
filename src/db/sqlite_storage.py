"""DAO relacional para a tabela `documents`.

Atributos e responsabilidades:
    - DocumentRecord: snapshot tipado de uma linha.
    - SqliteStorage: classe sem estado de conexao; cada metodo abre/fecha conexao
      via context manager ``sqlite3.connect`` para simplicidade e testabilidade.

Convensoes de serializacao:
    - ``Path`` <-> ``str``: ``str(file_path)``.
    - ``datetime`` <-> ``str``: ISO 8601 (UTC, sem timezone) via ``isoformat()``.

Versionamento (Sprint 2, Fase 9.1):
    - ``schema.sql`` representa o baseline v1.
    - ``schema_migrations/0002_doc_metadata.sql`` adiciona colunas/indices v2.
    - ``init_schema()`` aplica baseline e em seguida roda as migrations
      pendentes. Idempotente em qualquer versao ja aplicada.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from src.db.migrations import apply_pending, read_user_version
from src.db.schema_sql import SCHEMA_SQL


def _utcnow() -> datetime:
    """Retorna datetime naive em UTC (compat com Python 3.12+ sem DeprecationWarning)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class DocumentRecord:
    """Snapshot tipado de uma linha da tabela ``documents``.

    Campos ``None`` mapeiam para NULL no banco; campos opcionais
    (``file_path``, ``content_hash``, ``published_at``, ``ingested_at``)
    permanecem nulos ate serem preenchidos pelos estagios posteriores
    (download, parser, indexador).

    Campos adicionados na v2 (Sprint 2, Fase 9.1):
        - ``nt_number``: numero estruturado (ex: ``"2019.001"`` para NT).
        - ``version``: revisao explícita do documento (ex: ``"3.2"``).
        - ``replaces_doc_id``: FK para ``documents.id`` da versao anterior
          (substituicoes / republicacoes).
        - ``language``: codigo ISO 639-1 (default ``"pt-BR"``).
    """

    id: int | None = None
    url: str = ""
    source_domain: str = ""
    doc_type: str = ""
    title: str = ""
    file_path: Path | None = None
    content_hash: str | None = None
    published_at: datetime | None = None
    fetched_at: datetime = field(default_factory=_utcnow)
    ingested_at: datetime | None = None
    status: str = "nao_ingerido"
    nt_number: str | None = None
    version: str | None = None
    replaces_doc_id: int | None = None
    language: str | None = None


def _datetime_to_str(value: datetime | None) -> str | None:
    """Serializa datetime para ISO 8601; retorna None se o valor ja e None."""
    if value is None:
        return None
    return value.isoformat()


def _str_to_datetime(value: str | None) -> datetime | None:
    """Desserializa ISO 8601 para datetime naive (UTC); retorna None se vazio."""
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _path_to_str(value: Path | None) -> str | None:
    """Serializa Path para str; retorna None se o valor ja e None."""
    if value is None:
        return None
    return str(value)


def _str_to_path(value: str | None) -> Path | None:
    """Desserializa str para Path; retorna None se vazio."""
    if value is None:
        return None
    return Path(value)


def _row_to_record(row: sqlite3.Row) -> DocumentRecord:
    """Converte uma ``sqlite3.Row`` em ``DocumentRecord`` desserializando tipos.

    Tolerante a bancos pre-Fase-9: campos v2 ausentes sao tratados como
    ``None`` via ``row[...] if ... else None`` -- o teste com bancos legados
    nao quebra a desserializacao.
    """
    columns: set[str] = set(row.keys())

    def col(name: str) -> object | None:
        if name in columns:
            value = row[name]
            return value if value is not None else None
        return None

    return DocumentRecord(
        id=row["id"],
        url=row["url"],
        source_domain=row["source_domain"],
        doc_type=row["doc_type"],
        title=row["title"],
        file_path=_str_to_path(row["file_path"]),
        content_hash=row["content_hash"],
        published_at=_str_to_datetime(row["published_at"]),
        fetched_at=_str_to_datetime(row["fetched_at"]) or _utcnow(),
        ingested_at=_str_to_datetime(row["ingested_at"]),
        status=row["status"],
        nt_number=col("nt_number"),
        version=col("version"),
        replaces_doc_id=int(col("replaces_doc_id")) if col("replaces_doc_id") is not None else None,
        language=col("language"),
    )


class SqliteStorage:
    """DAO fino sobre ``sqlite3`` para a tabela ``documents``.

    Nao armazena conexao: cada operacao abre/fecha via ``with sqlite3.connect``
    para simplificar testes com ``tmp_path`` e evitar locks de longa duracao.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path: Path = db_path

    def _connect(self) -> sqlite3.Connection:
        """Abre conexao com ``Row`` factory para acesso por nome de coluna."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        """Executa o DDL baseline + aplica migrations pendentes (idempotente).

        Ordem das operacoes:
            1. ``SCHEMA_SQL`` (baseline v1) — CREATE TABLE/INDEX IF NOT EXISTS.
            2. :func:`apply_pending` — migrations com versao > ``PRAGMA
               user_version``. Adiciona colunas/indices v2 sem perder dados.

        Pode ser chamado multiplas vezes sobre o mesmo banco. ``schema.sql``
        nao cria colunas/indices v2 diretamente para nao falhar em bancos
        legados que ja tem a tabela ``documents`` (versao 1) sem essas
        colunas; o delta v2 vive somente na migration 0002.
        """
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)
            conn.commit()
        apply_pending(self._db_path)

    def migrate(self) -> int:
        """Aplica migrations pendentes. Retorna nova versao do schema.

        Conveniencia: delega para :func:`apply_pending`.
        Idempotente.
        """
        return apply_pending(self._db_path)

    def current_schema_version(self) -> int:
        """Retorna ``PRAGMA user_version`` atual do banco."""
        return read_user_version(self._db_path)

    def upsert_document(self, record: DocumentRecord) -> int:
        """Insere ou atualiza por ``url``, retornando o ``rowid`` da linha.

        Comportamento:
            - Se ``url`` nao existe: INSERT e retorna o novo ``rowid``.
            - Se ``url`` ja existe: UPDATE dos campos e retorna o ``rowid`` existente.

        ``fetched_at`` e sobrescrito em cada chamada para refletir a ultima
        atualizacao bem-sucedida. Usa ``RETURNING id`` (SQLite >= 3.35, bundled
        em Python 3.11+) para obter o ``rowid`` tanto em INSERT novo quanto em
        UPDATE por conflito, ja que ``cursor.lastrowid`` retorna 0 para a segunda
        via.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO documents (
                    url, source_domain, doc_type, title,
                    file_path, content_hash, published_at, fetched_at,
                    ingested_at, status,
                    nt_number, version, replaces_doc_id, language
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    source_domain = excluded.source_domain,
                    doc_type = excluded.doc_type,
                    title = excluded.title,
                    file_path = excluded.file_path,
                    content_hash = excluded.content_hash,
                    published_at = excluded.published_at,
                    fetched_at = excluded.fetched_at,
                    status = excluded.status,
                    nt_number = excluded.nt_number,
                    version = excluded.version,
                    replaces_doc_id = excluded.replaces_doc_id,
                    language = excluded.language
                RETURNING id
                """,
                (
                    record.url,
                    record.source_domain,
                    record.doc_type,
                    record.title,
                    _path_to_str(record.file_path),
                    record.content_hash,
                    _datetime_to_str(record.published_at),
                    _datetime_to_str(record.fetched_at),
                    _datetime_to_str(record.ingested_at),
                    record.status,
                    record.nt_number,
                    record.version,
                    record.replaces_doc_id,
                    record.language,
                ),
            )
            row = cursor.fetchone()
            conn.commit()
            if row is None:
                raise sqlite3.DatabaseError("upsert_document nao retornou rowid")  # pragma: no cover
            return int(row[0])

    def get_by_url(self, url: str) -> DocumentRecord | None:
        """Retorna o registro com a ``url`` indicada ou ``None`` se ausente."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE url = ?", (url,)
            ).fetchone()
        if row is None:
            return None
        return _row_to_record(row)

    def get_by_hash(self, content_hash: str) -> DocumentRecord | None:
        """Retorna o primeiro registro com o ``content_hash`` indicado ou ``None``.

        ``content_hash`` nao e UNIQUE por desenho (multiplos docs identicos podem
        coexistir teoricamente), mas para o padrao de ingestao idempotente
        basta a primeira ocorrencia.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE content_hash = ? LIMIT 1",
                (content_hash,),
            ).fetchone()
        if row is None:
            return None
        return _row_to_record(row)

    def get_by_nt_number(self, nt_number: str) -> DocumentRecord | None:
        """Retorna o registro cujo ``nt_number`` bate com o argumento.

        Args:
            nt_number: numero de NT no formato ``"AAAA.NNN"`` (ex: ``"2019.001"``).

        Returns:
            Primeiro registro com o NT indicado ou ``None`` se ausente.
            Quando existirem multiplas revisoes de uma mesma NT, retorna
            aquela com maior ``id`` (ultima republicacao) para favorecer
            versao atual — comportamento util para a regra do projeto
            que prefere a versao mais recente.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE nt_number = ? ORDER BY id DESC LIMIT 1",
                (nt_number,),
            ).fetchone()
        if row is None:
            return None
        return _row_to_record(row)

    def list_pending(self) -> list[DocumentRecord]:
        """Retorna todos os documentos com ``status='nao_ingerido'``."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM documents WHERE status = 'nao_ingerido' ORDER BY id"
            ).fetchall()
        return [_row_to_record(row) for row in rows]

    def list_by_doc_type(self, doc_type: str) -> list[DocumentRecord]:
        """Retorna todos os documentos cujo ``doc_type`` bate com o argumento.

        Ordena por ``published_at`` DESC (mais recente primeiro) para que
        chamadas tipicas do agente (pergunta sobre uma NT) recebam primeiro
        as versoes mais novas.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM documents WHERE doc_type = ? "
                "ORDER BY published_at DESC NULLS LAST, id",
                (doc_type,),
            ).fetchall()
        return [_row_to_record(row) for row in rows]

    def list_replaced_by(self, replaces_doc_id: int) -> list[DocumentRecord]:
        """Retorna todos os documentos que substituem o registro indicado.

        Caso de uso: dado o doc A, ``list_replaced_by(A.id)`` retorna todos
        os docs B/C/D que foram republicados com a coluna
        ``replaces_doc_id = A.id``. Ordena por ``published_at`` DESC para
        que o agente pegue a versao mais recente primeiro.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM documents WHERE replaces_doc_id = ? "
                "ORDER BY published_at DESC NULLS LAST, id",
                (replaces_doc_id,),
            ).fetchall()
        return [_row_to_record(row) for row in rows]

    def mark_ingested(self, document_id: int) -> None:
        """Marca o registro como ingerido, preenchendo ``ingested_at`` com UTC."""
        ingested_at: str = _utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE documents SET status = 'ingerido', ingested_at = ? WHERE id = ?",
                (ingested_at, document_id),
            )
            conn.commit()

    def mark_failed(self, document_id: int) -> None:
        """Marca o registro como falho. NAO altera ``ingested_at`` (continua NULL)."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE documents SET status = 'falhou' WHERE id = ?",
                (document_id,),
            )
            conn.commit()


__all__ = [
    "DocumentRecord",
    "SqliteStorage",
    "apply_pending",
    "read_user_version",
]  # re-exported for convenience; primary surface is SqliteStorage methods.
