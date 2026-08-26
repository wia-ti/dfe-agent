"""Coletor de documentos: orquestra descoberta, registro e download.

``DocumentCollector`` combina o descobridor por portal com o storage SQLite.
Os metodos publicos sao:

    - ``discover_and_register``: para cada source conhecida, executa
      ``discover_documents`` e insere novos registros no banco (idempotente).
    - ``download_pending``: para cada registro com ``status='nao_ingerido'``,
      faz throttled GET, calcula ``sha256`` e grava em ``data_dir``.

Validacao de URL (PLAN_SPRINT4 A.3):
    Usa ``src.utils.http_guard.validate_url`` para filtrar URLs antes
    do download. Esta camada importa ``hooks.domain_guard``
    internamente (fail-closed, BLOQUEANTE #2). O coletor NAO importa
    ``domain_guard`` diretamente.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from src.collector.portal_index import PORTAL_URLS, discover_documents
from src.db.sqlite_storage import DocumentRecord, SqliteStorage
from src.utils.http_guard import ALLOWED_DOMAINS, validate_url
from src.utils.throttler import Throttler


_DOWNLOAD_EXTENSIONS: tuple[str, ...] = (".pdf", ".html", ".htm")
_DOWNLOAD_TIMEOUT_S: int = 60


def _extract_source_domain(url: str) -> str:
    """Extrai o hostname de uma URL, removendo prefixo ``www.`` quando existir."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return ""
    host = parsed.hostname or ""
    if host.startswith("www."):
        host = host[4:]
    return host


def _extension_for(url: str) -> str:
    """Determina a extensao de download (com ponto, lowercased) ou fallback ``.bin``."""
    lowered = url.lower()
    for ext in _DOWNLOAD_EXTENSIONS:
        if lowered.endswith(ext):
            return ext
    return ".bin"


class DocumentCollector:
    """Orquestra discovery + download com throttling e idempotencia."""

    def __init__(
        self,
        storage: SqliteStorage,
        throttler: Throttler,
        data_dir: Path,
        allowed_domains: list[str] = ALLOWED_DOMAINS,
    ) -> None:
        self._storage: SqliteStorage = storage
        self._throttler: Throttler = throttler
        self._data_dir: Path = data_dir
        self._allowed_domains: list[str] = allowed_domains
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def discover_and_register(self) -> int:
        """Descobre documentos em cada portal e os registra no storage.

        Para cada ``source`` em ``PORTAL_URLS``, chama ``discover_documents``.
        Cada URL retornada e validada por ``validate_url``; URLs validas que
        ainda nao existem no banco sao inseridas como ``DocumentRecord`` com
        ``status='nao_ingerido'``. ``published_at`` e extraido do titulo
        pelo portal_index (regex "Publicado em DD/MM/YYYY").

        Quando ``discover_documents`` levanta ``requests.RequestException``
        (NXDOMAIN, timeout, 403), o erro e' categorizado em
        ``src.collector.__main__._categorize_request_error`` para distinguir
        DNS / timeout / refused. Plano: PLAN_SPRINT7 C.2 (I7.1).

        Returns:
            Numero de documentos NOVOS inseridos (idempotente: chamadas
            repetidas com a mesma base retornam 0).
        """
        inserted: int = 0
        for source in PORTAL_URLS:
            try:
                docs: list[dict[str, Any]] = discover_documents(
                    source, self._throttler
                )
            except requests.RequestException as exc:
                try:
                    from src.collector.__main__ import (
                        _categorize_request_error,
                    )

                    message = _categorize_request_error(exc)
                except ImportError:
                    message = f"{type(exc).__name__}: {exc}"
                print(f"[{source}] erro HTTP: {message}", file=sys.stderr)
                continue
            for doc in docs:
                url: str = doc["url"]
                if not validate_url(url, self._allowed_domains):
                    continue
                if self._storage.get_by_url(url) is not None:
                    continue
                record = DocumentRecord(
                    url=url,
                    source_domain=_extract_source_domain(url),
                    doc_type=doc.get("doc_type", source),
                    title=doc.get("title", url),
                    published_at=doc.get("published_at"),
                    status="nao_ingerido",
                )
                self._storage.upsert_document(record)
                inserted += 1
        return inserted

    def download_pending(self) -> int:
        """Baixa todos os documentos com ``status='nao_ingerido'``.

        Para cada documento pendente:
            1. ``throttler.wait()``.
            2. ``requests.get(url, timeout=60)``.
            3. ``sha256 = hashlib.sha256(content).hexdigest()``.
            4. Salva em ``data_dir/<sha256>.<ext>``.
            5. Atualiza ``file_path`` e ``content_hash`` no registro.

        Em caso de ``requests.RequestException`` (ou subclasse), o documento
        e marcado como ``status='falhou'`` via ``mark_failed`` e o loop segue.

        Returns:
            Numero de documentos baixados com sucesso.
        """
        downloaded: int = 0
        for record in self._storage.list_pending():
            try:
                self._throttler.wait()
                response = requests.get(
                    record.url, timeout=_DOWNLOAD_TIMEOUT_S
                )
                response.raise_for_status()
            except requests.RequestException:
                if record.id is not None:
                    self._storage.mark_failed(record.id)
                continue

            content: bytes = response.content
            content_hash: str = hashlib.sha256(content).hexdigest()
            extension: str = _extension_for(record.url)
            file_path: Path = self._data_dir / f"{content_hash}{extension}"
            file_path.write_bytes(content)

            update = DocumentRecord(
                id=record.id,
                url=record.url,
                source_domain=record.source_domain,
                doc_type=record.doc_type,
                title=record.title,
                file_path=file_path,
                content_hash=content_hash,
                published_at=record.published_at,
                fetched_at=record.fetched_at,
                status="nao_ingerido",
            )
            self._storage.upsert_document(update)
            downloaded += 1
        return downloaded
