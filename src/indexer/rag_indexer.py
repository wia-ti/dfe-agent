"""RagIndexer: indexacao idempotente de documentos na base RAG local.

Responsabilidades:
    - Para cada ``DocumentRecord`` com ``status='nao_ingerido'``, executar o
      pipeline: ``parser -> chunk -> embed -> persist (vetorial + relacional)``.
    - Garantir idempotencia:
        * Por ``list_pending()``: docs ja ingeridos nao sao reprocessados.
        * Por ``content_hash``: dois docs com mesmo texto nao geram chunks duplicados.
    - Em qualquer excecao durante a ingestao de um doc, marca o registro como
      ``'falhou'`` e segue para o proximo sem abortar o lote.

Sprint 2:
    - Fase 9.2: extrai metadados estruturados (NT, data, versao) do
      cabecalho antes do chunking e persiste em ``documents``.
    - Fase 10.1: opcionalmente usa :mod:`src.indexer.structural_chunker`
      para preservar contexto de secao NT nos chunks.

Coexistencia com Task 5.1:
    ``chunk_text`` / ``chunk_structural`` sao importados de forma LAZY
    dentro de ``_ingest_record`` para nao falhar caso os modulos ainda
    nao estejam disponiveis (ambiente de build paralelo).
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable, Literal

from src.db.sqlite_storage import DocumentRecord, SqliteStorage
from src.db.vector_store import ChunkRecord, VectorStore
from src.utils.logger import get_logger


_logger = get_logger(__name__)

ChunkerMode = Literal["flat", "structural"]


class RagIndexer:
    """Indexador RAG: orquestra parser + chunker + embedder + persistencia.

    Args:
        storage: DAO relacional (documentos + controle de ingestao).
        vector_store: DAO vetorial (chunks + embeddings + sidecar metadata).
        embedder: qualquer objeto com metodo ``embed(list[str]) -> list[list[float]]``.
        parser: funcao que recebe ``Path`` do arquivo local e devolve texto.
        chunker_mode:
            ``"flat"`` (default) usa :func:`src.indexer.chunker.chunk_text`
            — comportamento pre-Sprint-2.
            ``"structural"`` usa :func:`src.indexer.structural_chunker.chunk_structural`
            para preservar contexto de secao NT (Fase 10.1).
    """

    def __init__(
        self,
        storage: SqliteStorage,
        vector_store: VectorStore,
        embedder: object,
        parser: Callable[[Path], str],
        chunker_mode: ChunkerMode = "flat",
    ) -> None:
        if chunker_mode not in ("flat", "structural"):
            raise ValueError(
                f"chunker_mode invalido: {chunker_mode!r} "
                "(esperado 'flat' ou 'structural')"
            )
        self._storage: SqliteStorage = storage
        self._vector_store: VectorStore = vector_store
        self._embedder: object = embedder
        self._parser: Callable[[Path], str] = parser
        self._chunker_mode: ChunkerMode = chunker_mode

    def ingest_pending(self) -> int:
        """Processa todos os documentos com ``status='nao_ingerido'``.

        Returns:
            Numero de documentos indexados com sucesso (chunks > 0).
        """
        indexed: int = 0
        for record in self._storage.list_pending():
            if self._ingest_record(record) > 0:
                indexed += 1
        return indexed

    def ingest_one(self, document_id: int) -> int:
        """Processa apenas o documento com ``id=document_id``.

        Returns:
            Numero de chunks indexados (0 se o doc nao esta pendente,
            ja foi indexado, ou falhou).
        """
        record: DocumentRecord | None = self._find_pending(document_id)
        if record is None:
            return 0
        return self._ingest_record(record)

    def _find_pending(self, document_id: int) -> DocumentRecord | None:
        """Busca o doc entre os pendentes; ``None`` se ausente/ja ingerido."""
        for record in self._storage.list_pending():
            if record.id == document_id:
                return record
        return None

    def _ingest_record(self, record: DocumentRecord) -> int:
        """Executa o pipeline de ingestao para um unico ``record``.

        Retorna o numero de chunks inseridos (0 em qualquer falha). Em
        excecao durante o pipeline, o registro e marcado como ``'falhou'``.

        Lazy import:
            ``chunk_text`` vem de ``src.indexer.chunker`` (Task 5.1) e e
            importado aqui dentro para conviver com build paralelo.
            ``extract_document_metadata`` vem de ``src.parser.metadata_extractor``
            (Sprint 2, Fase 9.2) e segue a mesma convenção.

        Sprint 2 / Fase 9.2:
            Apos extrair o texto e antes de prosseguir, identificamos
            metadados estruturados (``nt_number``, ``version``,
            ``published_at``, ``language``) e persistimos via
            ``upsert_document`` para que fiquem disponiveis mesmo em
            caso de falha de embedding.
        """
        from src.indexer.chunker import chunk_text
        from src.parser.metadata_extractor import extract_document_metadata

        doc_id: int = int(record.id)  # type: ignore[arg-type]

        if record.file_path is None:
            self._storage.mark_failed(doc_id)
            return 0

        try:
            text: str = self._parser(record.file_path) or ""
        except Exception as exc:
            _logger.warning("rag_indexer parser falhou para doc_id=%s: %s", doc_id, exc)
            self._storage.mark_failed(doc_id)
            return 0

        # Fase 9.2: enriquecimento de metadados estruturados (best effort).
        # Persistimos via upsert_document antes do final do pipeline para
        # que metadados ja estejam em DB se a fase de embedding falhar.
        try:
            metadata = extract_document_metadata(text, doc_type=record.doc_type)
        except Exception as exc:  # noqa: BLE001 — defensivo, nunca deve derrubar ingestao
            _logger.warning("rag_indexer extract_document_metadata falhou: %s", exc)
            metadata = None

        if metadata is not None:
            if record.nt_number is None and metadata.nt_number is not None:
                record.nt_number = metadata.nt_number
            if record.version is None and metadata.version is not None:
                record.version = metadata.version
            if record.published_at is None and metadata.published_at is not None:
                record.published_at = metadata.published_at
            if record.language is None:
                record.language = metadata.language or "pt-BR"
            try:
                self._storage.upsert_document(record)
            except Exception as exc:  # noqa: BLE001 — defensivo
                _logger.warning("rag_indexer upsert_document falhou: %s", exc)
                pass

        text_hash: str = hashlib.sha256(text.encode("utf-8")).hexdigest()
        existing: DocumentRecord | None = self._storage.get_by_hash(text_hash)
        if existing is not None and existing.id != doc_id:
            self._storage.mark_ingested(doc_id)
            return 0

        # Sprint 2 / Fase 10.1: chunker estrutural preserva contexto de
        # secao NT. Em modo flat (default) delega a chunk_text direto.
        if self._chunker_mode == "structural":
            from src.indexer.structural_chunker import chunk_structural

            structured = chunk_structural(text)
            chunk_texts: list[str] = [c.text for c in structured]
            chunk_sections: list[tuple[str, int]] = [
                (c.section_path, c.section_level) for c in structured
            ]
        else:
            chunk_texts = chunk_text(text)
            chunk_sections = [("", 0)] * len(chunk_texts)

        if not chunk_texts:
            self._storage.mark_failed(doc_id)
            return 0

        embeddings: list[list[float]] = self._embedder.embed(chunk_texts)
        chunk_records: list[ChunkRecord] = [
            ChunkRecord(
                document_id=doc_id,
                chunk_index=i,
                text=chunk,
                embedding=embeddings[i],
                source_url=record.url,
                doc_title=record.title,
                section_path=chunk_sections[i][0],
                section_level=chunk_sections[i][1],
            )
            for i, chunk in enumerate(chunk_texts)
        ]
        # Aplica defaults de kind/parent (Fase 14): defaults mantidos para
        # retrocompatibilidade — todos os chunks gerados pelos chunkers
        # flat/structural sao ``detail`` sem parent.
        self._vector_store.insert_chunks(chunk_records)

        # Sprint 2 / Fase 12.1: sumario deterministico para o two-stage
        # retrieval de QueryEngine.search_hierarchical. Embedamos o
        # sumario separadamente (nao derivado dos chunks — sinal mais
        # denso por ser uma amostra do texto inteiro).
        try:
            self._persist_summary(doc_id, text)
        except Exception as exc:  # noqa: BLE001 — defensivo, nao derruba o ingest
            _logger.warning("rag_indexer _persist_summary falhou: %s", exc)
            pass

        record.content_hash = text_hash
        record.status = "ingerido"
        self._storage.upsert_document(record)
        self._storage.mark_ingested(doc_id)
        return len(chunk_texts)

    def _persist_summary(self, document_id: int, text: str) -> None:
        """Gera, embeda e persiste o sumario deterministico do documento.

        Etapas:
            1. ``summarize(text, max_chars=400)``: extracao sem LLM.
            2. ``embedder.embed([summary])``: vetor do resumo.
            3. ``DocSummaryStore.upsert_summary``: ``INSERT OR REPLACE``
               (idempotente por document_id).

        Fica en-capsulado num metodo privado apenas para manter
        ``_ingest_record`` legivel; tambem facilita mock nos testes.
        """
        if not text or not text.strip():
            return
        from src.db.doc_summaries import DocSummaryStore
        from src.indexer.summarizer import summarize

        summary: str = summarize(text)
        if not summary:
            return

        embedding_vec: list[list[float]] = self._embedder.embed([summary])
        store = DocSummaryStore(self._vector_store.db_path, dim=len(embedding_vec[0]))
        store.upsert_summary(
            document_id=document_id,
            summary=summary,
            embedding=embedding_vec[0],
        )


__all__ = ["ChunkerMode", "RagIndexer"]