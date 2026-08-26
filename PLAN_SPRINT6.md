# PLAN_SPRINT6.md

> Plano de remediacao para o `RecursionError` em `python -m src.collector --once`
> descoberto em 2026-08-26.
> Origem: traceback de runtime contra `src/utils/http_guard.py` + `.opencode/hooks/domain_guard.py`
> + `src/collector/portal_index.py`.
> Itens cobertos: **1 BLOQUEANTE** (recursao do guard HTTP in-process).
> Principio: **TDD** (teste vermelho primeiro), zero regressao nas suites existentes,
> cobertura >= 80%.
>
> NAO cobre hardening adicional (auditoria de `install_guard_once` em outros entry-points,
> smoke do coletor ponta-a-ponta, instrumentacao do `urlparse`) — itens registrados
> no Apêndice B para follow-up.

## Criterio global de conclusao

`pytest tests/ --cov=src --cov-fail-under=80` retorna exit code 0 **E** o BLOQUEANTE B6
e verificado manualmente pelo comando shell documentado em "Verificacao manual do BLOQUEANTE"
no fim deste plano **E** os 2 testes novos (`test_safe_session_get_does_not_recurse`,
`test_safe_get_does_not_recurse`) passam.

```
Fase A (unica) ──► Fase B
fix guard        regressao
recursao         automatica
BLOQUEANTE       IMPORTANTE
```

**Dependencias criticas entre fases**:
- B (testes de regressao) depende de A (fix). TDD: escrever testes novos primeiro,
  ver falhar com `RecursionError`, aplicar A, ver passar.

---

## Fase A — Corrigir auto-recursao do guard HTTP in-process (BLOQUEANTE B6)

**Criterio**: `pytest tests/integration/test_domain_guard_plugin.py` exit 0.
Apos `install_http_guard()`, `requests.Session().get(URL_AUTORIZADA)` retorna a
`Response` da rede (ou do adapter fake) **sem** recursivar; idem para `requests.get(URL_AUTORIZADA)`.

### Task A.1 — Trocar chamadas recursivas pelos originais em `src/utils/http_guard.py`

- Agent: Backend Engineer
- Input: nenhuma
- Diagnostico (resumo):
  - `install_http_guard()` faz `requests.Session.get = safe_session_get`
    (linha 113). Em runtime, `safe_session_get` valida a URL e, se aprovada,
    chama `session.get(url, **kwargs)` na linha 92. Como `Session.get` foi
    patchado, a resolucao de atributo retorna `safe_session_get`, que chama
    a si mesmo ate `RecursionError`.
  - Mesmo bug latente em `safe_get` (linha 79) — sem call-site em `src/`
    que dispare, mas e' simetria quebrada que deve ser corrigida.
- Output:
  - `src/utils/http_guard.py:79`: trocar `return requests.get(url, **kwargs)`
    por `return _original_requests_get(url, **kwargs)`.
  - `src/utils/http_guard.py:92`: trocar `return session.get(url, **kwargs)`
    por `return _original_session_get(session, url, **kwargs)`.
  - Variaveis `_original_requests_get` e `_original_session_get` ja' existem
    no modulo (linhas 95-96); sem novas dependencias.
  - Sem mudanca em `install_http_guard` / `uninstall_http_guard` (linhas 100-127):
    o save/restore das referencias originais continua correto (e' a fonte
    de verdade para o `_original_*`).
- Criterios de aceitacao:
  - [ ] `git diff src/utils/http_guard.py` mostra apenas as duas linhas alteradas.
  - [ ] Suites previas (`tests/unit/test_http_guard_bootstrap.py`,
    `tests/integration/test_domain_guard_plugin.py`,
    `tests/unit/collector/test_portal_index.py`) continuam passando.
  - [ ] Verificacao manual do BLOQUEANTE (secao abaixo) imprime "OK: ...".

---

## Fase B — Cobertura de regressao para o caminho AUTORIZADO (IMPORTANTE I6.1)

**Criterio**: `pytest tests/integration/test_domain_guard_plugin.py::test_safe_session_get_does_not_recurse
pytest tests/integration/test_domain_guard_plugin.py::test_safe_get_does_not_recurse` exit 0.

### Task B.1 — Adicionar 2 testes em `tests/integration/test_domain_guard_plugin.py`

- Agent: QA Engineer
- Input: A.1 completa
- Output:
  - `test_safe_session_get_does_not_recurse`: instala o guard, monta `Session()` +
    adapter fake (`getadapter`-based) que retorna `Response(200)`, chama
    `session.get(URL_AUTORIZADA)`, asserta 1 chamada, status 200, sem `RecursionError`.
  - `test_safe_get_does_not_recurse`: analogo em `requests.get` (mod-level).
  - Reset deterministico de `_guards_installed` (ja' documentado no fixture
    `_reset_bootstrap_state` em `test_http_guard_bootstrap.py:24`); uso do mesmo
    padrao com `monkeypatch.setattr(http_guard, "_guards_installed", False)`
    + `try/finally` com `uninstall_http_guard()`.
  - URL autorizada de exemplo: `https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=/Wo1BKrxAaW8=` (hostname canonico `nfe.fazenda.gov.br` em
    `.opencode/hooks/allowed_domains.py:18`).
  - Sem rede real: `requests-mock` (ja' em uso nos testes via `mocker.patch.object`),
    adapter custom via `session.get_adapter` ou `mocker.patch.object(req_module, "get", ...)`.
- Criterios de aceitacao:
  - [ ] Antes de A.1: testes novos falham com `RecursionError` (vermelho).
  - [ ] Depois de A.1: testes novos passam (verde).
  - [ ] `pytest tests/integration/test_domain_guard_plugin.py` overall exit 0.

---

## Verificacao manual do BLOQUEANTE

Comandos shell a serem executados **apos** A.1 e B.1 concluidas:

```bash
# BLOQUEANTE B6: guard nao recursiva para URLs autorizadas
python -c "
from src.utils import http_guard
http_guard.install_http_guard()
import requests
import unittest.mock as mock
fake = mock.MagicMock(status_code=200, raise_for_status=lambda: None)
with mock.patch.object(requests, 'get', return_value=fake):
    r = requests.get('https://www.nfe.fazenda.gov.br/portal/x', timeout=5)
    print('OK requests.get:', r.status_code)
sess = requests.Session()
with mock.patch.object(requests.Session, 'get', return_value=fake):
    r = sess.get('https://www.nfe.fazenda.gov.br/portal/x', timeout=5)
    print('OK Session.get:', r.status_code)
http_guard.uninstall_http_guard()
"
# esperado: 'OK requests.get: 200' e 'OK Session.get: 200' (sem RecursionError)

# Sanidade: URLs bloqueadas continuam sendo bloqueadas (regressao de A.1)
python -c "
from src.utils import http_guard
http_guard.install_http_guard()
import requests
try:
    requests.get('https://evil.com/x', timeout=5)
    print('FAIL: deveria ter levantado PermissionError')
except PermissionError as e:
    print('OK bloqueio preservado:', e)
http_guard.uninstall_http_guard()
"
```

## Apêndice A — Riscos conhecidos e mitigacoes

| Risco | Probabilidade | Impacto | Mitigacao |
|-------|---------------|---------|-----------|
| A.1 quebra testes que monkeypatcham `requests.Session.get` diretamente | Media | Medio | `uninstall_http_guard()` no teardown dos testes (padrao ja' usado em `test_domain_guard_plugin.py:64,92,111`); `monkeypatch.setattr(http_guard, "_guards_installed", False)` antes de cada teste. |
| B.1 testes nao conseguem reproduzir `RecursionError` antes de A.1 | Baixa | Alto | Validacao manual previa do traceback original (ja' documentada na causa raiz deste plano); se o teste nao reproduzir a recursao, e' red flag de que o teste nao esta exercitando o caminho patched. |
| Patch em `Session.get` nao cobre casos onde subclasses customizadas de `Session` redefinem `get` | Baixa | Baixo | `requests.Session.get = safe_session_get` substitui na classe base; subclasses que sobrescrevem `get` continuam usando o proprio override (escopo: o que o coletor usa e' `requests.Session()` cru). |

## Apêndice B — Itens fora do escopo desta Sprint (registro para follow-up)

1. Auditar `install_guard_once()` em `src/indexer/ingest` e `src/query/__main__` (consistencia com a centralizacao introduzida em Sprint 5 B1) — sugestao do usuario descartada para esta rodada.
2. Smoke do coletor ponta-a-ponta apos o fix (`python -m src.collector --once` real, nao teste) — depende de rede e throttling, fora de "Sem rede em integracao" (`tests.md`).
3. Instrumentar `urlparse`/`_coerce_args` para detectar recursao prematuramente (fail-fast antes do limite de recursao) — fora de escopo, o fix de A.1 ja' elimina a recursao por construcao.
4. A pergunta original do usuario ("rejeicoes da NF-e ate o final do ano") — volta a fila apos este plano; requer o guard funcional + consulta RAG.