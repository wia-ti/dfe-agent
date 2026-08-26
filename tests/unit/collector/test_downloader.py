"""Testes unitarios de src.collector.downloader (DocumentCollector).

Cobre (PLAN.md linhas 108-110):
    - discover_and_register insere DocumentRecord com status="nao_ingerido"
      para URLs novas, idempotente (segunda chamada nao duplica).
    - download_pending chama throttler.wait() uma vez por documento, antes do GET.
    - Quando requests.get levanta ConnectionError, mark_failed e chamado e o
      loop continua para os proximos documentos.

Tambem cobre:
    - download_pending salva arquivo com sha256 no nome.
    - download_pending atualiza file_path e content_hash no storage.
    - download_pending aceita extensoes .pdf/.html/.htm (case-insensitive).
    - DocumentCollector.__init__ cria data_dir se nao existir.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.collector import downloader
from src.collector.downloader import DocumentCollector
from src.db.sqlite_storage import DocumentRecord


def _make_response(content: bytes = b"%PDF-1.4 fake body") -> MagicMock:
    response = MagicMock()
    response.content = content
    response.raise_for_status = lambda: None
    return response


def _patch_validate(mocker, return_value: bool = True) -> None:
    mocker.patch.object(downloader, "validate_url", return_value=return_value)


def _patch_discover(mocker, docs: list[dict] | None = None) -> None:
    """Mocka discover_documents em todos os sources para retornar `docs`."""
    if docs is None:
        docs = []
    mocker.patch.object(downloader, "discover_documents", return_value=docs)


def test_discover_and_register_inserts_new_documents_with_nao_ingerido(
    mocker, fake_storage, fake_throttler, fake_data_dir
) -> None:
    docs = [
        {"url": f"https://www.nfe.fazenda.gov.br/docs/nt_{i}.pdf",
         "title": f"NT {i}", "doc_type": "nfe", "published_at": None}
        for i in range(5)
    ]
    _patch_discover(mocker, docs)
    _patch_validate(mocker, True)

    collector = DocumentCollector(fake_storage, fake_throttler, fake_data_dir)
    inserted = collector.discover_and_register()

    assert inserted == 5
    for d in docs:
        rec = fake_storage.get_by_url(d["url"])
        assert rec is not None, f"Registro ausente para {d['url']}"
        assert rec.status == "nao_ingerido"
        assert rec.doc_type == "nfe"
        assert rec.source_domain == "nfe.fazenda.gov.br"


def test_discover_and_register_is_idempotent(
    mocker, fake_storage, fake_throttler, fake_data_dir
) -> None:
    docs = [
        {"url": "https://www.nfe.fazenda.gov.br/a.pdf",
         "title": "A", "doc_type": "nfe", "published_at": None}
    ]
    _patch_discover(mocker, docs)
    _patch_validate(mocker, True)

    collector = DocumentCollector(fake_storage, fake_throttler, fake_data_dir)

    first = collector.discover_and_register()
    second = collector.discover_and_register()

    assert first == 1
    assert second == 0

    rec = fake_storage.get_by_url(docs[0]["url"])
    assert rec is not None
    assert rec.status == "nao_ingerido"


def test_discover_and_register_skips_urls_rejected_by_validate(
    mocker, fake_storage, fake_throttler, fake_data_dir
) -> None:
    docs = [
        {"url": "https://www.nfe.fazenda.gov.br/ok.pdf",
         "title": "OK", "doc_type": "nfe", "published_at": None},
        {"url": "https://evil.com/bad.pdf",
         "title": "bad", "doc_type": "nfe", "published_at": None},
    ]
    _patch_discover(mocker, docs)

    def fake_validate(url: str, allowed_domains: list[str] | None = None) -> bool:
        return "nfe.fazenda.gov.br" in url

    mocker.patch.object(downloader, "validate_url", side_effect=fake_validate)

    collector = DocumentCollector(fake_storage, fake_throttler, fake_data_dir)
    inserted = collector.discover_and_register()

    assert inserted == 1
    assert fake_storage.get_by_url(docs[0]["url"]) is not None
    assert fake_storage.get_by_url(docs[1]["url"]) is None


def test_download_pending_calls_throttler_before_each_get(
    mocker, fake_storage, fake_throttler, fake_data_dir
) -> None:
    for i in range(3):
        fake_storage.upsert_document(
            DocumentRecord(
                url=f"https://www.nfe.fazenda.gov.br/docs/doc_{i}.pdf",
                source_domain="www.nfe.fazenda.gov.br",
                doc_type="nota_tecnica",
                title=f"doc {i}",
            )
        )

    mock_get = mocker.patch.object(
        downloader.requests, "get", return_value=_make_response(b"body-%PDF")
    )
    wait_spy = mocker.spy(fake_throttler, "wait")

    collector = DocumentCollector(fake_storage, fake_throttler, fake_data_dir)
    downloaded = collector.download_pending()

    assert downloaded == 3
    assert wait_spy.call_count == 3
    assert mock_get.call_count == 3


def test_download_pending_marks_failed_on_connection_error_and_continues(
    mocker, fake_storage, fake_throttler, fake_data_dir
) -> None:
    """requests.get levanta ConnectionError no 2o de 3 documentos.

    Esperado:
        - O documento 2 e marcado status='falhou' via mark_failed.
        - O documento 3 ainda e processado.
        - O retorno == 2 (quantos foram baixados com sucesso).
    """
    a_id = fake_storage.upsert_document(
        DocumentRecord(
            url="https://www.nfe.fazenda.gov.br/a.pdf",
            source_domain="www.nfe.fazenda.gov.br",
            doc_type="nota_tecnica",
            title="A",
        )
    )
    b_id = fake_storage.upsert_document(
        DocumentRecord(
            url="https://www.nfe.fazenda.gov.br/b.pdf",
            source_domain="www.nfe.fazenda.gov.br",
            doc_type="nota_tecnica",
            title="B",
        )
    )
    c_id = fake_storage.upsert_document(
        DocumentRecord(
            url="https://www.nfe.fazenda.gov.br/c.pdf",
            source_domain="www.nfe.fazenda.gov.br",
            doc_type="nota_tecnica",
            title="C",
        )
    )

    responses = [
        _make_response(b"pdf-A"),
        _make_response(b"pdf-B-fail"),
        _make_response(b"pdf-C"),
    ]

    def fake_get(url: str, timeout: int = 30, **kwargs) -> MagicMock:
        if "b.pdf" in url:
            raise downloader.requests.RequestException("boom")
        if "a.pdf" in url:
            return responses[0]
        if "c.pdf" in url:
            return responses[2]
        raise AssertionError(f"unexpected URL {url}")

    mocker.patch.object(downloader.requests, "get", side_effect=fake_get)
    mark_failed_spy = mocker.spy(fake_storage, "mark_failed")

    collector = DocumentCollector(fake_storage, fake_throttler, fake_data_dir)
    downloaded = collector.download_pending()

    assert downloaded == 2
    assert mark_failed_spy.call_count == 1
    mark_failed_spy.assert_called_once_with(b_id)

    # Apos download_pending, documentos baixados com sucesso permanecem
    # como 'nao_ingerido' — quem muda para 'ingerido' e o RagIndexer
    # (Fase 5). O downloader so atualiza file_path e content_hash.
    assert fake_storage.get_by_url(
        "https://www.nfe.fazenda.gov.br/a.pdf"
    ).status == "nao_ingerido"
    assert fake_storage.get_by_url(
        "https://www.nfe.fazenda.gov.br/b.pdf"
    ).status == "falhou"
    assert fake_storage.get_by_url(
        "https://www.nfe.fazenda.gov.br/c.pdf"
    ).status == "nao_ingerido"


def test_download_pending_saves_file_with_sha256_filename(
    mocker, fake_storage, fake_throttler, fake_data_dir
) -> None:
    body = b"%PDF-1.4 conteudo de teste"
    expected_hash = hashlib.sha256(body).hexdigest()
    fake_storage.upsert_document(
        DocumentRecord(
            url="https://www.nfe.fazenda.gov.br/docs/sample.pdf",
            source_domain="www.nfe.fazenda.gov.br",
            doc_type="nota_tecnica",
            title="sample",
        )
    )
    mocker.patch.object(
        downloader.requests, "get", return_value=_make_response(body)
    )

    collector = DocumentCollector(fake_storage, fake_throttler, fake_data_dir)
    collector.download_pending()

    rec = fake_storage.get_by_url("https://www.nfe.fazenda.gov.br/docs/sample.pdf")
    assert rec is not None
    assert rec.content_hash == expected_hash
    assert rec.file_path is not None
    assert rec.file_path.exists()
    assert rec.file_path.name == f"{expected_hash}.pdf"
    assert rec.file_path.read_bytes() == body


def test_download_pending_handles_html_and_htm_extensions(
    mocker, fake_storage, fake_throttler, fake_data_dir
) -> None:
    cases = [
        ("https://www.nfe.fazenda.gov.br/docs/nota.html", b"<html>a</html>", "html"),
        ("https://www.nfe.fazenda.gov.br/docs/nota.htm", b"<html>b</html>", "htm"),
        ("https://www.nfe.fazenda.gov.br/docs/NOTAS.PDF", b"%PDF c", "pdf"),
    ]
    for url, _, _ in cases:
        fake_storage.upsert_document(
            DocumentRecord(
                url=url,
                source_domain="www.nfe.fazenda.gov.br",
                doc_type="nota_tecnica",
                title=url.rsplit("/", 1)[-1],
            )
        )

    responses_by_url = {url: _make_response(body) for url, body, _ in cases}

    def fake_get(url: str, timeout: int = 30, **kwargs) -> MagicMock:
        return responses_by_url[url]

    mocker.patch.object(downloader.requests, "get", side_effect=fake_get)

    collector = DocumentCollector(fake_storage, fake_throttler, fake_data_dir)
    downloaded = collector.download_pending()

    assert downloaded == 3
    for url, _, _ in cases:
        rec = fake_storage.get_by_url(url)
        assert rec is not None
        assert rec.file_path is not None
        assert rec.file_path.exists()
        assert rec.file_path.suffix.lower() in {".pdf", ".html", ".htm"}


def test_download_pending_returns_zero_when_no_pending(
    mocker, fake_storage, fake_throttler, fake_data_dir
) -> None:
    mock_get = mocker.patch.object(downloader.requests, "get")

    collector = DocumentCollector(fake_storage, fake_throttler, fake_data_dir)
    downloaded = collector.download_pending()

    assert downloaded == 0
    mock_get.assert_not_called()


def test_constructor_creates_data_dir_if_missing(tmp_path: Path) -> None:
    """__init__ deve criar data_dir (parents=True, exist_ok=True)."""
    from src.db.sqlite_storage import SqliteStorage
    from src.utils.throttler import Throttler

    nested = tmp_path / "a" / "b" / "c" / "data"
    assert not nested.exists()

    DocumentCollector(
        SqliteStorage(tmp_path / "s.db"),
        Throttler(request_interval_ms=0, jitter_ms=0),
        nested,
    )

    assert nested.is_dir()


def test_download_pending_marks_ingested_only_when_pending_already(
    mocker, fake_storage, fake_throttler, fake_data_dir
) -> None:
    """Documentos ja ingeridos nao sao baixados novamente."""
    rec = DocumentRecord(
        url="https://www.nfe.fazenda.gov.br/x.pdf",
        source_domain="www.nfe.fazenda.gov.br",
        doc_type="nota_tecnica",
        title="X",
    )
    new_id = fake_storage.upsert_document(rec)
    fake_storage.mark_ingested(new_id)

    mock_get = mocker.patch.object(downloader.requests, "get")

    collector = DocumentCollector(fake_storage, fake_throttler, fake_data_dir)
    downloaded = collector.download_pending()

    assert downloaded == 0
    mock_get.assert_not_called()


def test_extension_for_returns_bin_for_unknown_extension() -> None:
    """URLs sem extensao reconhecida caem em '.bin' (fallback de seguranca)."""
    from src.collector.downloader import _extension_for

    assert _extension_for("https://example.com/file") == ".bin"
    assert _extension_for("https://example.com/file.PDF") == ".pdf"
    assert _extension_for("https://example.com/x.htm") == ".htm"


def test_extract_source_domain_strips_www() -> None:
    from src.collector.downloader import _extract_source_domain

    assert _extract_source_domain("https://www.nfe.fazenda.gov.br/x") == "nfe.fazenda.gov.br"
    assert _extract_source_domain("https://nfe.fazenda.gov.br/x") == "nfe.fazenda.gov.br"
    assert _extract_source_domain("not-a-url") == ""


def test_extract_source_domain_returns_empty_on_invalid_ipv6() -> None:
    """urlparse levanta ValueError para IPv6 malformado; cobrimos o branch defensivo."""
    from src.collector.downloader import _extract_source_domain

    assert _extract_source_domain("http://[invalid_ipv6") == ""


def test_download_pending_skips_mark_failed_when_record_has_no_id(
    mocker, fake_storage, fake_throttler, fake_data_dir
) -> None:
    """Se record.id e None (caso degenerado), mark_failed NAO e chamado."""
    collector = DocumentCollector(fake_storage, fake_throttler, fake_data_dir)

    synthetic = DocumentRecord(
        id=None,
        url="https://www.nfe.fazenda.gov.br/zzz.pdf",
        source_domain="www.nfe.fazenda.gov.br",
        doc_type="nota_tecnica",
        title="ZZZ",
    )
    mocker.patch.object(
        downloader.requests, "get",
        side_effect=downloader.requests.RequestException("boom"),
    )
    mocker.patch.object(fake_storage, "list_pending", return_value=[synthetic])
    mark_failed_spy = mocker.patch.object(fake_storage, "mark_failed")

    downloaded = collector.download_pending()

    assert downloaded == 0
    mark_failed_spy.assert_not_called()


def test_discover_and_register_continues_after_source_failure(
    mocker, fake_storage, fake_throttler, fake_data_dir, capsys
) -> None:
    """Quando discover_documents levanta RequestException para um source,
    o loop deve isolar a falha e continuar varrendo os sources seguintes.

    Cenario:
        - 'nfe' retorna 2 docs (sucesso).
        - 'nfce' levanta ConnectionError (timeout/DNS/5xx).
        - 'cte' retorna 1 doc (sucesso).
        - demais sources retornam [].

    Esperado:
        - discover_and_register retorna 3 (apenas docs dos sources que
          succeed).
        - Os docs de 'nfe' e 'cte' estao no storage; nenhum de 'nfce' foi
          inserido (porque nao retornou nada).
        - O erro e logado em stderr com o pattern '[<source>] erro HTTP: ...'.
        - discover_documents foi chamado para TODOS os sources (nenhum
          source foi pulado por causa da falha do 'nfce').
    """
    from src.collector.portal_index import PORTAL_URLS

    def fake_discover(source: str, throttler, http_session=None) -> list[dict]:
        if source == "nfe":
            return [
                {"url": "https://www.nfe.fazenda.gov.br/a.pdf",
                 "title": "A", "doc_type": "nfe", "published_at": None},
                {"url": "https://www.nfe.fazenda.gov.br/b.pdf",
                 "title": "B", "doc_type": "nfe", "published_at": None},
            ]
        if source == "nfce":
            raise downloader.requests.ConnectionError(
                "DNS resolution failed for nfce.fazenda.gov.br"
            )
        if source == "cte":
            return [
                {"url": "https://www.cte.fazenda.gov.br/c.pdf",
                 "title": "C", "doc_type": "cte", "published_at": None},
            ]
        return []

    mocker.patch.object(
        downloader, "discover_documents", side_effect=fake_discover
    )
    _patch_validate(mocker, True)

    collector = DocumentCollector(fake_storage, fake_throttler, fake_data_dir)
    inserted = collector.discover_and_register()

    assert inserted == 3

    assert fake_storage.get_by_url(
        "https://www.nfe.fazenda.gov.br/a.pdf"
    ) is not None
    assert fake_storage.get_by_url(
        "https://www.nfe.fazenda.gov.br/b.pdf"
    ) is not None
    assert fake_storage.get_by_url(
        "https://www.cte.fazenda.gov.br/c.pdf"
    ) is not None

    captured = capsys.readouterr()
    assert "[nfce] erro HTTP:" in captured.err
    assert "DNS resolution failed" in captured.err

    assert downloader.discover_documents.call_count == len(PORTAL_URLS)


def test_discover_and_register_does_not_propagate_when_all_sources_fail(
    mocker, fake_storage, fake_throttler, fake_data_dir, capsys
) -> None:
    """Se TODOS os sources falham, discover_and_register retorna 0 e NAO
    propaga a excecao (resiliencia total do loop)."""
    def fake_discover(source: str, throttler, http_session=None) -> list[dict]:
        raise downloader.requests.Timeout(f"timeout on {source}")

    mocker.patch.object(
        downloader, "discover_documents", side_effect=fake_discover
    )
    _patch_validate(mocker, True)

    collector = DocumentCollector(fake_storage, fake_throttler, fake_data_dir)
    inserted = collector.discover_and_register()

    assert inserted == 0

    captured = capsys.readouterr()
    assert captured.err.count("erro HTTP:") >= 1
