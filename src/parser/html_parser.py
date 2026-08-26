"""Extrator de texto e links de HTML de paginas de legislacao fiscal eletronica.

Foco: limpar conteudo HTML de portais governamentais (NF-e, NFC-e, CT-e,
MDF-e, SPED, CONFAZ) para alimentar a base RAG. Tolerante a HTML malformado
(tags sem fechamento, encoding inconsistente) - a fonte de dados e a web,
nao algo que controlamos.

Contrato:
    - `extract_text_from_html(str) -> str`
    - `extract_links(str, base_url, allowed_domains=None) -> list[str]`

`extract_links` usa `ALLOWED_DOMAINS` do hook `.opencode/hooks/allowed_domains.py`
como default. Aceita override explicito para testes e para uso por outros
modulos que precisem de um filtro mais amplo ou restrito.
"""
from __future__ import annotations

from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from hooks.allowed_domains import ALLOWED_DOMAINS  # noqa: E402


def extract_text_from_html(html: str) -> str:
    """Extrai texto limpo de HTML usando BeautifulSoup com lxml.

    - Remove scripts/styles antes de extrair o texto (sua presenca como
      string solta seria ruído na base RAG).
    - Usa `separator="\\n"` para quebras entre blocos e `strip=True` para
      remover espacos nas pontas de cada nodo de texto.
    - Colapsa 3+ '\\n' consecutivos em '\\n\\n' (mesmo padrao do PDF parser).
    - NUNCA levanta excecao: BeautifulSoup com lxml e tolerante a HTML
      malformado por design.
    """
    soup = BeautifulSoup(html, "lxml")
    # Remove <script> e <style> antes de extrair texto (defensivo: get_text
    # puro ja descarta o conteudo desses elementos, mas explicitar reduz
    # chance de contaminacao por conteudo inline malicioso).
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text


def extract_links(
    html: str,
    base_url: str,
    allowed_domains: list[str] | None = None,
) -> list[str]:
    """Extrai e filtra links de um HTML para dominios permitidos.

    - Parseia `<a href="...">`.
    - Resolve URLs relativas via `urljoin(base_url, href)`.
    - Ignora anchors (`#...`), `javascript:`, `mailto:`, `tel:` e tags `<a>`
      sem atributo href.
    - Filtra para manter apenas URLs cujo dominio (com prefixo `www.`
      removido) faz match exato OU e sufixo `.domain` de algum item em
      `allowed_domains`. Isso aceita subdominios legítimos (ex:
      `sub.nfe.fazenda.gov.br`) mas rejeita ataques do tipo
      `nfe.fazenda.gov.br.evil.com`.
    - Remove duplicatas preservando a primeira ocorrencia e retorna a
      lista ordenada alfabeticamente (resultado determinístico, facil de
      testar e de logar).

    Args:
        html: Conteudo HTML bruto.
        base_url: URL usada para resolver hrefs relativos.
        allowed_domains: Lista de dominios permitidos (sem prefixo `www.`).
            Se None, usa `ALLOWED_DOMAINS` do hook `allowed_domains.py`.

    Returns:
        Lista ordenada de URLs absolutas que pertencem a `allowed_domains`.
    """
    if allowed_domains is None:
        allowed_domains = ALLOWED_DOMAINS

    soup = BeautifulSoup(html, "lxml")
    seen: set[str] = set()
    resolved: list[str] = []

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        # Ignora hrefs vazios (self-link), anchors e schemes nao-web.
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        full_url = urljoin(base_url, href)
        domain = (urlparse(full_url).hostname or "").lower().lstrip("www.")
        valid = any(domain == d or domain.endswith("." + d) for d in allowed_domains)
        if valid and full_url not in seen:
            seen.add(full_url)
            resolved.append(full_url)

    return sorted(resolved)
