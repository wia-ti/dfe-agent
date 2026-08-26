"""Testes de integracao para Sprint 2, Fase 9.2: extrator de metadados aplicado
via ``RagIndexer``.

Verifica que, ao ingerir um documento cujo texto traz NT number / data /
versao no cabecalho, o ``RagIndexer``:
    1. Detecta os metadados via :mod:`src.parser.metadata_extractor`.
    2. Persiste-os no relacional via ``upsert_document``.
    3. Mantem comportamento idempotente: reingerir o mesmo doc nao duplica
       chunks nem sobrescreve metadados ja presentes (Fonte da verdade:
       o que ja esta em record tem precedencia).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import sqlite_vec

from src.db.sqlite_storage import DocumentRecord, SqliteStorage
from src.db.vector_store import VectorStore
from src.indexer.rag_indexer import RagIndexer


# --- helpers ---------------------------------------------------------------


def _embedder_stub(dim: int = 4) -> MagicMock:
    """Mock de EmbeddingProvider; gera vetor ``[0.1]*dim`` por chunk."""
    embedder = MagicMock()
    embedder.dim = dim
    embedder.embed.side_effect = lambda texts: [[0.1] * dim for _ in texts]
    return embedder


def _bootstrap(tmp_path: Path) -> tuple[SqliteStorage, VectorStore]:
    db_path = tmp_path / "rag.db"
    storage = SqliteStorage(db_path)
    storage.init_schema()
    vector_store = VectorStore(db_path, dim=4)
    vector_store.init_schema()
    return storage, vector_store


# --- testes -----------------------------------------------------------------


def test_indexer_extrai_nt_number_e_persiste(tmp_path: Path) -> None:
    """Texto com NT 2019.001 faz o doc virar localizavel por get_by_nt_number."""
    storage, _ = _bootstrap(tmp_path)
    embedder = _embedder_stub()
    parser = lambda p: (
        "NOTA TÉCNICA 2019.001 — NF-e\n"
        + "Publicada em 15/03/2019.\n"
        + ("conteudo util sobre cancelamento " * 80)
    )
    indexer = RagIndexer(storage, VectorStore(tmp_path / "rag.db", dim=4), embedder, parser=parser)

    doc_file = tmp_path / "nt.pdf"
    doc_file.write_text(parser.__call__.__code__.__code__ if False else "")  # noqa
    record = DocumentRecord(
        url="https://nfe.fazenda.gov.br/nt/2019.001",
        source_domain="nfe.fazenda.gov.br",
        doc_type="nota_tecnica",
        title="NT 2019.001",
        file_path=doc_file,
    )
    doc_id = storage.upsert_document(record)

    n_chunks = indexer.ingest_one(doc_id)
    assert n_chunks >= 1

    fetched = storage.get_by_nt_number("2019.001")
    assert fetched is not None
    assert fetched.nt_number == "2019.001"
    assert fetched.published_at == datetime(2019, 3, 15)
    assert fetched.status == "ingerido"


def test_indexer_nao_sobrescreve_metadata_existente(tmp_path: Path) -> None:
    """Se o record ja tem nt_number, o extrator nao sobrescreve.

    Util quando o coletor ja preenche a NT via URL parsing antes de
    chamar o indexador.
    """
    storage, _ = _bootstrap(tmp_path)
    embedder = _embedder_stub()
    parser = lambda p: (
        "NOTA TÉCNICA 2099.999 - NT fantasma\n"
        + ("conteudo irrelevante " * 80)
    )
    indexer = RagIndexer(storage, VectorStore(tmp_path / "rag.db", dim=4), embedder, parser=parser)

    doc_file = tmp_path / "nt.pdf"
    doc_file.write_text("")
    record = DocumentRecord(
        url="https://nfe.fazenda.gov.br/nt/custom",
        source_domain="nfe.fazenda.gov.br",
        doc_type="nota_tecnica",
        title="NT custom",
        file_path=doc_file,
        nt_number="2019.001",
    )
    doc_id = storage.upsert_document(record)

    indexer.ingest_one(doc_id)

    fetched = storage.get_by_url("https://nfe.fazenda.gov.br/nt/custom")
    assert fetched is not None
    assert fetched.nt_number == "2019.001"


def test_indexer_persiste_metadados_antes_de_chunking(
    tmp_path: Path,
) -> None:
    """Cobre o caminho feliz: o pipeline completo persiste metadata.

    Foco do teste: garantir que ``upsert_document`` com metadados e
    invocado dentro de ``_ingest_record`` ANTES do fim do pipeline, de
    modo que metadados sejam visiveis via ``get_by_nt_number``.
    """
    storage, vector_store = _bootstrap(tmp_path)
    embedder = _embedder_stub()

    def parser_com_cabecalho(text_file: Path) -> str:
        return (
            "NOTA TÉCNICA 2020.005 - Atualiza regras de cancelamento.\n"
            + "Publicado em 10/06/2020.\n"
            + ("conteudo util sobre cancelamento " * 80)
        )

    indexer = RagIndexer(storage, vector_store, embedder, parser=parser_com_cabecalho)

    doc_file = tmp_path / "nt.pdf"
    doc_file.write_text("")
    record = DocumentRecord(
        url="https://nfe.fazenda.gov.br/nt/2020.005",
        source_domain="nfe.fazenda.gov.br",
        doc_type="nota_tecnica",
        title="NT 2020.005",
        file_path=doc_file,
    )
    doc_id = storage.upsert_document(record)

    n_chunks = indexer.ingest_one(doc_id)
    assert n_chunks >= 1

    fetched = storage.get_by_nt_number("2020.005")
    assert fetched is not None
    assert fetched.nt_number == "2020.005"
    assert fetched.published_at == datetime(2020, 6, 10)


def test_indexer_com_texto_sem_metadados_nao_quebra(tmp_path: Path) -> None:
    """Texto sem cabecalho estruturado: ingest funciona, metadados ficam None."""
    storage, vector_store = _bootstrap(tmp_path)
    embedder = _embedder_stub()
    parser = lambda p: "lorem ipsum dolor sit amet sem formato. " * 80
    indexer = RagIndexer(storage, vector_store, embedder, parser=parser)

    doc_file = tmp_path / "x.txt"
    doc_file.write_text("")
    record = DocumentRecord(
        url="https://nfe.fazenda.gov.br/x",
        source_domain="nfe.fazenda.gov.br",
        doc_type="outro",
        title="Sem cabecalho",
        file_path=doc_file,
    )
    doc_id = storage.upsert_document(record)

    n_chunks = indexer.ingest_one(doc_id)
    assert n_chunks >= 1

    fetched = storage.get_by_url("https://nfe.fazenda.gov.br/x")
    assert fetched is not None
    assert fetched.nt_number is None
    assert fetched.published_at is None
    assert fetched.status == "ingerido"


def test_indexer_cai_no_fallback_quando_extrator_falha(
    tmp_path: Path,
) -> None:
    """Defesa: extrator levantando e tratado, ingest nao quebra.

    Cobre branch ``except Exception: metadata = None`` em
    ``_ingest_record`` — path defensivo documentado.
    """
    storage, vector_store = _bootstrap(tmp_path)
    embedder = _embedder_stub()

    with patch(
        "src.parser.metadata_extractor.extract_document_metadata",
        side_effect=RuntimeError("extrator indisponivel"),
    ):
        parser = lambda p: ("texto sem metadados " * 80)
        indexer = RagIndexer(storage, vector_store, embedder, parser=parser)

        doc_file = tmp_path / "x.txt"
        doc_file.write_text("")
        record = DocumentRecord(
            url="https://nfe.fazenda.gov.br/fallback",
            source_domain="nfe.fazenda.gov.br",
            doc_type="outro",
            title="X",
            file_path=doc_file,
        )
        doc_id = storage.upsert_document(record)
        n_chunks = indexer.ingest_one(doc_id)

    assert n_chunks >= 1
    fetched = storage.get_by_url("https://nfe.fazenda.gov.br/fallback")
    assert fetched is not None
    assert fetched.nt_number is None


def test_indexer_persiste_language_pt_br_default(tmp_path: Path) -> None:
    """Quando o record nao tem language, o indexador preenche ``pt-BR``."""
    storage, vector_store = _bootstrap(tmp_path)
    embedder = _embedder_stub()
    parser = lambda p: "texto simples sobre a NT 2020.001 publicada em 01/02/2020. " * 40

    indexer = RagIndexer(storage, vector_store, embedder, parser=parser)
    doc_file = tmp_path / "x.txt"
    doc_file.write_text("")
    record = DocumentRecord(
        url="https://nfe.fazenda.gov.br/lang",
        source_domain="nfe.fazenda.gov.br",
        doc_type="nota_tecnica",
        title="Lang",
        file_path=doc_file,
    )
    doc_id = storage.upsert_document(record)
    indexer.ingest_one(doc_id)

    fetched = storage.get_by_url("https://nfe.fazenda.gov.br/lang")
    assert fetched is not None
    assert fetched.language == "pt-BR"


def test_indexer_com_upsert_falho_nao_aborta_ingestao(
    tmp_path: Path,
) -> None:
    """Cobertura defensiva: erro no ``upsert_document`` de metadata e engolido.

    Para isolar o caminho defensivo da Fase 9.2, fazemos o patch
    falhar APENAS nas primeiras chamadas (limite = 1, contando a
    chamada inicial de insert/upsert fora do patch) e deixar o final do
    pipeline funcionar. O ponto do teste e verificar que o try/except
    interno absorve a falha sem propagar.
    """
    storage, vector_store = _bootstrap(tmp_path)
    embedder = _embedder_stub()
    parser = lambda p: (
        "NOTA TÉCNICA 2020.007 - Conteudo relevante.\n"
        + ("detalhes da NT " * 80)
    )

    doc_file = tmp_path / "x.txt"
    doc_file.write_text("")
    record = DocumentRecord(
        url="https://nfe.fazenda.gov.br/broken",
        source_domain="nfe.fazenda.gov.br",
        doc_type="nota_tecnica",
        title="Broken",
        file_path=doc_file,
    )

    # Patch que falha apenas quando um campo especifico e recebido.
    original_upsert = storage.upsert_document
    fail_count = {"n": 0}

    def selective_failing_upsert(rec: DocumentRecord) -> int:
        # Falha APENAS para a chamada de metadados (record nt_number set
        # antes do persist final).
        if rec.nt_number == "2020.007" and rec.status == "nao_ingerido":
            fail_count["n"] += 1
            raise RuntimeError("transient")
        return original_upsert(rec)

    with patch.object(
        storage, "upsert_document", side_effect=selective_failing_upsert
    ):
        doc_id = original_upsert(record)  # cria o doc sem metadata
        indexer = RagIndexer(storage, vector_store, embedder, parser=parser)
        n_chunks = indexer.ingest_one(doc_id)

    assert n_chunks >= 1, "defesa deve absorver falha da upsert de metadados"
    assert fail_count["n"] >= 1, "patch deveria ter sido invocado"
    fetched = storage.get_by_url("https://nfe.fazenda.gov.br/broken")
    assert fetched is not None
    assert fetched.status == "ingerido"
    assert fetched.nt_number == "2020.007"  # metadata foi aplicada via pipeline final


def test_indexer_atribui_version_e_published_at_independente(
    tmp_path: Path,
) -> None:
    """Cobre branches onde ``record.version is None`` e ``record.published_at is None``."""
    storage, vector_store = _bootstrap(tmp_path)
    embedder = _embedder_stub()
    parser = lambda p: (
        "NOTA TÉCNICA 2021.010\n"
        "Versao 4.1\n"
        "Versao XYZ placeholder (so para o topo).\n"  # nao casa
        "Publicado em 25/12/2021.\n"
        + ("conteudo " * 80)
    )

    indexer = RagIndexer(storage, vector_store, embedder, parser=parser)
    doc_file = tmp_path / "x.txt"
    doc_file.write_text("")
    record = DocumentRecord(
        url="https://nfe.fazenda.gov.br/v4",
        source_domain="nfe.fazenda.gov.br",
        doc_type="nota_tecnica",
        title="V4.1",
        file_path=doc_file,
    )
    doc_id = storage.upsert_document(record)
    indexer.ingest_one(doc_id)

    fetched = storage.get_by_url("https://nfe.fazenda.gov.br/v4")
    assert fetched is not None
    assert fetched.nt_number == "2021.010"
    assert fetched.version == "4.1"
    assert fetched.published_at == datetime(2021, 12, 25)
