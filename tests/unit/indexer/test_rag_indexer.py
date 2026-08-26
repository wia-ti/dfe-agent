"""Testes unitarios para src.indexer.rag_indexer.

Cobre (PLAN.md linhas 177-179 - Task 5.2):
    - [x] ingest_one em 1 doc registrado indexa >= 1 chunk; list_pending nao
          contem mais o id; vector_store.search retorna chunk com source_url correto.
    - [x] Segunda chamada de ingest_one no mesmo id retorna 0 e nao duplica chunks
          (contagem em vec_chunks antes/depois).
    - [x] Quando parser levanta PdfParseError, ingest_pending chama mark_failed
          e continua para o proximo documento.
    - [x] Quando outro documento ja tem o mesmo content_hash, ingest_one do novo
          e idempotente: marca como ingerido e nao duplica chunks.

Estrategia:
    - Storage e VectorStore reais (via tmp_path) - exercita SQL de verdade.
    - Embedder e um MagicMock - retorna 1 embedding fixo por chunk sem
      tocar no modelo sentence-transformers.
    - Parser e uma lambda controlada - evita dependenciar pypdf real nos testes.
"""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import sqlite_vec

from src.db.sqlite_storage import DocumentRecord, SqliteStorage
from src.db.vector_store import VectorStore
from src.indexer.rag_indexer import RagIndexer
from src.parser.exceptions import PdfParseError


# --- helpers ---


def _make_embedder(dim: int = 4, fill: float = 0.1) -> MagicMock:
    """Cria mock de EmbeddingProvider com dim configuravel.

    ``embed(texts)`` retorna uma embedding ``[fill]*dim`` para cada texto,
    de modo que o numero de embeddings devolvidas bate com o numero de chunks.
    """
    embedder = MagicMock()
    embedder.dim = dim
    embedder.embed.side_effect = (
        lambda texts: [[fill] * dim for _ in texts]
    )
    return embedder


def _count_vec_chunks(db_path: Path) -> int:
    """Conta linhas na tabela virtual vec_chunks carregando sqlite-vec."""
    conn = sqlite3.connect(db_path)
    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        cur = conn.execute("SELECT COUNT(*) FROM vec_chunks")
        return int(cur.fetchone()[0])
    finally:
        conn.close()


def _bootstrap(tmp_path: Path) -> tuple[SqliteStorage, VectorStore, Path]:
    """Inicializa schemas e retorna (storage, vector_store, db_path)."""
    db_path = tmp_path / "rag.db"
    storage = SqliteStorage(db_path)
    storage.init_schema()
    vector_store = VectorStore(db_path, dim=4)
    vector_store.init_schema()
    return storage, vector_store, db_path


# --- testes criticos (PLAN.md linhas 177-179) ---


def test_ingest_one_indexes_pending_document(tmp_path: Path) -> None:
    """1 doc registrado + arquivo 1500 chars: ingest_one retorna N>=1 chunks.

    Apos a execucao:
        - list_pending nao contem mais esse id.
        - vector_store.search retorna chunk com source_url == document.url.
    """
    storage, vector_store, db_path = _bootstrap(tmp_path)

    doc_file = tmp_path / "doc.txt"
    doc_file.write_text("a" * 1500)

    record = DocumentRecord(
        url="https://nfe.fazenda.gov.br/docs/nt-2019-001",
        source_domain="nfe.fazenda.gov.br",
        doc_type="nfe",
        title="NT 2019.001",
        file_path=doc_file,
        status="nao_ingerido",
    )
    doc_id = storage.upsert_document(record)

    embedder = _make_embedder()
    indexer = RagIndexer(
        storage, vector_store, embedder, parser=lambda p: p.read_text()
    )

    n_chunks = indexer.ingest_one(doc_id)

    assert n_chunks >= 1, f"esperava >=1 chunk, recebi {n_chunks}"
    pending_ids = {p.id for p in storage.list_pending()}
    assert doc_id not in pending_ids

    # Sprint 2 / Fase 12.1: o embedder e chamado para os chunks e tambem
    # para o summary deterministico. Total de chamadas >= 1.
    embedder.embed.assert_called()
    sample_embedding: list[float] = [0.1, 0.1, 0.1, 0.1]
    results = vector_store.search(sample_embedding, top_k=1)
    assert len(results) >= 1
    assert results[0].source_url == "https://nfe.fazenda.gov.br/docs/nt-2019-001"
    assert results[0].doc_title == "NT 2019.001"


def test_ingest_one_is_idempotent_on_second_call(tmp_path: Path) -> None:
    """Segunda chamada de ingest_one no mesmo id retorna 0 e nao duplica chunks."""
    storage, vector_store, db_path = _bootstrap(tmp_path)

    doc_file = tmp_path / "doc.txt"
    doc_file.write_text("b" * 1500)

    record = DocumentRecord(
        url="https://nfe.fazenda.gov.br/docs/nt-2020-001",
        source_domain="nfe.fazenda.gov.br",
        doc_type="nfe",
        title="NT 2020.001",
        file_path=doc_file,
        status="nao_ingerido",
    )
    doc_id = storage.upsert_document(record)

    embedder = _make_embedder()
    indexer = RagIndexer(
        storage, vector_store, embedder, parser=lambda p: p.read_text()
    )

    n1 = indexer.ingest_one(doc_id)
    assert n1 >= 1
    n_before: int = _count_vec_chunks(db_path)
    assert n_before >= 1

    n2 = indexer.ingest_one(doc_id)
    assert n2 == 0, f"segunda chamada devia retornar 0, retornou {n2}"

    n_after: int = _count_vec_chunks(db_path)
    assert n_after == n_before, (
        f"chunks duplicados: antes={n_before}, depois={n_after}"
    )


def test_ingest_pending_marks_failed_on_parser_error_and_continues(
    tmp_path: Path,
) -> None:
    """Parser levanta PdfParseError: mark_failed + continua para o proximo."""
    storage, vector_store, db_path = _bootstrap(tmp_path)

    doc1 = tmp_path / "doc1_erro.txt"
    doc1.write_text("qualquer texto")
    id1 = storage.upsert_document(
        DocumentRecord(
            url="https://nfe.fazenda.gov.br/docs/erro",
            source_domain="nfe.fazenda.gov.br",
            doc_type="nfe",
            title="Erro",
            file_path=doc1,
            status="nao_ingerido",
        )
    )

    doc2 = tmp_path / "doc2_ok.txt"
    doc2.write_text("texto normal sobre NF-e")
    id2 = storage.upsert_document(
        DocumentRecord(
            url="https://nfe.fazenda.gov.br/docs/ok",
            source_domain="nfe.fazenda.gov.br",
            doc_type="nfe",
            title="OK",
            file_path=doc2,
            status="nao_ingerido",
        )
    )

    def parser_selectivo(path: Path) -> str:
        if "erro" in path.name:
            raise PdfParseError("simulando falha do parser")
        return path.read_text()

    embedder = _make_embedder()
    indexer = RagIndexer(
        storage, vector_store, embedder, parser=parser_selectivo
    )

    n_indexed = indexer.ingest_pending()

    assert n_indexed == 1, f"somente doc2 devia ser indexado, recebi {n_indexed}"

    doc1_after = storage.get_by_url("https://nfe.fazenda.gov.br/docs/erro")
    assert doc1_after is not None
    assert doc1_after.status == "falhou"
    assert doc1_after.ingested_at is None

    doc2_after = storage.get_by_url("https://nfe.fazenda.gov.br/docs/ok")
    assert doc2_after is not None
    assert doc2_after.status == "ingerido"


# --- teste extra: idempotencia por hash de conteudo ---


def test_ingest_one_skips_when_other_document_has_same_hash(tmp_path: Path) -> None:
    """Se outro doc ja tem o mesmo content_hash, mark_ingested sem duplicar."""
    storage, vector_store, db_path = _bootstrap(tmp_path)

    doc1 = tmp_path / "doc1.txt"
    doc1.write_text("conteudo identico" * 100)
    id1 = storage.upsert_document(
        DocumentRecord(
            url="https://nfe.fazenda.gov.br/a",
            source_domain="nfe.fazenda.gov.br",
            doc_type="nfe",
            title="A",
            file_path=doc1,
        )
    )

    doc2 = tmp_path / "doc2.txt"
    doc2.write_text("conteudo identico" * 100)
    id2 = storage.upsert_document(
        DocumentRecord(
            url="https://nfe.fazenda.gov.br/b",
            source_domain="nfe.fazenda.gov.br",
            doc_type="nfe",
            title="B",
            file_path=doc2,
            status="nao_ingerido",
        )
    )

    embedder = _make_embedder()
    indexer = RagIndexer(
        storage, vector_store, embedder, parser=lambda p: p.read_text()
    )

    n1 = indexer.ingest_one(id1)
    assert n1 >= 1
    n_before = _count_vec_chunks(db_path)

    n2 = indexer.ingest_one(id2)
    assert n2 == 0

    n_after = _count_vec_chunks(db_path)
    assert n_after == n_before, "hash duplicado nao deveria inserir chunks"

    rec2 = storage.get_by_url("https://nfe.fazenda.gov.br/b")
    assert rec2 is not None
    assert rec2.status == "ingerido"


# --- testes de borda / robustez ---


def test_ingest_one_returns_zero_when_document_id_missing(tmp_path: Path) -> None:
    """Se document_id nao existe em list_pending, ingest_one retorna 0."""
    storage, vector_store, _ = _bootstrap(tmp_path)
    embedder = _make_embedder()
    indexer = RagIndexer(
        storage, vector_store, embedder, parser=lambda p: p.read_text()
    )

    assert indexer.ingest_one(99999) == 0


def test_ingest_one_returns_zero_when_only_other_docs_pending(
    tmp_path: Path,
) -> None:
    """Ha docs pendentes, mas com id diferente do solicitado: retorna 0.

    Cobre a branch False do ``_find_pending`` (loop itera sem match).
    """
    storage, vector_store, _ = _bootstrap(tmp_path)
    doc_file = tmp_path / "doc.txt"
    doc_file.write_text("texto qualquer")
    storage.upsert_document(
        DocumentRecord(
            url="https://nfe.fazenda.gov.br/outro",
            source_domain="nfe.fazenda.gov.br",
            doc_type="nfe",
            title="Outro",
            file_path=doc_file,
            status="nao_ingerido",
        )
    )

    embedder = _make_embedder()
    indexer = RagIndexer(
        storage, vector_store, embedder, parser=lambda p: p.read_text()
    )

    assert indexer.ingest_one(99999) == 0


def test_ingest_one_marks_failed_when_file_path_is_none(tmp_path: Path) -> None:
    """Record sem file_path: mark_failed (sem levantar)."""
    storage, vector_store, _ = _bootstrap(tmp_path)
    id_no_path = storage.upsert_document(
        DocumentRecord(
            url="https://nfe.fazenda.gov.br/sem-arquivo",
            source_domain="nfe.fazenda.gov.br",
            doc_type="nfe",
            title="Sem arquivo",
            file_path=None,
            status="nao_ingerido",
        )
    )

    embedder = _make_embedder()
    indexer = RagIndexer(
        storage, vector_store, embedder, parser=lambda p: p.read_text()
    )

    n = indexer.ingest_one(id_no_path)
    assert n == 0

    rec = storage.get_by_url("https://nfe.fazenda.gov.br/sem-arquivo")
    assert rec is not None
    assert rec.status == "falhou"


def test_ingest_one_marks_failed_when_chunker_returns_empty(tmp_path: Path) -> None:
    """Texto vazio produz chunks=[]: mark_failed (sem inserir nada)."""
    storage, vector_store, db_path = _bootstrap(tmp_path)
    doc_file = tmp_path / "empty.txt"
    doc_file.write_text("   \n\n   \t  ")
    doc_id = storage.upsert_document(
        DocumentRecord(
            url="https://nfe.fazenda.gov.br/vazio",
            source_domain="nfe.fazenda.gov.br",
            doc_type="nfe",
            title="Vazio",
            file_path=doc_file,
            status="nao_ingerido",
        )
    )

    embedder = _make_embedder()
    indexer = RagIndexer(
        storage, vector_store, embedder, parser=lambda p: p.read_text()
    )

    n = indexer.ingest_one(doc_id)
    assert n == 0
    assert _count_vec_chunks(db_path) == 0

    rec = storage.get_by_url("https://nfe.fazenda.gov.br/vazio")
    assert rec is not None
    assert rec.status == "falhou"


def test_ingest_one_marks_failed_on_unexpected_exception(tmp_path: Path) -> None:
    """Excecao nao-PdfParseError no parser: mark_failed sem abortar."""
    storage, vector_store, _ = _bootstrap(tmp_path)
    doc_file = tmp_path / "x.txt"
    doc_file.write_text("algo")
    doc_id = storage.upsert_document(
        DocumentRecord(
            url="https://nfe.fazenda.gov.br/x",
            source_domain="nfe.fazenda.gov.br",
            doc_type="nfe",
            title="X",
            file_path=doc_file,
            status="nao_ingerido",
        )
    )

    def parser_que_explode(path: Path) -> str:
        raise RuntimeError("boom generico")

    embedder = _make_embedder()
    indexer = RagIndexer(
        storage, vector_store, embedder, parser=parser_que_explode
    )

    n = indexer.ingest_one(doc_id)
    assert n == 0

    rec = storage.get_by_url("https://nfe.fazenda.gov.br/x")
    assert rec is not None
    assert rec.status == "falhou"


def test_ingest_pending_indexes_all_pending_when_no_failures(
    tmp_path: Path,
) -> None:
    """Sem falhas, ingest_pending indexa todos os pendentes."""
    storage, vector_store, _ = _bootstrap(tmp_path)

    for i in range(3):
        f = tmp_path / f"d{i}.txt"
        f.write_text(f"texto fiscal {i} - " * 80)
        storage.upsert_document(
            DocumentRecord(
                url=f"https://nfe.fazenda.gov.br/d{i}",
                source_domain="nfe.fazenda.gov.br",
                doc_type="nfe",
                title=f"D{i}",
                file_path=f,
                status="nao_ingerido",
            )
        )

    embedder = _make_embedder()
    indexer = RagIndexer(
        storage, vector_store, embedder, parser=lambda p: p.read_text()
    )

    n_indexed = indexer.ingest_pending()
    assert n_indexed == 3
    assert storage.list_pending() == []


def test_ingest_pending_no_pending_returns_zero(tmp_path: Path) -> None:
    """Sem documentos pendentes, ingest_pending retorna 0."""
    storage, vector_store, _ = _bootstrap(tmp_path)
    embedder = _make_embedder()
    indexer = RagIndexer(
        storage, vector_store, embedder, parser=lambda p: p.read_text()
    )
    assert indexer.ingest_pending() == 0
    embedder.embed.assert_not_called()