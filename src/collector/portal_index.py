"""Descobridor de documentos por portal oficial.

Para cada ``source`` conhecida (nfe, nfce, cte, mdfe, sped, confaz), faz um
``GET`` na URL raiz do portal apos aplicar ``throttler.wait()`` e retorna uma
lista de dicionarios com metadados minimos de cada documento (url, title,
doc_type, published_at).

Padroes de URL reconhecidos:

- Extensao direta ``.pdf``, ``.html``, ``.htm``.
- ``exibirArquivo.aspx?conteudo=<hash>=`` (NF-e, NFC-e, CT-e — servidor
  retorna application/pdf com o PDF anexado).
- ``onclick="download_arquivo_estatico('SISTEMA', TIPO, 'NOME.pdf')"``
  (portal SVRS usado pelo MDF-e — convertido para URL direta
  ``/<SISTEMA>/DownloadArquivoEstatico/...`` antes de retornar).

URLs que nao pertencem a ``ALLOWED_DOMAINS`` (via ``validate_url``) sao
descartadas. URLs relativas sao resolvidas contra a URL do portal via
``urllib.parse.urljoin``.

Validacao de URL (PLAN_SPRINT4 A.3):
    O coletor usa ``src.utils.http_guard.validate_url`` para filtrar
    URLs. Esta camada importa ``hooks.domain_guard`` internamente
    (fail-closed, BLOQUEANTE #2). O coletor NAO importa
    ``domain_guard`` diretamente (regra de arquitetura).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from src.utils.http_guard import ALLOWED_DOMAINS, validate_url
from src.utils.throttler import Throttler


PORTAL_URLS: dict[str, str] = {
    "nfe": "https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=04BIflQt1aY=",
    "nfce": "https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=04BIflQt1aY=",
    "cte": "https://www.cte.fazenda.gov.br/portal/listaConteudo.aspx?tipoConeudo=Y0nErnoZpsg=".replace("Coneudo", "Conteudo"),
    "mdfe": "https://dfe-portal.svrs.rs.gov.br/MDFE/Documentos",
    "sped": "https://sped.gov.br/",
    # CONFAZ descontinuado (PLAN_SPRINT4 D.1 / AGENTS.md): hosts
    # confaz.fazenda.gov.br e www.confaz.fazenda.gov.br nao resolvem
    # no DNS publico desde 2024. Decisao formal: REMOVIDO de PORTAL_URLS.
    # Para reativar, obter URL alternativa oficial via outros canais
    # (ex.: mirror SEFAZ-RS, diario oficial) e re-adicionar entrada aqui.
}

_DOWNLOAD_EXTENSIONS: tuple[str, ...] = (".pdf", ".html", ".htm")
_EXIBIR_ARQUIVO_NEEDLE: str = "exibirarquivo.aspx"  # case-insensitive; URL original vem "exibirArquivo.aspx"
_SVRS_DOWNLOAD_RE: re.Pattern[str] = re.compile(
    r"""download_arquivo_estatico\(\s*['"]([^'"]+)['"]\s*,\s*(\d+)\s*,\s*['"]([^'"]+)['"]\s*\)""",
    re.IGNORECASE,
)

# Regex para extrair data de publicacao do titulo do documento.
# Exemplos aceitos:
#   "Nota Tecnica 2025.002 v.1.51 - Publicada em 04/08/2026"
#   "Informe Tecnico 2026.001 v1.01 - Publicado em 04/08/2026"
#   "Nota Tecnica 2014.001 v.1.41 - Publicada em 04/08/2026"
_PUBLISHED_AT_RE: re.Pattern[str] = re.compile(
    r"Publicad[ao]\s+em\s+(\d{2})/(\d{2})/(\d{4})",
    re.IGNORECASE,
)


def _parse_published_at_from_title(title: str) -> datetime | None:
    """Extrai data de publicacao do titulo do documento.

    Retorna ``None`` se nao encontrar o padrao "Publicado/Publicada em DD/MM/YYYY".
    """
    if not title:
        return None
    match = _PUBLISHED_AT_RE.search(title)
    if match is None:
        return None
    d, mo, y = match.groups()
    try:
        return datetime(int(y), int(mo), int(d))
    except ValueError:
        return None


def _is_candidate_url(url: str) -> bool:
    """Verifica se a URL aponta para um documento baixavel.

    Reconhece:
        - extensao direta ``.pdf``, ``.html``, ``.htm``
        - endpoint ``exibirArquivo.aspx?conteudo=...`` (NF-e/CT-e — PDF)
    """
    lowered = url.lower()
    if any(lowered.endswith(ext) for ext in _DOWNLOAD_EXTENSIONS):
        return True
    if _EXIBIR_ARQUIVO_NEEDLE in lowered:
        return True
    return False


def _parse_svrs_onclick(onclick: str) -> tuple[str, str, str] | None:
    """Extrai ``(sistema, tipo, nome_arquivo)`` de um onclick SVRS.

    Retorna ``None`` se o onclick nao casar com o padrao esperado.
    """
    match = _SVRS_DOWNLOAD_RE.search(onclick)
    if match is None:
        return None
    return match.group(1), match.group(2), match.group(3)


def _build_svrs_download_url(portal_url: str, sistema: str, tipo: str, nome: str) -> str:
    """Constroi URL absoluta para DownloadArquivoEstatico a partir do portal."""
    parsed = urlparse(portal_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    from urllib.parse import quote
    return (
        f"{base}/{sistema}/DownloadArquivoEstatico/"
        f"?sistema={quote(sistema)}&tipoArquivo={quote(tipo)}&nomeArquivo={quote(nome)}"
    )


def discover_documents(
    source: str,
    throttler: Throttler,
    http_session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """Descobre documentos de um portal oficial.

    Args:
        source: Identificador do portal (``nfe``, ``nfce``, ``cte``, ``mdfe``,
            ``sped``). Qualquer outro valor retorna ``[]``.
        throttler: Instancia de :class:`Throttler` aplicada antes do GET.
        http_session: Opcional. Sessao ``requests`` injetada para
            testabilidade; se ``None``, uma nova ``requests.Session()`` e criada.

    Returns:
        Lista de dicionarios com chaves ``url``, ``title``, ``doc_type`` e
        ``published_at`` (extraido do titulo via regex quando possivel).
        Apenas URLs validadas por ``validate_url`` e que casem com um dos
        padroes reconhecidos sao incluidas.
    """
    if source not in PORTAL_URLS:
        return []

    throttler.wait()
    session = http_session if http_session is not None else requests.Session()

    portal_url: str = PORTAL_URLS[source]
    response = session.get(portal_url, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")
    docs: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    def _build_doc(url: str, title: str) -> dict[str, Any]:
        return {
            "url": url,
            "title": title,
            "doc_type": source,
            "published_at": _parse_published_at_from_title(title),
        }

    # 1) <a href="..."> links com URL direta (inclui exibirArquivo.aspx)
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "")
        if not isinstance(href, str) or not href:
            continue
        url = urljoin(portal_url, href)
        if not validate_url(url, ALLOWED_DOMAINS):
            continue
        if not _is_candidate_url(url):
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        title: str = anchor.get_text(strip=True) or url
        docs.append(_build_doc(url, title))

    # 2) onclick="download_arquivo_estatico(...)" (portal SVRS/MDF-e)
    for el in soup.find_all(attrs={"onclick": True}):
        onclick = el.get("onclick", "")
        if not isinstance(onclick, str):
            continue
        parsed = _parse_svrs_onclick(onclick)
        if parsed is None:
            continue
        sistema, tipo, nome = parsed
        url = _build_svrs_download_url(portal_url, sistema, tipo, nome)
        if not validate_url(url, ALLOWED_DOMAINS):
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        title_text: str = (
            el.get_text(strip=True) or f"{sistema} {nome}"
        )
        docs.append(_build_doc(url, title_text))

    return docs
