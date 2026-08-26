"""Testes para src.parser.html_parser.

Cobre (PLAN.md linhas 142-144 - Task 4.2):
    - HTML com <p> Convenio ICMS 123/2024 </p> + <script> produz texto limpo
      sem a tag script e sem espacos extras nas pontas.
    - HTML com <a href="/docs/nota.pdf"> relativo a base em dominio permitido
      retorna a URL absoluta; <a href="https://evil.com/x"> retorna [].
    - extract_text_from_html("<p>sem fechamento") NAO levanta excecao e
      retorna o texto ate onde o parser conseguiu ler.

Casos extras para 100% de cobertura:
    - Normalizacao de 3+ '\\n' consecutivos em '\\n\\n'.
    - extract_links deduplica URLs iguais e ordena alfabeticamente.
    - extract_links ignora anchors (#), javascript:, mailto: e tel:.
    - extract_links aceita dominios com prefixo www. e subdominios validos.
    - extract_links ignora tags <a> sem atributo href.
"""
from __future__ import annotations

from src.parser.html_parser import extract_links, extract_text_from_html


# --- extract_text_from_html: casos do PLAN.md ---


def test_extract_text_from_html_strips_script_and_normalizes_whitespace() -> None:
    """Tag <script> e seu conteudo NAO devem aparecer no texto extraido.

    Espacos extras nas pontas devem ser removidos via strip=True.
    """
    html = (
        "<html><body>"
        "<p>  Convenio ICMS 123/2024 </p>"
        "<script>x</script>"
        "</body></html>"
    )

    result = extract_text_from_html(html)

    assert "Convenio ICMS 123/2024" in result
    assert "<script>" not in result
    assert "</script>" not in result
    assert "x</script>" not in result
    # Sem espacos/newlines nas pontas (strip=True)
    assert result == result.strip()


def test_extract_text_from_html_does_not_raise_on_unclosed_tags() -> None:
    """HTML malformado (tag sem fechamento) NAO deve levantar excecao.

    BeautifulSoup com lxml e tolerante; o parser retorna o texto ate onde
    conseguiu interpretar. O importante e nao abortar o lote.
    """
    html = "<p>sem fechamento"

    result = extract_text_from_html(html)

    assert isinstance(result, str)
    assert "sem fechamento" in result


def test_extract_text_from_html_keeps_style_content_out() -> None:
    """Tags <style> tambem nao devem vazar para o texto (defensivo)."""
    html = "<style>body { color: red; }</style><p>visivel</p>"

    result = extract_text_from_html(html)

    assert "visivel" in result
    assert "color: red" not in result


# --- extract_text_from_html: normalizacao de whitespace ---


def test_extract_text_from_html_collapses_multiple_newlines() -> None:
    """3+ '\\n' consecutivos sao colapsados em '\\n\\n' (mesmo padrao do PDF)."""
    html = "<p>linha1</p>\n\n\n\n\n<p>linha2</p>"

    result = extract_text_from_html(html)

    assert "\n\n\n" not in result
    assert "linha1" in result
    assert "linha2" in result


def test_extract_text_from_html_empty_input_returns_empty_string() -> None:
    """String vazia retorna string vazia (sem raise)."""
    assert extract_text_from_html("") == ""


# --- extract_links: casos do PLAN.md ---


def test_extract_links_resolves_relative_and_filters_external() -> None:
    """URL relativa e resolvida contra base_url; dominio externo descartado."""
    html = (
        '<a href="/docs/nota.pdf">PDF</a>'
        '<a href="https://evil.com/x">bad</a>'
    )
    base_url = "https://www.nfe.fazenda.gov.br/portal/"
    allowed_domains = ["nfe.fazenda.gov.br"]

    result = extract_links(html, base_url, allowed_domains)

    assert result == ["https://www.nfe.fazenda.gov.br/docs/nota.pdf"]


def test_extract_links_with_external_only_returns_empty_list() -> None:
    """HTML so com link para dominio externo -> []."""
    html = '<a href="https://evil.com/x">bad</a>'
    base_url = "https://www.nfe.fazenda.gov.br/portal/"
    allowed_domains = ["nfe.fazenda.gov.br"]

    assert extract_links(html, base_url, allowed_domains) == []


# --- extract_links: dedup + ordenacao ---


def test_extract_links_dedupes_and_sorts() -> None:
    """URLs duplicadas viram uma unica entrada; resultado e ordenado."""
    html = (
        '<a href="/docs/b.pdf">B</a>'
        '<a href="/docs/a.pdf">A</a>'
        '<a href="/docs/b.pdf">B dup</a>'
        '<a href="/docs/c.pdf">C</a>'
    )
    base_url = "https://nfe.fazenda.gov.br/portal/"
    allowed_domains = ["nfe.fazenda.gov.br"]

    result = extract_links(html, base_url, allowed_domains)

    assert result == [
        "https://nfe.fazenda.gov.br/docs/a.pdf",
        "https://nfe.fazenda.gov.br/docs/b.pdf",
        "https://nfe.fazenda.gov.br/docs/c.pdf",
    ]


# --- extract_links: filtros de schemes nao-http ---


def test_extract_links_skips_anchors_and_javascript() -> None:
    """Anchors (#...), javascript:, mailto:, tel: NAO viram links."""
    html = (
        '<a href="#section">anchor</a>'
        '<a href="javascript:void(0)">js</a>'
        '<a href="mailto:x@y.z">mail</a>'
        '<a href="tel:+5511999">phone</a>'
        '<a href="/docs/ok.pdf">real</a>'
    )
    base_url = "https://nfe.fazenda.gov.br/portal/"
    allowed_domains = ["nfe.fazenda.gov.br"]

    result = extract_links(html, base_url, allowed_domains)

    assert result == ["https://nfe.fazenda.gov.br/docs/ok.pdf"]


def test_extract_links_ignores_anchors_without_href() -> None:
    """Tag <a> sem atributo href e ignorada silenciosamente."""
    html = (
        '<a>sem href</a>'
        '<a href="">vazio</a>'
        '<a href="/docs/x.pdf">ok</a>'
    )
    base_url = "https://nfe.fazenda.gov.br/portal/"
    allowed_domains = ["nfe.fazenda.gov.br"]

    result = extract_links(html, base_url, allowed_domains)

    assert result == ["https://nfe.fazenda.gov.br/docs/x.pdf"]


# --- extract_links: variantes de dominio permitido ---


def test_extract_links_strips_www_prefix_for_domain_match() -> None:
    """Prefixo www. no dominio do link NAO impede o match."""
    html = '<a href="/docs/x.pdf">x</a>'
    base_url = "https://www.nfe.fazenda.gov.br/portal/"
    allowed_domains = ["nfe.fazenda.gov.br"]

    result = extract_links(html, base_url, allowed_domains)

    assert result == ["https://www.nfe.fazenda.gov.br/docs/x.pdf"]


def test_extract_links_accepts_subdomain_of_allowed() -> None:
    """Subdominio (ex: sub.nfe.fazenda.gov.br) e aceito."""
    html = '<a href="/docs/x.pdf">x</a>'
    base_url = "https://sub.nfe.fazenda.gov.br/portal/"
    allowed_domains = ["nfe.fazenda.gov.br"]

    result = extract_links(html, base_url, allowed_domains)

    assert result == ["https://sub.nfe.fazenda.gov.br/docs/x.pdf"]


def test_extract_links_rejects_deceptive_suffix() -> None:
    """Dominio enganoso (ex: nfe.fazenda.gov.br.evil.com) NAO e aceito."""
    html = '<a href="https://nfe.fazenda.gov.br.evil.com/x">x</a>'
    base_url = "https://www.nfe.fazenda.gov.br/portal/"
    allowed_domains = ["nfe.fazenda.gov.br"]

    result = extract_links(html, base_url, allowed_domains)

    assert result == []


def test_extract_text_from_html_collapses_many_consecutive_newlines() -> None:
    """6 '\\n' consecutivos colapsam em '\\n\\n' (cobre iteracoes do while)."""
    # 6 \n seguidos: 1a iteracao do while reduz para 4, 2a para 2 (\n\n).
    # Sem tags para nao confundir com \\n injetado pelo BeautifulSoup.
    html = "a\n\n\n\n\n\nb"

    result = extract_text_from_html(html)

    assert "\n\n\n" not in result
    assert result == "a\n\nb"


def test_extract_links_default_allowed_domains_accepts_nfe() -> None:
    """Quando allowed_domains=None, usa ALLOWED_DOMAINS do hook (cobre branch)."""
    # Importa o modulo para garantir que ALLOWED_DOMAINS foi resolvido.
    from hooks.allowed_domains import ALLOWED_DOMAINS

    assert "nfe.fazenda.gov.br" in ALLOWED_DOMAINS

    html = '<a href="/docs/x.pdf">x</a>'
    base_url = "https://www.nfe.fazenda.gov.br/portal/"
    # Nao passa allowed_domains -> usa ALLOWED_DOMAINS como default.

    result = extract_links(html, base_url)

    assert result == ["https://www.nfe.fazenda.gov.br/docs/x.pdf"]
