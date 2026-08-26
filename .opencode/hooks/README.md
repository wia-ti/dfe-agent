# hooks
Guardrails executados antes/depois de ações sensíveis (ex.: `domain_guard.py` bloqueia requisições fora de `ALLOWED_DOMAINS`).

## Politica anti-TLD (PLAN_SPRINT4 A.2)

O guardrail de dominio implementa uma politica anti-TLD:

- **TLDs (ex.: `gov.br`) NAO podem estar na lista.** Apenas dominios
  canonicos exatos (ex.: `nfe.fazenda.gov.br`) ou prefixos oficiais
  conhecidos (ex.: `www.gov.br`).
- **Suffix-match limitado a 2 niveis de profundidade:**
  - `*.fazenda.gov.br` aceita `nfe.fazenda.gov.br`
  - **rejeita** `attacker.nfe.fazenda.gov.br` (deep subdomain attack)
  - A regra e: o prefixo antes de `.<dominio>` deve ser um unico label
    DNS sem pontos.

Adicionar novo dominio: apenas via rule formal dfe-rules (item 2) +
teste em `tests/unit/test_domain_guard.py` cobrindo o caso positivo e
o caso de deep subdomain.
