"""Modulo canonico de validacao de URLs contra `ALLOWED_DOMAINS` (PLAN_SPRINT11 B).

Comportamento:
    - Scheme deve ser `http` ou `https`.
    - Prefixo `www.` do hostname e' removido apenas como prefixo isolado.
    - Hostname deve ser IGUAL a algum item canonico de `allowed_domains`
      (match exato, sem suffix-match).

    Politica (PLAN_SPRINT4 A.2 / BLOQUEANTE #3):
        - TLDs (ex.: ``gov.br``) NUNCA podem estar na allow-list. Apenas
          dominios canonicos exatos (ex.: ``nfe.fazenda.gov.br``).
        - Suffix-match DESATIVADO: ``sub.nfe.fazenda.gov.br`` e
          ``attacker.nfe.fazenda.gov.br`` sao ambos REJEITADOS.
          Apenas o hostname canonico (ex.: ``nfe.fazenda.gov.br``) e aceito.
        - Esta politica bloqueia tanto ataques de TLD (``malware.gov.br``)
          quanto deep subdomain attacks (``attacker.nfe.fazenda.gov.br``).

Importado por:
    - ``src/utils/http_guard.py`` (guard HTTP in-process).

Historico (pre-Sprint 11):
    - Antes da Sprint 11, este modulo tambem era invocado como CLI
      ``python .opencode/hooks/domain_guard.py <url>`` pelo
      ``.opencode/hooks/manifest.json`` (``type: pre_request``).
      Como opencode nao suporta nativamente esse tipo de hook (Sprint 5 C.1),
      a forma CLI era letra morta desde 2026-08-26. O bloco
      ``if __name__ == "__main__"`` foi removido em Sprint 11.
"""
from __future__ import annotations

from urllib.parse import urlparse

if __package__:
    from .allowed_domains import ALLOWED_DOMAINS
else:
    from allowed_domains import ALLOWED_DOMAINS

_ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})
_WWW_PREFIX: str = "www."
_WWW_PREFIX_LEN: int = len(_WWW_PREFIX)


def validate_url(url: str, allowed_domains: list[str] = ALLOWED_DOMAINS) -> bool:
    """Retorna `True` se a URL aponta para um dominio permitido.

    Politica: match EXATO contra `allowed_domains` (sem suffix-match).
    Casos rejeitados:
        - scheme != http/https
        - hostname `None` ou vazio
        - hostname diferente de todos os itens de `allowed_domains`
          (cobre TLD attack, deep subdomain attack, qualquer suffix-match).

    Casos aceitos:
        - Match exato: ``hostname == domain`` (apos strip do prefixo
          opcional ``www.``).
    """
    parsed = urlparse(url)

    if parsed.scheme not in _ALLOWED_SCHEMES:
        return False

    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        return False

    if hostname.startswith(_WWW_PREFIX):
        hostname = hostname[_WWW_PREFIX_LEN:]
    if not hostname:
        return False

    return hostname in allowed_domains


__all__ = ["validate_url", "ALLOWED_DOMAINS"]
