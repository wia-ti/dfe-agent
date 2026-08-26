# PLAN_FIXES.md

> Plano de remediacao para os achados do code-reviewer.
> Origem: relatorio de revisao contra `SPEC.md` + `PLAN.md` + `PLAN_SPRINT2.md` + `PLAN_SPRINT3.md`.
> Itens cobertos: **5 BLOQUEANTE** + **7 IMPORTANTE** (12 total).
> Principio: **TDD** (teste vermelho primeiro), zero regressao nas suites existentes, cobertura >= 80%.
>
> NAO cobre os 9 SUGESTAO (lista em `AGENTS.md` Decisoes pendentes para arbitragem humana).

## Criterio global de conclusao

`pytest tests/ --cov=src --cov-fail-under=80` retorna exit code 0 **E** os 5 BLOQUEANTE
sao verificados manualmente por comandos shell documentados na secao "Verificacao manual"
de cada fase.

```
Fase A ──► Fase B ──► Fase C ──► Fase D ──► Fase E
guardrail  dispatch   deps      funcional   qualidade
hardening  @-mention  pinning  CONFAZ/      perf/logs/
(security)  routing           frontmatter  hooks
                              /eval_set
```

**Dependencias criticas entre fases**:
- A.2 (decisao sobre sufixo gov.br) → A.1 (fail-closed) conceitualmente; executar A.1 primeiro.
- D.3 (eval_set URLs reais) → D.1 (CONFAZ reativado).
- E.3 (hook type correto) → B.1 (dispatch refatorado suporta novo evento).

---

## Fase A — Hardening do guardrail de dominio (BLOQUEANTE #2, #3, #4)

**Criterio**: `pytest tests/unit/test_domain_guard.py tests/unit/collector/ tests/integration/test_guardrails.py` exit 0.
Sob `domain_guard` ausente no `sys.path`, qualquer importacao em `src/` levanta `RuntimeError`,
nunca retorna `True` silenciosamente.

### Task A.1 — Fail-closed fallback em `validate_url` (resolve BLOQUEANTE #2)

- Agent: Backend Engineer
- Input: nenhuma
- Output:
  - `src/collector/portal_index.py:39-46` e `src/collector/downloader.py:27-33`:
    substituir o bloco `try/except ImportError: def validate_url(...): return True`
    por um que **levante `RuntimeError("domain_guard indisponivel; guardrail exige-o")`**.
  - Adicionar `tests/unit/collector/test_fallback_fail_closed.py` com 2 testes:
    - `test_collector_raises_when_domain_guard_missing`: apos `sys.modules.pop("domain_guard")`
      e remocao do path, `from src.collector.downloader import DocumentCollector`
      levanta `RuntimeError`.
    - `test_portal_index_raises_when_domain_guard_missing`: analogo para `portal_index`.
  - Adicionar fixture em `tests/conftest.py` que adiciona `.opencode/hooks` ao `sys.path`
    **automaticamente** (elimina dependencia de import manual nos testes existentes).

- Criterios de aceitacao:
  - [ ] `pytest tests/unit/collector/test_fallback_fail_closed.py` passa (2 testes).
  - [ ] `git grep "return True" src/collector/` retorna 0 ocorrencias dentro de funcoes
    nomeadas `validate_url`.
  - [ ] Suites previas (`tests/unit/collector/test_downloader.py`,
    `tests/integration/test_guardrails.py::test_guardrail_domain_blocks_external`)
    continuam passando.

### Task A.2 — Substituir `www.gov.br` por hosts exatos (resolve BLOQUEANTE #3)

- Agent: Backend Engineer
- Input: A.1 completa (fail-closed primeiro, senao o teste desta task usa o stub)
- Output:
  - `.opencode/hooks/allowed_domains.py:24`:
    - **Remover** `"www.gov.br"`.
    - Adicionar **somente** o subdominio exato do SPED se ja migrado (verificar:
      `curl -I https://sped.gov.br`); caso contrario, manter `sped.rfb.gov.br` ja presente.
  - `.opencode/hooks/domain_guard.py:49-51`: explicitar no docstring que a politica
    e match exato OU suffix `.dominio_canonico` (sem jamais cobrir TLD).
  - Decisao documentada em `.opencode/hooks/README.md`:
    "Sufixo so entre 2 niveis (`*.fazenda.gov.br` aceita `nfe.fazenda.gov.br`,
    rejeita `attacker.nfe.fazenda.gov.br`). TLD (`gov.br`) nao pode estar na lista."
  - `tests/unit/test_domain_guard.py`:
    - `test_validate_url_rejects_other_gov_br_subdomain`:
      `validate_url("https://malware.gov.br/x")` retorna `False`.
    - `test_validate_url_rejects_deep_subdomain_attack`:
      `validate_url("https://attacker.nfe.fazenda.gov.br/x")` retorna `False`
      (decisao: limitar a 2 niveis de profundidade).
    - Atualizar `test_validate_url_accepts_subdomain_match` se necessario
      (regressao do comportamento `sub.nfe.fazenda.gov.br` aceito).

- Criterios de aceitacao:
  - [ ] `pytest tests/unit/test_domain_guard.py` passa (3 testes novos + existentes).
  - [ ] `git grep "www.gov.br" .opencode/ src/` retorna 0 (apenas comentario em changelog
    se houver).
  - [ ] `.opencode/hooks/README.md` documenta a politica anti-TLD.

### Task A.3 — Conectar `manifest.json` ao dispatcher real (resolve BLOQUEANTE #4)

- Agent: Backend Engineer
- Input: A.1 e A.2 completas
- Output:
  - `.opencode/plugin/agent-hooks.ts:154-238`:
    - No hook `config`, ler `.opencode/hooks/manifest.json` e registrar wrappers
      para `requests.get`, `requests.Session.get`, `urllib.request.urlopen`.
    - Cada wrapper: parse URL, executar `validate_url`, levantar `Error` se bloqueado.
  - Remover o stub em `src/collector/portal_index.py:40` e `src/collector/downloader.py:28`
    (agora a guarda vem do plugin, nao mais do in-process try/except).
  - `tests/integration/test_domain_guard_plugin.py` (novo):
    - `test_plugin_loads_manifest_and_registers_domain_guard`: importa o plugin,
      verifica que `manifest.json` foi parseado e 1 hook registrado.
    - `test_requests_get_blocks_evil_url`: `requests.get("https://evil.com/x")` sob
      plugin mockado levanta `PermissionError`.
    - `test_requests_get_allows_nfe_url`: `requests.get("https://www.nfe.fazenda.gov.br/x.pdf")`
      passa.
    - `test_plugin_warns_when_manifest_missing`: manifest ausente → warning no log,
      modo permissivo (degradacao controlada).

- Criterios de aceitacao:
  - [ ] `pytest tests/integration/test_domain_guard_plugin.py` passa.
  - [ ] `git grep "from domain_guard" src/` retorna 0 (stub removido).
  - [ ] Plugin sob manifest vazio **nao derruba** opencode (graceful degradation).

---

## Fase B — Correcao do dispatch do code-reviewer (BLOQUEANTE #1)

**Criterio**: `@code-reviewer` invocado via opencode @-mention **seta `DFE_ACTIVE_AGENT=code-reviewer`**
no shell env do processo Python; tentativa de `Edit`/`Write` e bloqueada pelo hook `pre_tool_use.py`.

### Task B.1 — Propagacao de `DFE_ACTIVE_AGENT` no dispatch de @-mention

- Agent: Prompt Engineer (CLI) + Backend Engineer (plugin fallback)
- Input: nenhuma
- Output:
  - Investigar como opencode CLI roteia @-mentions (flag `--agent`, env var injetada,
    ou metadata de sessao).
  - `.opencode/plugin/agent-hooks.ts:137-152` (`detectAgentFromSession`):
    - Adicionar fallback **explícito** que escaneia `process.argv` e `process.env`
      por slug do agent conhecido (`code-reviewer`, `backend-engineer`, etc.).
    - Quando nenhum agent e detectado, **registrar warning** em
      `storage/agent_hooks.log` com mensagem
      `"[session] agent nao detectado; modo permissivo (bypass ativo)"`.
  - `.claude/hooks/code-reviewer/pre_tool_use.py:42` (`detect_active_agent`):
    quando `payload` nao identifica agent e env var ausente, registrar warning
    (via `log_event`) antes de retornar `"session"`.
  - `tests/integration/test_agent_dispatch.py` (novo):
    - `test_dfe_active_agent_env_propagates_to_subprocess`:
      ao invocar `python -c "import os; print(os.environ['DFE_ACTIVE_AGENT'])"`
      sob contexto simulado de code-reviewer, retorna `"code-reviewer"`.
    - `test_code_reviewer_blocks_write_in_subprocess`:
      `Edit` em subprocesso com `DFE_ACTIVE_AGENT=code-reviewer` levanta
      `PermissionError` (exit 2 do hook).
    - `test_no_agent_logs_warning_and_runs_permissive`:
      sem env var, hook nao dispara mas warning e logado.

- Criterios de aceitacao:
  - [ ] Verificacao manual: `@code-reviewer foo` em opencode CLI + `Edit foo.py`
    → hook bloqueia (exit 2).
  - [ ] `pytest tests/integration/test_agent_dispatch.py` passa (3 testes).
  - [ ] `storage/agent_hooks.log` tem entrada `[session] agent nao detectado`
    em sessoes sem slug explicito.

---

## Fase C — Higiene de schema e dependencias (IMPORTANTE #1, #2)

**Criterio**: `pyproject.toml` e `requirements.txt` declaram o **mesmo conjunto** de pacotes
com **pin exato** (`==X.Y.Z`); `pip install -e .` em venv novo reproduz o mesmo env de quem usa
`pip install -r requirements.txt`.

### Task C.1 — Sincronizar dependencias e pin exato

- Agent: Backend Engineer
- Input: nenhuma
- Output:
  - `pyproject.toml:14-22`:
    adicionar `transformers==X.Y.Z`, `huggingface_hub==X.Y.Z`, `accelerate==X.Y.Z`,
    `pytest==X.Y.Z`, `pytest-mock==X.Y.Z`, `pytest-cov==X.Y.Z` (mesmas versoes que
    `requirements.txt`).
  - `requirements.txt:1-14`:
    substituir todos os `>=X,<Y` por `==X.Y.Z`, mantendo sincronia com `pyproject.toml`.
    Versoes de referencia: executar `pip freeze` no venv atual e copiar valores.
  - Documentar em `AGENTS.md` "Padroes de codigo": "Pin exato obrigatorio; bounds
    (`>=X,<Y`) so para libs com churn alto documentado em comentario."
  - `tests/unit/test_dependency_pinning.py` (novo):
    - `test_pyproject_and_requirements_have_same_packages`: parse de ambos, assert
      `set(python_pkg_names) == set(requirements_pkg_names)`.
    - `test_all_versions_are_exact`: regex `==\d+\.\d+\.\d+` em ambos arquivos.

- Criterios de aceitacao:
  - [ ] `pytest tests/unit/test_dependency_pinning.py` passa (2 testes).
  - [ ] `diff <(grep -oP '\S+' pyproject.toml | sort -u) <(grep -oP '^[a-zA-Z]' requirements.txt | sort -u)` retorna vazio.
  - [ ] `git grep ">=" requirements.txt` retorna 0.

---

## Fase D — Correcoes funcionais (BLOQUEANTE #5, IMPORTANTE #3, #6)

**Criterio**: `python -m src.collector --dry-run` lista URLs CONFAZ (ou decisao formal em
`AGENTS.md`); `opencode run` carrega `dfe-agent.md` sem warning; `python -m src.eval` produz
`recall_at_5 > 0` para ao menos 1 pergunta.

### Task D.1 — Reativar descoberta CONFAZ (resolve BLOQUEANTE #5)

- Agent: Backend Engineer
- Input: A.2 completa (decisao gov.br afeta URL CONFAZ)
- Output:
  - Investigar URL alternativa oficial do CONFAZ:
    - Verificar `https://www.confaz.fazenda.gov.br/legislacao` (atual em SPEC).
    - Se nao resolve, testar mirror em `confaz.fazenda.gov.br` direto (sem `www.`)
      ou SEFAZ-RS (`www.sefaz.rs.gov.br` nao esta em `ALLOWED_DOMAINS`).
  - `src/collector/portal_index.py:55-59`:
    - Adicionar entrada `"confaz": "<URL_VERIFICADA>"` com comentario citando
      fonte e data da verificacao (ex.: `"# verificado em 2026-XX-XX via ..."`).
    - Se nao houver URL alternativa viavel, **registrar decisao formal** em
      `AGENTS.md` "Decisoes pendentes" e remover CONFAZ de `SPEC.md`
      (atualizar AGENTS.md e PLAN_SPRINT3 se necessario).
  - `tests/unit/collector/test_portal_index.py`:
    - `test_portal_urls_contains_all_spec_sources`: `assert "confaz" in PORTAL_URLS`
      se URL viavel; senao, `pytest.skip("CONFAZ descontinuado — ver AGENTS.md")`.

- Criterios de aceitacao:
  - [ ] `python -m src.collector --dry-run` lista ao menos 1 URL CONFAZ,
    OU `AGENTS.md` documenta formalmente a descontinuidade.
  - [ ] `pytest tests/unit/collector/test_portal_index.py` passa.

### Task D.2 — Corrigir frontmatter de `dfe-agent.md` (resolve IMPORTANTE #3)

- Agent: Prompt Engineer
- Input: nenhuma
- Output:
  - Investigar provider real do `MiniMax-M3` no opencode CLI deste usuario
    (`opencode config get providers` ou `.opencode/plugin/` carregado).
  - `.opencode/agent/dfe-agent.md:3`:
    mudar para `model: <provider_real>/MiniMax-M3`. Se provider desconhecido,
    registrar decisao em `AGENTS.md` com placeholder explicito
    (`model: PROVIDER/MiniMax-M3` + nota).
  - `tests/unit/test_dfe_agent_definition.py:33-36`:
    atualizar regex para `r"^model:\s*\S+/\S+\s*$"` (provider/model).
  - `tests/unit/test_dfe_fiscal_skill_definition.py`: verificar se ha assert
    similar (skill nao precisa de `model`, mas deve ter `name`/`description`).

- Criterios de aceitacao:
  - [ ] `pytest tests/unit/test_dfe_agent_definition.py` passa com novo regex.
  - [ ] `opencode agent list` mostra `dfe-agent` sem warning de validacao.

### Task D.3 — Corrigir `eval_set.json` para bater com URLs reais (resolve IMPORTANTE #6)

- Agent: QA Engineer
- Input: D.1 completa (CONFAZ reativado para ter URLs reais)
- Output:
  - Executar `python -m src.collector --once` em ambiente isolado (ou via
    `tests/integration/conftest.py::fake_portal_url`) para obter URLs reais
    de cada portal.
  - `tests/fixtures/eval_set.json`:
    para cada pergunta, substituir `expected_doc_url` pelo URL **real** descoberto
    (ex.: `https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=...`).
  - `src/eval/runner.py`:
    mudar match de **exato** para **match por dominio + token**:
    `expected_doc_url` define o **dominio** esperado (regex `^https?://([^/]+)/`);
    URL real e qualquer um daquele dominio com pelo menos 1 keyword de
    `expected_keywords` em seu `text` ou `doc_title`.
  - `tests/unit/test_eval_runner.py` e `tests/unit/test_eval_ab.py`:
    atualizar para refletir a nova logica (testes devem cobrir match parcial).

- Criterios de aceitacao:
  - [ ] `python -m src.eval --eval-set tests/fixtures/eval_set.json --report /tmp/r.json`
    produz `recall_at_5 > 0` para ao menos 1 pergunta do corpus real.
  - [ ] `pytest tests/unit/test_eval_runner.py tests/unit/test_eval_ab.py` passa.
  - [ ] `storage/benchmark_report.json` (se regenerado) tem `recall_at_k` nao-zero.

---

## Fase E — Qualidade e observabilidade (IMPORTANTE #4, #5, #7)

**Criterio**: `git grep "except Exception.*BLE001" src/` retorna 0 (ou apenas com `logger.warning`
antes); `_apply_v2` e `_apply_v6` fazem 1 `PRAGMA table_info` por execution; hooks `learning_*`
disparam **apos** o subagent terminar.

### Task E.1 — Cache de `PRAGMA table_info` em migrations (resolve IMPORTANTE #4)

- Agent: Backend Engineer
- Input: nenhuma
- Output:
  - `src/db/migrations.py:_apply_v2`:
    pre-computar `existing = _existing_columns(conn, "documents")` uma vez
    e passar para as 4 chamadas a `_ensure_column` (modificar helper para aceitar
    `existing: set[str] | None = None`).
  - `src/db/migrations.py:_apply_v6:208-215`:
    pre-computar `existing_chunk_meta = {row[1] for row in conn.execute("PRAGMA table_info(chunk_metadata)")}`
    uma vez e reusar nas 2 checagens (`kind`, `parent_chunk_id`).
  - `tests/unit/db/test_migrations.py`:
    - `test_apply_v2_calls_table_info_documents_once`: spy em
      `conn.execute("PRAGMA table_info(documents)")`, assert call_count == 1.
    - `test_apply_v6_calls_table_info_chunk_metadata_once`: analogo para v6.

- Criterios de aceitacao:
  - [ ] `pytest tests/unit/db/test_migrations.py` passa (2 testes novos).
  - [ ] Suites previas (`tests/unit/db/test_sqlite_storage_v2.py`) continuam passando.

### Task E.2 — Logging em `except Exception` (resolve IMPORTANTE #5)

- Agent: Backend Engineer
- Input: nenhuma
- Output:
  - `src/query/query_engine.py:1-23`:
    adicionar `from src.utils.logger import get_logger; logger = get_logger(__name__)`.
  - `src/query/query_engine.py:190, 240, 258, 306, 340, 349, 370`:
    substituir cada `except Exception:  # noqa: BLE001 — fallback gracas`
    por `except Exception as exc: logger.warning("query_engine fallback: %s", exc); return ...`.
  - Auditar `src/parser/`, `src/indexer/`, `src/db/` por outros `except Exception`
    com `# noqa: BLE001` ou sem logging — adicionar `logger.warning` onde aplicavel.
  - `tests/unit/query/test_query_engine.py`:
    - `test_search_logs_warning_on_embedding_failure`: mock `embedder.embed` para
      levantar `RuntimeError("model not loaded")`, assert `search()` retorna `[]`
      E `caplog.records` contem nivel WARNING com substring "model not loaded".

- Criterios de aceitacao:
  - [ ] `git grep "noqa: BLE001" src/` retorna 0 (ou somente com `logger.warning` antes).
  - [ ] `pytest tests/unit/query/test_query_engine.py` passa (teste novo incluido).
  - [ ] Cobertura de `src/query/query_engine.py` mantida >= 95%.

### Task E.3 — Corrigir tipo dos hooks `learning_*` (resolve IMPORTANTE #7)

- Agent: Prompt Engineer
- Input: B.1 completa (dispatch refatorado suporta o novo tipo de evento)
- Output:
  - `.opencode/hooks/manifest.json:18-35`:
    trocar `"type": "pre_request"` por `"type": "subagent_end"` (ou `post_request`,
    conforme suporte real do opencode). Atualizar comentario inline.
  - `.opencode/plugin/agent-hooks.ts:213-237`:
    estender handler `event` para mapear `event.type === "subagent_end"` para o
    hook `learning_subagent_stop.py`, e `event.type === "session.idle"` para
    `learning_stop.py` (ja existe).
  - `.opencode/hooks/learning_subagent_stop.py` e `learning_stop.py`:
    garantir **idempotencia**: rodar 2x na mesma sessao nao duplica entrada
    em `.claude/knowledge/` (checar se ja existe antes de criar).

- Criterios de aceitacao:
  - [ ] `manifest.json` declara tipo correto (verificar contra schema do opencode).
  - [ ] Rodar `opencode run "pergunta"` + `exit` resulta em **uma** entrada `.md`
    nova em `.claude/knowledge/` (verificado por contagem de arquivos mtime > start).
  - [ ] Rodar 2 sessoes identicas seguidas nao duplica a entrada.

---

## Resumo de paralelismo e agents

### Tasks paralelas por fase

| Fase | Tasks em paralelo | Pico de paralelismo |
|------|-------------------|---------------------|
| A    | A.1 ‖ A.2 ‖ A.3 (A.2 depende conceitual de A.1; A.3 de A.1+A.2) | 1 |
| B    | B.1 | 1 |
| C    | C.1 | 1 |
| D    | D.1 ‖ D.2 (D.3 depende de D.1) | 2 |
| E    | E.1 ‖ E.2 (E.3 depende de B.1) | 2 |

**Pico absoluto**: 2 agents simultaneos. Nenhuma fase tem paralelismo intra-fase real
(deps cruzadas fortes: A.2->A.1, A.3->A.1+A.2, D.3->D.1, E.3->B.1).

### Total de tasks e agents

- **Total de tasks**: 12
- **Papeis necessarios**:
  - **Backend Engineer** — A.1, A.2, A.3, C.1, D.1, E.1, E.2 (7 tasks, 58%)
  - **Prompt Engineer** — B.1, D.2, E.3 (3 tasks, 25%)
  - **QA Engineer** — D.3 (1 task, 8%)
  - **code-reviewer** — revisao final de cada fase antes de marcar done (1 task recorrente, 8%)
  - **ML Engineer** — nenhuma task neste plano.

### Criterios de aceitacao globais

- [ ] Todos os 12 checkboxes de fases acima marcados.
- [ ] `pytest tests/ --cov=src --cov-fail-under=80` exit 0 em CI limpo.
- [ ] 5 verificacoes manuais (uma por BLOQUEANTE) executadas e registradas.
- [ ] `code-reviewer` re-convocado na conclusao emite relatorio final sem novos BLOQUEANTE.

---

## Apêndice A — Verificacao manual dos BLOQUEANTE

Comandos shell a serem executados **apos** todas as fases concluidas:

```bash
# BLOQUEANTE #1: @-mention propaga env var e hook bloqueia
DFE_ACTIVE_AGENT=code-reviewer python .claude/hooks/code-reviewer/pre_tool_use.py \
  <<< '{"tool_name":"Edit","tool_input":{"file_path":"README.md"}}'
# Esperado: exit 2 + stderr contendo "BLOQUEADO"

# BLOQUEANTE #2: domain_guard ausente → RuntimeError, nao retorno True
cd /tmp && python -c "import sys; sys.path = [p for p in sys.path if 'hooks' not in p]; from src.collector.downloader import validate_url"
# Esperado: RuntimeError; nunca return True

# BLOQUEANTE #3: gov.br TLD bloqueado
python -c "from domain_guard import validate_url; assert validate_url('https://malware.gov.br/x') == False"

# BLOQUEANTE #4: manifest.json e lido pelo plugin
python -c "import json; m = json.load(open('.opencode/hooks/manifest.json')); assert any(h['name']=='domain_guard' for h in m['hooks'])"

# BLOQUEANTE #5: CONFAZ descoberto (ou decisao formal em AGENTS.md)
python -m src.collector --dry-run 2>&1 | grep -i confaz
# OU: grep -i "CONFAZ descontinuado" AGENTS.md retorna match
```

## Apêndice B — Riscos conhecidos e mitigacoes

| Risco | Probabilidade | Impacto | Mitigacao |
|-------|---------------|---------|-----------|
| A.1 quebra testes existentes que dependem do stub | Alta | Medio | Manter stub apenas em `conftest.py` para testes (nao em `src/`) |
| B.1 exige mudanca na CLI opencode (fora do repo) | Media | Alto | Fallback no plugin + warning logged; documentar em AGENTS.md |
| D.1 descobre que CONFAZ nao tem URL alternativa viavel | Media | Baixo | Decisao formal em AGENTS.md e remocao de SPEC.md |
| D.2 descobre que provider do MiniMax-M3 nao e configurado | Alta | Medio | Registrar como "decisao pendente" em AGENTS.md |
| E.3 descobre que opencode nao suporta `subagent_end` | Media | Baixo | Manter `pre_request` + adicionar idempotencia para evitar duplicacao |
