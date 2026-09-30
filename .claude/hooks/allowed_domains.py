"""Lista permitida de dominios oficiais para coleta de documentacao fiscal eletronica.

Sao apenas dominios dos orgaos publicos brasileiros responsaveis pela publicacao
de documentos do ecossistema DFe (NF-e, NFC-e, CT-e, MDF-e, SPED, CONFAZ).

Politica (PLAN_SPRINT4 A.2 / BLOQUEANTE #3):
    - TLDs (ex.: ``gov.br``) NUNCA podem estar na lista. Apenas dominios
      canonicos exatos ou prefixos oficiais conhecidos.
    - Suffix-match do ``domain_guard`` aceita apenas 1 nivel de subdominio
      alem do canonico (ex.: aceita ``sub.nfe.fazenda.gov.br``, rejeita
      ``attacker.nfe.fazenda.gov.br``).

Adicionar novo dominio apenas via rule formal dfe-rules (item 2).
"""
from __future__ import annotations

ALLOWED_DOMAINS: list[str] = [
    "nfe.fazenda.gov.br",
    "nfce.fazenda.gov.br",
    "cte.fazenda.gov.br",
    "mdfe.fazenda.gov.br",
    "sped.rfb.gov.br",
    "sped.gov.br",
    "confaz.fazenda.gov.br",
    "dfe-portal.svrs.rs.gov.br",
]
