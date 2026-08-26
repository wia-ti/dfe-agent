"""Testes unitarios de src.collector.portal_index.

Cobre:
    - discover_documents faz throttler.wait() antes de qualquer GET HTTP.
    - discover_documents retorna [] para source desconhecido.
    - discover_documents filtra URLs via validate_url (rejeita dominios fora).
    - discover_documents retorna lista de dicts com chaves {url, title, doc_type, published_at}.
    - discover_documents aceita http_session injetado (sem criar Session nova).
    - _parse_published_at_from_title extrai data do padrao "Publicado em DD/MM/YYYY".
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.collector import portal_index
from src.collector.portal_index import (
    _parse_published_at_from_title,
    _parse_svrs_onclick,
    _build_svrs_download_url,
    _is_candidate_url,
    discover_documents,
)


def _build_mock_session(html: str = "") -> MagicMock:
    session = MagicMock()
    response = MagicMock()
    response.text = html
    response.raise_for_status = lambda: None
    session.get.return_value = response
    return session


def test_discover_documents_throttles_before_get(mocker) -> None:
    mock_throttler = mocker.MagicMock()
    session = _build_mock_session()
    mocker.patch.object(portal_index, "validate_url", return_value=True)

    discover_documents("nfe", mock_throttler, http_session=session)

    assert mock_throttler.wait.call_count == 1
    assert session.get.call_count == 1


def test_discover_documents_throttles_for_every_known_source(mocker) -> None:
    mock_throttler = mocker.MagicMock()
    session = _build_mock_session()
    mocker.patch.object(portal_index, "validate_url", return_value=True)

    # CONFAZ descontinuado (PLAN_SPRINT4 D.1 / AGENTS.md).
    sources = ["nfe", "nfce", "cte", "mdfe", "sped"]
    for src in sources:
        mock_throttler.reset_mock()
        session.reset_mock()
        discover_documents(src, mock_throttler, http_session=session)
        assert mock_throttler.wait.call_count == 1, f"missing wait() for source={src}"
        assert session.get.call_count == 1, f"missing GET for source={src}"


def test_discover_documents_unknown_source_returns_empty_without_get(mocker) -> None:
    mock_throttler = mocker.MagicMock()
    session = _build_mock_session()

    result = discover_documents("portal_inexistente", mock_throttler, http_session=session)

    assert result == []
    assert session.get.call_count == 0


def test_discover_documents_unknown_source_does_not_throttle(mocker) -> None:
    """Para source desconhecido, a funcao deve retornar [] SEM chamar wait().

    Isso evita que o coletor 'engasgue' com intervalos ao receber uma source
    mal-formada — apenas fontes validas disparam o ciclo de throttling.
    """
    mock_throttler = mocker.MagicMock()

    discover_documents("xyz", mock_throttler, http_session=_build_mock_session())

    assert mock_throttler.wait.call_count == 0


def test_discover_documents_filters_urls_via_validate_url(mocker) -> None:
    """URLs que falham em validate_url sao descartadas do retorno."""
    html = (
        "<html><body>"
        '<a href="https://www.nfe.fazenda.gov.br/docs/nt.pdf">NT 1</a>'
        '<a href="https://evil.com/malware.pdf">malware</a>'
        '<a href="https://www.nfe.fazenda.gov.br/docs/nota.html">NT 2</a>'
        "</body></html>"
    )
    session = _build_mock_session(html)

    def fake_validate(url: str, allowed_domains: list[str] | None = None) -> bool:
        return "evil.com" not in url

    mocker.patch.object(portal_index, "validate_url", side_effect=fake_validate)

    docs = discover_documents("nfe", mocker.MagicMock(), http_session=session)

    urls = [d["url"] for d in docs]
    assert len(urls) == 2
    assert "https://evil.com/malware.pdf" not in urls
    assert all(u.startswith("https://www.nfe.fazenda.gov.br") for u in urls)


def test_discover_documents_returns_dicts_with_required_keys(mocker) -> None:
    html = (
        '<a href="https://www.nfe.fazenda.gov.br/docs/nt.pdf">Nota Tecnica 2019.001</a>'
    )
    session = _build_mock_session(html)
    mocker.patch.object(portal_index, "validate_url", return_value=True)

    docs = discover_documents("nfe", mocker.MagicMock(), http_session=session)

    assert len(docs) == 1
    doc = docs[0]
    assert set(doc.keys()) >= {"url", "title", "doc_type", "published_at"}
    assert doc["url"] == "https://www.nfe.fazenda.gov.br/docs/nt.pdf"
    assert doc["title"] == "Nota Tecnica 2019.001"
    assert doc["doc_type"] == "nfe"
    assert doc["published_at"] is None


def test_discover_documents_skips_non_document_extensions(mocker) -> None:
    """Apenas links .pdf/.html/.htm (case-insensitive) sao retornados."""
    html = (
        '<a href="https://www.nfe.fazenda.gov.br/page.css">css</a>'
        '<a href="https://www.nfe.fazenda.gov.br/img.png">img</a>'
        '<a href="https://www.nfe.fazenda.gov.br/docs/nt.pdf">pdf</a>'
        '<a href="https://www.nfe.fazenda.gov.br/docs/NOTAS.HTML">upper</a>'
    )
    session = _build_mock_session(html)
    mocker.patch.object(portal_index, "validate_url", return_value=True)

    docs = discover_documents("nfe", mocker.MagicMock(), http_session=session)

    urls = [d["url"] for d in docs]
    assert "https://www.nfe.fazenda.gov.br/docs/nt.pdf" in urls
    assert "https://www.nfe.fazenda.gov.br/docs/NOTAS.HTML" in urls
    assert "https://www.nfe.fazenda.gov.br/page.css" not in urls
    assert "https://www.nfe.fazenda.gov.br/img.png" not in urls


def test_discover_documents_resolves_relative_urls(mocker) -> None:
    """URLs relativas no HTML sao resolvidas contra a URL do portal."""
    html = '<a href="/docs/nt.pdf">relative</a>'
    session = _build_mock_session(html)
    mocker.patch.object(portal_index, "validate_url", return_value=True)

    docs = discover_documents("nfe", mocker.MagicMock(), http_session=session)

    assert len(docs) == 1
    assert docs[0]["url"].startswith("https://www.nfe.fazenda.gov.br")
    assert docs[0]["url"].endswith("/docs/nt.pdf")


def test_discover_documents_creates_session_when_none_provided(mocker) -> None:
    """Quando http_session=None, uma Session nova e instanciada."""
    mock_session_cls = mocker.patch.object(portal_index.requests, "Session")
    mock_session_instance = _build_mock_session()
    mock_session_cls.return_value = mock_session_instance
    mocker.patch.object(portal_index, "validate_url", return_value=True)

    discover_documents("nfe", mocker.MagicMock(), http_session=None)

    mock_session_cls.assert_called_once()
    mock_session_instance.get.assert_called_once()


def test_discover_documents_raises_on_http_error(mocker) -> None:
    """Se o GET falha (raise_for_status levanta), a excecao propaga ao caller.

    O caller (DocumentCollector.discover_and_register) e responsavel por tratar.
    """
    session = MagicMock()
    response = MagicMock()
    response.raise_for_status.side_effect = RuntimeError("HTTP 500")
    session.get.return_value = response
    mocker.patch.object(portal_index, "validate_url", return_value=True)

    with pytest.raises(RuntimeError, match="HTTP 500"):
        discover_documents("nfe", mocker.MagicMock(), http_session=session)


def test_discover_documents_uses_source_specific_portal_url(mocker) -> None:
    """Cada source conhecida dispara GET para a URL do portal correspondente.

    Atualizado em 2026: NFC-e e NF-e compartilham o mesmo portal/lista
    (`www.nfe.fazenda.gov.br/portal/listaConteudo.aspx`). CONFAZ desabilitado.
    SPED migrou para ``sped.gov.br`` (BLOQUEANTE B2 / Sprint 5); o
    antigo ``www.gov.br/sped/pt-br`` foi removido de ``ALLOWED_DOMAINS``.
    """
    session = _build_mock_session()
    mocker.patch.object(portal_index, "validate_url", return_value=True)

    cases = {
        "nfe": "nfe.fazenda.gov.br",
        "nfce": "nfe.fazenda.gov.br",  # mesmo host do NF-e
        "cte": "cte.fazenda.gov.br",
        "mdfe": "dfe-portal.svrs.rs.gov.br",  # migrou para SVRS em 2024
        "sped": "sped.gov.br",  # PLAN_SPRINT5 A.2: BLOQUEANTE B2
    }
    for source, expected_host in cases.items():
        session.reset_mock()
        discover_documents(source, mocker.MagicMock(), http_session=session)
        called_url = session.get.call_args.args[0]
        assert expected_host in called_url, (
            f"source={source} deve chamar host que contem '{expected_host}', "
            f"mas chamou '{called_url}'"
        )


def test_portal_urls_contains_all_spec_sources() -> None:
    """``PORTAL_URLS`` cobre todas as fontes oficiais declaradas em SPEC.md.

    Fontes oficiais: NF-e, NFC-e, CT-e, MDF-e, SPED, CONFAZ.

    CONFAZ foi descontinuado em 2026 (PLAN_SPRINT4 D.1): hosts
    ``confaz.fazenda.gov.br`` e ``www.confaz.fazenda.gov.br`` nao
    resolvem no DNS publico. Ver AGENTS.md "Decisoes resolvidas (Sprint 4)".
    """
    from src.collector.portal_index import PORTAL_URLS

    for required in ("nfe", "nfce", "cte", "mdfe", "sped"):
        assert required in PORTAL_URLS, (
            f"Portal '{required}' deveria estar em PORTAL_URLS. "
            f"Atual: {list(PORTAL_URLS.keys())}"
        )

    if "confaz" not in PORTAL_URLS:
        pytest.skip(
            "CONFAZ descontinuado — ver AGENTS.md (PLAN_SPRINT4 D.1)"
        )


def test_discover_documents_skips_anchors_without_href(mocker) -> None:
    """Ancoras sem href ou com href vazio sao ignoradas sem levantar excecao."""
    html = (
        "<a>no-href</a>"
        '<a href="">empty</a>'
        '<a href="https://www.nfe.fazenda.gov.br/docs/ok.pdf">OK</a>'
    )
    session = _build_mock_session(html)
    mocker.patch.object(portal_index, "validate_url", return_value=True)

    docs = discover_documents("nfe", mocker.MagicMock(), http_session=session)

    assert len(docs) == 1
    assert docs[0]["title"] == "OK"


def test_discover_documents_recognizes_exibir_arquivo_pattern(mocker) -> None:
    """Links ``exibirArquivo.aspx?conteudo=...`` sao reconhecidos como candidatos.

    O portal do NF-e e CT-e serve PDFs via esse endpoint (nao termina em .pdf).
    """
    html = (
        '<a href="exibirArquivo.aspx?conteudo=abc123=">Nota Tecnica 2019.001</a>'
    )
    session = _build_mock_session(html)
    mocker.patch.object(portal_index, "validate_url", return_value=True)

    docs = discover_documents("cte", mocker.MagicMock(), http_session=session)

    assert len(docs) == 1
    assert "exibirArquivo.aspx?conteudo=abc123=" in docs[0]["url"]
    assert docs[0]["title"] == "Nota Tecnica 2019.001"


def test_discover_documents_recognizes_svrs_download_onclick(mocker) -> None:
    """onclick ``download_arquivo_estatico('SISTEMA', TIPO, 'arquivo.pdf')``
    no portal SVRS (MDF-e) e convertido em URL ``DownloadArquivoEstatico``.
    """
    html = (
        '<a onclick="download_arquivo_estatico(\'MDFE\', 3, \'Nota_Tecnica_2024.pdf\');">'
        "Nota Tecnica 2024</a>"
    )
    session = _build_mock_session(html)
    mocker.patch.object(portal_index, "validate_url", return_value=True)

    docs = discover_documents("mdfe", mocker.MagicMock(), http_session=session)

    assert len(docs) == 1
    assert "DownloadArquivoEstatico" in docs[0]["url"]
    assert "sistema=MDFE" in docs[0]["url"]
    assert "tipoArquivo=3" in docs[0]["url"]
    assert "Nota_Tecnica_2024.pdf" in docs[0]["url"]
    assert docs[0]["title"] == "Nota Tecnica 2024"


def test_discover_documents_svrs_url_uses_portal_base(mocker) -> None:
    """A URL construida para download SVRS usa o host do portal."""
    html = (
        '<a onclick="download_arquivo_estatico(\'MDFE\', 1, \'MOC.pdf\');">MOC</a>'
    )
    session = _build_mock_session(html)
    mocker.patch.object(portal_index, "validate_url", return_value=True)

    docs = discover_documents("mdfe", mocker.MagicMock(), http_session=session)

    assert docs[0]["url"].startswith("https://dfe-portal.svrs.rs.gov.br/MDFE/DownloadArquivoEstatico/")


# --- _parse_published_at_from_title ---


def test_parse_published_at_from_title_extracts_br_date() -> None:
    """Extrai data no formato DD/MM/YYYY de "Publicado/Publicada em DD/MM/YYYY"."""
    assert _parse_published_at_from_title(
        "Nota Tecnica 2025.002 v.1.51 - Publicada em 04/08/2026"
    ) == datetime(2026, 8, 4)


def test_parse_published_at_from_title_handles_masculine_form() -> None:
    """Aceita tambem "Publicado em" (genero masculino: Informe Tecnico)."""
    assert _parse_published_at_from_title(
        "Informe Tecnico 2026.001 v1.01 - Publicado em 04/08/2026"
    ) == datetime(2026, 8, 4)


def test_parse_published_at_from_title_is_case_insensitive() -> None:
    """Match case-insensitive em "Publicado/Publicada"."""
    assert _parse_published_at_from_title(
        "PUBLICADA EM 15/03/2025 - NT exemplo"
    ) == datetime(2025, 3, 15)


def test_parse_published_at_from_title_returns_none_when_missing() -> None:
    """Titulo sem data no padrao retorna None (sem erro)."""
    assert _parse_published_at_from_title("Convenio ICMS 123/2024") is None
    assert _parse_published_at_from_title("") is None
    assert _parse_published_at_from_title("CT-e Manual de Orientacao") is None


def test_parse_published_at_from_title_rejects_invalid_date() -> None:
    """Data invalida (ex: 31/02/2025) retorna None em vez de levantar excecao."""
    assert _parse_published_at_from_title("NT - Publicada em 31/02/2025") is None


def test_discover_documents_populates_published_at_from_title(mocker) -> None:
    """Cada doc retornado tem ``published_at`` parseado do titulo quando possivel."""
    html = (
        '<a href="exibirArquivo.aspx?conteudo=abc=">'
        "Nota Tecnica 2025.002 v.1.51 - Publicada em 04/08/2026</a>"
    )
    session = _build_mock_session(html)
    mocker.patch.object(portal_index, "validate_url", return_value=True)

    docs = discover_documents("cte", mocker.MagicMock(), http_session=session)

    assert len(docs) == 1
    assert docs[0]["published_at"] == datetime(2026, 8, 4)


def test_discover_documents_published_at_is_none_when_title_has_no_date(mocker) -> None:
    """Titulo sem data retorna published_at=None (sem quebrar)."""
    html = (
        '<a href="https://www.nfe.fazenda.gov.br/docs/nt.pdf">Manual sem data</a>'
    )
    session = _build_mock_session(html)
    mocker.patch.object(portal_index, "validate_url", return_value=True)

    docs = discover_documents("nfe", mocker.MagicMock(), http_session=session)

    assert len(docs) == 1
    assert docs[0]["published_at"] is None
