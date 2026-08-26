"""Testes do modulo ``hooks.domain_guard`` (guardrail de dominios oficiais DFe).

Cobre (PLAN_SPRINT11 B):
    - ``validate_url()`` aceita URLs em dominios permitidos (com ou sem www).
    - ``validate_url()`` rejeita dominios externos, schemes nao-http e URLs maliciosas.

A partir da Sprint 11, ``domain_guard.py`` nao tem mais bloco
``if __name__ == "__main__"``: a forma CLI era letra morta desde
Sprint 5 C.1 (opencode nao suporta nativamente ``pre_request``).
O guard HTTP in-process vive em ``src/utils/http_guard.py``.

Criterio de conclusao (PLAN.md linhas 92-95):
    - [x] validate_url("https://www.nfe.fazenda.gov.br/docs/nt.pdf", ALLOWED_DOMAINS) -> True
    - [x] validate_url("https://malware.example.com/x.exe", ALLOWED_DOMAINS) -> False
    - [x] validate_url("ftp://nfe.fazenda.gov.br/x", ALLOWED_DOMAINS) -> False
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
HOOKS_PKG_PARENT: Path = PROJECT_ROOT / ".opencode"

if str(HOOKS_PKG_PARENT) not in sys.path:
    sys.path.insert(0, str(HOOKS_PKG_PARENT))

from hooks.allowed_domains import ALLOWED_DOMAINS  # noqa: E402
from hooks.domain_guard import validate_url  # noqa: E402


# --- validate_url: casos de aceite ---


def test_validate_url_accepts_https_with_www_prefix() -> None:
    assert (
        validate_url(
            "https://www.nfe.fazenda.gov.br/docs/nt.pdf", ALLOWED_DOMAINS
        )
        is True
    )


def test_validate_url_accepts_exact_allowed_domain() -> None:
    assert (
        validate_url("https://nfe.fazenda.gov.br/docs", ALLOWED_DOMAINS)
        is True
    )


def test_validate_url_rejects_subdomain_match() -> None:
    """Subdominios de canonical (ex.: ``sub.nfe.fazenda.gov.br``) sao REJEITADOS.

    Mudanca de politica no PLAN_SPRINT4 A.2 (BLOQUEANTE #3): suffix-match
    desativado. Apenas o hostname canonico exato e aceito. Isso blinda
    contra TLD attack (``malware.gov.br``) e deep subdomain attack
    (``attacker.nfe.fazenda.gov.br``).
    """
    assert (
        validate_url("https://sub.nfe.fazenda.gov.br/x", ALLOWED_DOMAINS)
        is False
    )


def test_validate_url_accepts_http_scheme() -> None:
    assert (
        validate_url("http://nfe.fazenda.gov.br/docs", ALLOWED_DOMAINS)
        is True
    )


# --- validate_url: casos de rejeicao ---


def test_validate_url_rejects_external_domain() -> None:
    assert (
        validate_url("https://malware.example.com/x.exe", ALLOWED_DOMAINS)
        is False
    )


def test_validate_url_rejects_deceptive_match() -> None:
    """nfce.fazenda.gov.br.evil.com NAO termina com .nfce.fazenda.gov.br.

    Verifica que o sufixo .nfce.fazenda.gov.br nao e' enganado por um
    dominio 'nfce.fazenda.gov.br.evil.com' que compartilha prefixo textual.
    """
    assert (
        validate_url(
            "https://nfce.fazenda.gov.br.evil.com/x", ALLOWED_DOMAINS
        )
        is False
    )


def test_validate_url_rejects_other_gov_br_subdomain() -> None:
    """`malware.gov.br` deve ser rejeitado (BLOQUEANTE #3).

    O TLD ``gov.br`` NAO pode estar na allow-list (politica anti-TLD).
    Apenas subdominios EXATOS como ``sped.gov.br`` ou ``www.gov.br``
    podem estar.
    """
    assert (
        validate_url("https://malware.gov.br/x", ALLOWED_DOMAINS) is False
    )


def test_validate_url_rejects_www_gov_br_direct_url() -> None:
    """`https://www.gov.br/sped/x` deve ser rejeitado (BLOQUEANTE B2 / Sprint 5).

    ``www.gov.br`` foi REMOVIDO de ``ALLOWED_DOMAINS`` no PLAN_SPRINT5 A.2
    para fechar o BLOQUEANTE residual de 2024 (politica anti-TLD).
    Apenas ``sped.gov.br`` (host exato, sem ``www.``) permanece para
    SPED. Esta regressao protege contra reintroducao acidental de
    ``www.gov.br`` ou contra URL com prefixo TLD generico.
    """
    assert (
        validate_url("https://www.gov.br/sped/pt-br", ALLOWED_DOMAINS)
        is False
    )


def test_validate_url_accepts_sped_gov_br() -> None:
    """`https://sped.gov.br/...` e' o host canonico do SPED (PLAN_SPRINT5 A.2)."""
    assert (
        validate_url("https://sped.gov.br/", ALLOWED_DOMAINS) is True
    )
    assert (
        validate_url("https://sped.gov.br/noticias/nt-2026-001", ALLOWED_DOMAINS)
        is True
    )


def test_validate_url_rejects_deep_subdomain_attack() -> None:
    """`attacker.nfe.fazenda.gov.br` deve ser rejeitado (BLOQUEANTE #3).

    Suffix-match limitado a 2 niveis de profundidade: ``*.fazenda.gov.br``
    aceita ``nfe.fazenda.gov.br``, rejeita ``attacker.nfe.fazenda.gov.br``.
    """
    assert (
        validate_url(
            "https://attacker.nfe.fazenda.gov.br/x", ALLOWED_DOMAINS
        )
        is False
    )


def test_validate_url_rejects_non_http_scheme() -> None:
    assert (
        validate_url("ftp://nfe.fazenda.gov.br/x", ALLOWED_DOMAINS)
        is False
    )


def test_validate_url_rejects_empty_string() -> None:
    assert validate_url("", ALLOWED_DOMAINS) is False


def test_validate_url_rejects_string_without_scheme() -> None:
    assert validate_url("not-a-url", ALLOWED_DOMAINS) is False


def test_validate_url_rejects_https_with_no_hostname() -> None:
    """Scheme https mas sem hostname: `https:///x` -> False.

    Cobre o branch `if not hostname:` que vem apos o parse de scheme
    (quando scheme e' http/https mas parsed.hostname e' None/vazio).
    """
    assert validate_url("https:///x", ALLOWED_DOMAINS) is False


def test_validate_url_rejects_www_only_hostname() -> None:
    """Hostname `www.` sem dominio real -> False.

    Cobre o branch `if not hostname:` apos o strip do prefixo www.
    """
    assert validate_url("https://www./path", ALLOWED_DOMAINS) is False
