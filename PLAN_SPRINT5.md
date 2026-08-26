# PLAN_SPRINT5.md

> Plano de remediacao para os achados da revisao completa do DFe-Agent.
> Origem: relatorio de revisao contra `SPEC.md` + `PLAN.md` + `PLAN_SPRINT2.md` +
> `PLAN_SPRINT3.md` + `PLAN_SPRINT4.md` + `.claude/rules/*.md`.
> Itens cobertos: **2 BLOQUEANTE** + **8 IMPORTANTE** + **7 PARCIAL/SUGESTAO** (17 total).
> Fase F (adicionada em 2026-08-25) cobre a resiliencia do agente LLM
> ao embedding fail (F.1, F.2) e hardening do ambiente Windows (F.3).
> Principio: **TDD** (teste vermelho primeiro), zero regressao nas suites existentes,
> cobertura >= 80%.
>
> NAO cobre as melhorias esteticas ou decisoes de UX/UI (fora de escopo do
> code-reviewer).

## Criterio global de conclusao

`pytest tests/ --cov=src --cov-fail-under=80` retorna exit code 0 **E** os 2 BLOQUEANTE
sao verificados manualmente pelos comandos shell documentados na secao
"Verificacao manual dos BLOQUEANTE" no fim deste plano **E** os 8 IMPORTANTE
tem teste automatizado cobrindo o desvio **E** os testes de Fase F
(`test_embedding_load_failure.py`, `test_embedding_load_float16.py`)
passam.

```
Fase A ──► Fase B ──► Fase C ──► Fase D ──► Fase E ──► Fase F
guardrail  docs/      plugin/    tests/     polish     embedding
runtime    frontmatter manifest  cmd_reidx  opcional   fail / agent
                           /event   eval_set             improvisa
BLOQUEANTE IMPORTANTE  IMPORTANTE  PARCIAL    SUGESTAO   IMPORTANTE
```

**Dependencias criticas entre fases**:

- A.1 (instalar guard em runtime) nao depende de ninguem — vem primeiro.
- A.2 (remover `www.gov.br`) e independente de A.1.
- B.1 (remover CONFAZ do SPEC) depende de confirmacao humana se URL CONFAZ
  deve sair do SPEC; tarefa registra a decisao, nao a altera sozinha.
- B.2 (path da skill) exige decisao humana previa (qual convencao o opencode
  CLI deste usuario aceita); tarefa implementa a opcao escolhida.
- C.2 (event type no plugin) depende de C.1 (plugin precisa estar carregado
  para sabermos se ele escuta `session_end`).
- D.2 (eval_set sem CONFAZ) depende de B.1.
- E.* (polish) sem deps.
- F.2 (skill do agente menciona env var) depende de F.1
  (`DFE_EMBEDDING_DTYPE` precisa estar documentada no codigo antes
  de ser citada na skill). F.1 e F.3 sao independentes entre si.

---

## Fase A — Guardrail de dominio em runtime (BLOQUEANTE B1, B2 + IMPORTANTE I6)

**Criterio**: `pytest tests/unit/collector/ tests/integration/test_guardrails.py
tests/integration/test_domain_guard_plugin.py` exit 0.
Quando `python -m src.collector --once` ou `python -m src.collector --dry-run`
sao executados, qualquer chamada HTTP passa por `validate_url` antes do I/O
(nao apenas `requests.get` mas tambem `requests.Session.get`).

### Task A.1 — Instalar `install_http_guard()` no boot dos entry-points

- Agent: Backend Engineer
- Input: nenhuma
- Output:
  - `src/collector/__main__.py`: importar `install_http_guard` e chamar
    uma unica vez no inicio de `main()` (antes de instanciar
    `Throttler`/`DocumentCollector`). Idempotente via flag
    `_guards_installed` em `http_guard.py`.
  - `src/indexer/ingest.py` (CLI): instalar guard no `main()` tambem,
    pois o ingest pode ser invocado fora do collector.
  - `src/query/__main__.py`: instalar guard no `main()` (defesa em
    profundidade — o query hoje nao faz HTTP externo, mas pode ser
    estendido).
  - Novo modulo `src/utils/http_guard_bootstrap.py` com funcao
    `install_guard_once()` que importa `http_guard` e chama
    `install_http_guard()` em um unico lugar (evita duplicacao).
  - `tests/unit/test_http_guard_bootstrap.py` (novo, 2 testes):
    - `test_install_guard_once_idempotent`: chamar 2x nao duplica
      registro.
    - `test_install_guard_once_invokes_install_http_guard`: assert que
      `http_guard.install_http_guard` foi chamado (via `monkeypatch`).
  - `tests/integration/test_guardrails.py`: adicionar teste
    `test_guardrail_active_in_collector_subprocess`: roda
    `python -m src.collector --dry-run` com URL maliciosa interceptada
    em `monkeypatch`; verifica que `PermissionError` foi levantado
    OU que a chamada `requests.get` foi bloqueada.

- Criterios de aceitacao:
  - [ ] `pytest tests/unit/test_http_guard_bootstrap.py` passa (2 testes).
  - [ ] `pytest tests/integration/test_guardrails.py` passa (teste novo incluso).
  - [ ] Suites previas (`tests/unit/collector/`, `tests/integration/test_guardrails.py`)
    continuam passando.
  - [ ] `grep -L "install_http_guard" src/collector/__main__.py src/indexer/ingest.py src/query/__main__.py`
    retorna 0 (todos chamam o bootstrap).

### Task A.2 — Remover `"www.gov.br"` de `ALLOWED_DOMAINS` (resolver BLOQUEANTE B2 residual)

- Agent: Backend Engineer
- Input: nenhuma
- Decisao previa (documentar em `AGENTS.md` antes de iniciar):
  - Confirmar com humano se o portal SPED oficial em 2026 e
    `https://www.gov.br/sped/pt-br` (ja em `PORTAL_URLS:46`).
  - Se sim: substituir entrada em `allowed_domains.py` por
    `"sped.gov.br"` (host exato, sem `www.`) **OU** mover `SPED` para
    `https://www.gov.br/sped/pt-br` direto sem checagem de host
    (assume-se que o subpath e' canonico).
  - Se nao: voltar para `sped.rfb.gov.br`.

- Output (caso decisao = "manter SPED em gov.br"):
  - `.opencode/hooks/allowed_domains.py:30`: remover `"www.gov.br"`.
  - `.opencode/hooks/allowed_domains.py:23`: manter `"sped.rfb.gov.br"`
    ou trocar por `"sped.gov.br"` (decisao humana).
  - `src/collector/portal_index.py:46`: atualizar URL SPED para refletir
    o host novo (se houver).
  - `.env:34`: remover `www.gov.br` da lista.
  - `tests/unit/test_domain_guard.py`: ajustar testes que esperam
    `www.gov.br` (se houver). Adicionar teste
    `test_validate_url_rejects_www_gov_br_direct_url` (regressao):
    `validate_url("https://www.gov.br/sped/x")` retorna `False`
    (assumindo que `www.gov.br` foi removido).
  - Atualizar `.opencode/hooks/README.md` (se existir) explicando a
    politica anti-TLD formal.

- Criterios de aceitacao:
  - [ ] `grep "www.gov.br" .opencode/hooks/allowed_domains.py` retorna 0.
  - [ ] `pytest tests/unit/test_domain_guard.py` passa (teste novo incluso).
  - [ ] Suites previas continuam passando.

### Task A.3 — Aplicar guardrail no caminho `--dry-run` (`src/collector/__main__.py:62`)

- Agent: Backend Engineer
- Input: A.1 completa (bootstrap garante guard ativo)
- Output:
  - Confirmar que `_run_dry_run` em `src/collector/__main__.py:57-69`
    herda o guard instalado em A.1 (ja que o guard monkey-patcha
    `requests.Session.get` globalmente).
  - `tests/integration/test_guardrails.py` adicionar
    `test_dry_run_blocks_evil_url`: spy em `discover_documents` para
    retornar URL maliciosa; assert que `validate_url` filtra
    (comportamento ja' existe via `portal_index.py:174`, mas torna-se
    explicito em teste).

- Criterios de aceitacao:
  - [ ] `pytest tests/integration/test_guardrails.py` passa (teste novo incluso).

---

## Fase B — Alinhamento de documentacao (IMPORTANTE I1, I2, I4)

**Criterio**: `python -c "import yaml; yaml.safe_load(open('<file>').read().split('---')[1])"`
para todos os agent/skill/rule/hook nao levanta excecao, e `git grep "CONFAZ"`
em `SPEC.md` retorna 0 matches.

### Task B.1 — Remover CONFAZ de `SPEC.md` e `dfe-agent.md` (resolver IMPORTANTE I1)

- Agent: Prompt Engineer
- Input: decisao humana previa (formalizada em `AGENTS.md` "Decisoes resolvidas (Sprint 4)")
- Output:
  - `SPEC.md:17`: reescrever a frase de "Coleta automatica" sem mencionar CONFAZ
    (ex.: "...e legislacao correlata dos orgaos publicos habilitados").
  - `SPEC.md:80`: remover a linha `CONFAZ (legislacao) | https://www.confaz.fazenda.gov.br/legislacao`
    da tabela "Sites oficiais a monitorar".
  - `SPEC.md:71-79`: revisar as outras entradas (NF-e, NFC-e, CT-e, MDF-e, SPED)
    para garantir que estao alinhadas com `PORTAL_URLS` em
    `src/collector/portal_index.py:41-46`.
  - `.opencode/agent/dfe-agent.md:34`: substituir o exemplo
    `https://www.confaz.fazenda.gov.br/legislacao/convenio_123_2024`
    por um exemplo que use um dominio ainda ativo
    (ex.: `https://www.nfe.fazenda.gov.br/portal/principal.aspx`).
  - `.opencode/agent/dfe-agent.md:8`: remover "CONFAZ" do elenco de
    documentacao coberta (substituir por "legislacao fiscal eletronica
    oficial" generico).
  - `tests/unit/test_dfe_agent_definition.py`: verificar se ha assercao
    que dependa de "CONFAZ" no body. Se houver, ajustar.
  - Atualizar `AGENTS.md` linha 2 e linha 186 para remover CONFAZ dos
    enumerados.

- Criterios de aceitacao:
  - [ ] `grep -n "CONFAZ" SPEC.md` retorna 0.
  - [ ] `grep -n "CONFAZ\|confaz" .opencode/agent/dfe-agent.md` retorna 0.
  - [ ] `pytest tests/unit/test_dfe_agent_definition.py` passa.

### Task B.2 — Padronizar path da skill `dfe-fiscal` (resolver IMPORTANTE I2)

- Agent: Prompt Engineer
- Input: decisao humana previa (qual convencao o opencode CLI aceita)
- Output (opcao A — manter `dfe-fiscal/SKILL.md`):
  - `AGENTS.md:71`: atualizar estrutura de pastas para
    `skills/dfe-fiscal/SKILL.md`.
  - `AGENTS.md:159`: ajustar regra de nomenclatura para
    `kebab-case/SKILL.md para skills` (ou apenas citar SKILL.md).
  - `PLAN.md:244`: atualizar exemplo para o path real.
  - `PLAN_SPRINT2.md:250`: idem.
  - `.opencode/skills/README.md:2`: atualizar exemplo.
  - `.claude/rules/convencoes-gerais.md:7`: idem.
- Output (opcao B — mover para `dfe-fiscal.md`):
  - Mover `.opencode/skills/dfe-fiscal/SKILL.md` para
    `.opencode/skills/dfe-fiscal.md`.
  - Remover diretorio `.opencode/skills/dfe-fiscal/` se ficar vazio.
  - Validar com `opencode skill list` que `dfe-fiscal` continua
    descoberto.
- Teste novo em `tests/unit/test_dfe_fiscal_skill_definition.py`:
  - `test_skill_path_matches_opencode_discovery`: rodar `opencode
    skill list --json` (se disponivel) e verificar que `dfe-fiscal`
    aparece. Fallback: apenas verificar que o path documentado existe
    no disco.

- Criterios de aceitacao:
  - [ ] `pytest tests/unit/test_dfe_fiscal_skill_definition.py` passa (com teste novo).
  - [ ] `grep "skills/dfe-fiscal" AGENTS.md PLAN.md PLAN_SPRINT2.md .opencode/skills/README.md`
    retorna paths consistentes.

### Task B.3 — Adicionar frontmatter nas rules incondicionais (resolver IMPORTANTE I4)

- Agent: Prompt Engineer
- Input: nenhuma
- Output:
  - `.claude/rules/seguranca.md`: adicionar YAML frontmatter no topo:
    ```yaml
    ---
    name: seguranca
    description: Guardrails inviolaveis de seguranca aplicaveis a qualquer agent (segredos, anti-bot, guardrails, proveniencia do RAG, substituicao por replaces_doc_id).
    ---
    ```
  - `.claude/rules/convencoes-gerais.md`: adicionar frontmatter similar.
  - Documentar em `AGENTS.md` (secao "Convencoes gerais"): rules
    incondicionais (sem `paths:`) usam `name` + `description` simples;
    rules escopadas continuam usando `paths:` no frontmatter.

- Criterios de aceitacao:
  - [ ] Ambos arquivos comecam com `---\nname: ...\ndescription: ...\n---`.
  - [ ] `python -c "import yaml; yaml.safe_load(open('.claude/rules/seguranca.md').read().split('---')[1])"`
    nao levanta excecao.

---

## Fase C — Plugin TypeScript e event types (IMPORTANTE I5, PARCIAL P3)

**Criterio**: `.opencode/hooks/manifest.json` nao tem hook cujo `type` nao
seja despachado em `.opencode/plugin/agent-hooks.ts`. Plugin TS aparece
em `opencode.json > plugins`.

### Task C.1 — Registrar plugin TS em `opencode.json` (resolver PARCIAL P3)

- Agent: Prompt Engineer
- Input: nenhuma
- Output:
  - `opencode.json`: adicionar campo `plugin` (ou `plugins`) apontando
    para `.opencode/plugin/agent-hooks.ts`. Formato exato depende da
    schema do opencode CLI deste usuario; consultar docs em
    https://opencode.ai/config.json (campo `plugin` ou `plugins`).
  - Se o opencode CLI deste usuario nao suportar registro inline de
    plugins via JSON: registrar como decisao em `AGENTS.md`
    "Decisoes pendentes" e documentar como instalar via CLI
    (`opencode plugin add .opencode/plugin/agent-hooks.ts`).
  - Validar com `opencode agent list --verbose` que o plugin foi
    carregado (se o CLI oferecer tal flag).

- Criterios de aceitacao:
  - [ ] `opencode.json` contem referencia ao plugin TS.
  - [ ] `opencode run "..."` (modo dev) nao emite warning de plugin
    nao-carregado.

### Task C.2 — Alinhar event type `manifest.json:learning_stop` com handler do plugin (resolver IMPORTANTE I5)

- Agent: Backend Engineer + Prompt Engineer
- Input: C.1 completa (plugin carregado e' pre-requisito para verificar dispatch)
- Investigacao:
  - Consultar schema do opencode CLI para `event.type` validos em hooks
    (provavelmente `session.start`, `session.stop`, `session.idle`,
    `subagent.start`, `subagent.stop`, `subagent.end`).
  - Confirmar se `session_end` e' um valor valido ou se o correto e'
    `session.stop` / `session.idle`.
- Output:
  - Se `session_end` nao existe: trocar `.opencode/hooks/manifest.json:30`
    para `session.stop` ou `session.idle` (o que estiver consistente
    com `.opencode/plugin/agent-hooks.ts:266`).
  - Se `session_end` existe: estender `.opencode/plugin/agent-hooks.ts`
    para escutar `ev.type === "session_end"` alem de `session.stopped`
    e `session.idle` (linha 266).
  - Garantir que o dispatch realimenta o hook `learning_stop.py` com
    payload correto.
  - Teste novo em `tests/integration/test_learning_hooks_dispatch.py`
    (se nao existir): mockar `event` do opencode e verificar que o hook
    Python correto e' invocado.

- Criterios de aceitacao:
  - [ ] `manifest.json` declara tipos validos.
  - [ ] `agent-hooks.ts` despacha todos os tipos declarados.
  - [ ] `pytest tests/integration/test_learning_hooks_dispatch.py` (novo)
    passa.

---

## Fase D — Cobertura de testes (PARCIAL P1, P2)

**Criterio**: `pytest tests/unit/test_ragctl.py` cobre `cmd_reindex`;
`tests/fixtures/eval_set.json` nao contem URLs CONFAZ.

### Task D.1 — Cobertura de `cmd_reindex` em `test_ragctl.py` (resolver PARCIAL P1)

- Agent: QA Engineer
- Input: nenhuma
- Output:
  - `tests/unit/test_ragctl.py`: adicionar 3 testes:
    - `test_reindex_drops_vec_and_sidecars`: cria DB com 3 docs e 10
      chunks, chama `cmd_reindex`, verifica que `vec_chunks` foi dropado
      e `documents.status='nao_ingerido'` para docs com `file_path`.
    - `test_reindex_falha_se_db_inexistente`: assert exit 1 e mensagem
      clara em stderr.
    - `test_reindex_chunker_flag_propagado`: chama `cmd_reindex --chunker=structural`
      e verifica que o subprocess ingest foi invocado com a flag.
  - Usar `monkeypatch` em `subprocess.run` para nao rodar ingest real.

- Criterios de aceitacao:
  - [ ] `pytest tests/unit/test_ragctl.py` passa com 3 testes novos.
  - [ ] Cobertura de `src/ragctl.py:cmd_reindex` >= 95%.

### Task D.2 — Remover URL CONFAZ de `eval_set.json` (resolver PARCIAL P2, depende B.1)

- Agent: QA Engineer
- Input: B.1 completa (decisao sobre CONFAZ documentada)
- Output:
  - `tests/fixtures/eval_set.json`: substituir a pergunta sobre
    "Convenio ICMS 123/2024" (linha 8-11) por uma pergunta que use
    URL `https://www.nfe.fazenda.gov.br/...` ou similar (sem CONFAZ).
  - Se a CONFAZ URL precisar ficar como teste de "host nao presente
    no corpus": mover para `tests/unit/eval/test_offline_hosts.json`
    (fixture separada) e manter `eval_set.json` apenas com URLs reais.
  - Atualizar `tests/unit/test_eval_runner.py` se algum teste depender
    do CONFAZ host (improvavel, ja que runner usa match por hostname).

- Criterios de aceitacao:
  - [ ] `grep -i confaz tests/fixtures/eval_set.json` retorna 0.
  - [ ] `pytest tests/unit/test_eval_runner.py tests/unit/test_eval_ab.py` passa.

---

## Fase E — Polish opcional (SUGESTAO)

**Criterio**: items de polish implementados **OU** documentados como
"decisao pendente" em `AGENTS.md` se nao houver acao imediata.

### Task E.1 — Verificar `.claude/rag.db` nao versionado (SUGESTAO S1)

- Agent: Backend Engineer
- Output:
  - `git ls-files .claude/rag.db` deve retornar vazio.
  - Se retornar arquivo: `git rm --cached .claude/rag.db` e
    confirmar que `.gitignore:55` ja tem `.claude/rag.db*` (ja tem).
  - Limpar arquivos temporarios do disco:
    `.coverage.NTANDREWS.pid*.HNQIp837rWOh` (12 arquivos listados).

- Criterios de aceitacao:
  - [ ] `git ls-files .claude/rag.db` retorna vazio.
  - [ ] Diretorio raiz sem `.coverage.*` orfaos.

### Task E.2 — Validar `test_learning_hooks_idempotent.py` cobre os criterios E.3 (SUGESTAO S5)

- Agent: QA Engineer
- Output:
  - Reler `tests/integration/test_learning_hooks_idempotent.py` e
    verificar que cobre:
    - (a) 2 sessoes identicas nao duplicam entrada em `.claude/knowledge/`.
    - (b) 1 sessao resulta em exatamente 1 arquivo `.md` novo
      (verificado por contagem mtime).
  - Se algum item estiver descoberto: adicionar teste.

- Criterios de aceitacao:
  - [ ] Relatorio explicito: "E.3 (a) coberto por `test_X`" e
    "E.3 (b) coberto por `test_Y`".

### Task E.3 — README em `.claude/scripts/lib/` (SUGESTAO S2)

- Agent: Prompt Engineer
- Output:
  - Criar `.claude/scripts/lib/README.md` (1 pagina) explicando o
    proposito de cada modulo TS:
    - `db.ts`: wrapper better-sqlite3.
    - `chunker.ts`: sentence-aware chunker.
    - `embedder.ts`: wrapper @xenova/transformers.
    - `classifier.ts`: heuristica de categoria.

- Criterios de aceitacao:
  - [ ] Arquivo existe e tem pelo menos 1 secao por modulo.

---

## Fase F — Resiliencia do agente LLM ao embedding fail (IMPORTANTE I7, I8 + SUGESTAO S6)

**Criterio**: `python -m src.query "..."` com modelo de embedding
indisponivel imprime mensagem acionavel em stderr (sugere
`DFE_EMBEDDING_DTYPE=float16` OU modelo alternativo); o agente LLM
NAO gera scripts ad-hoc em `scripts/` ao receber `Nao encontrei base
para responder` espurio; `tests/unit/indexer/test_embedding_load_failure.py`
e `tests/unit/indexer/test_embedding_load_float16.py` passam.

**Origem do problema (achado da revisao de 2026-08-25):** os arquivos
`scripts/answer_nf_e_10_2026.py`, `scripts/buscar_dfereferenciado.py`,
`scripts/demo_query.py` e `scripts/demo_query_2026.py` foram gerados
pelo proprio agente LLM apos o CLI `python -m src.query` retornar
`NO_EVIDENCE_MESSAGE` em razao de `OSError 1455` (page file do Windows
insuficiente) no load do `paraphrase-multilingual-MiniLM-L12-v2`. O
agente interpretou o "sem evidencia" como "CLI quebrado" e escreveu
SQL raw no DB, contornando o guardrail de veracidade. O comentario no
proprio `answer_nf_e_10_2026.py:71-77` reconhece o anti-pattern mas
nao ha mecanismo automatizado para impedir a reincidencia.

### Task F.1 — Diagnosticar falha de load do embedding (resolver IMPORTANTE I7)

- Agent: Backend Engineer
- Input: nenhuma (independente de A-E)
- Output:
  - `src/indexer/embeddings.py:78-90` (`_load`): envolver a chamada
    `SentenceTransformer(self._model_name, **kwargs)` em
    `try/except (OSError, RuntimeError)`. Em caso de captura:
    1. Logar via `get_logger` com: `model_name`, dimensao do modelo,
       `low_cpu_mem_usage`, `dtype`, tipo e codigo da excecao,
       `DFE_EMBEDDING_DTYPE` e `DFE_EMBEDDING_MODEL` lidas do env.
    2. Re-levantar como `RuntimeError` com mensagem canonica contendo
       as substrings `"DFE_EMBEDDING_DTYPE=float16"` e
       `"DFE_EMBEDDING_MODEL=all-MiniLM-L6-v2"` (workarounds conhecidos).
  - `src/indexer/embeddings.py:44-46` (`DEFAULT_MODEL_NAME`): adicionar
    `DFE_EMBEDDING_DTYPE` na lista de env vars lidas no topo do modulo
    (mesmo padrao de `DFE_EMBEDDING_MODEL`). Constante nova:
    `DEFAULT_EMBEDDING_DTYPE: str = os.environ.get("DFE_EMBEDDING_DTYPE", "float32")`.
  - `src/indexer/embeddings.py:66-76` (`__init__`): default de `dtype`
    passa a ser `DEFAULT_EMBEDDING_DTYPE` em vez de literal `"float32"`.
    Documentar no docstring a nova env var.
  - `tests/unit/indexer/test_embedding_load_failure.py` (novo, 2 testes):
    - `test_load_oserror_1455_raises_runtimeerror_with_workaround`:
      monkeypatch `sentence_transformers.SentenceTransformer` para
      raise `OSError(1455, "page file too small")`; assert
      `RuntimeError` levantado com substring
      `"DFE_EMBEDDING_DTYPE=float16"`.
    - `test_load_other_oserror_passes_through_unmodified`:
      monkeypatch para raise `OSError(22, "Invalid argument")`; assert
      `OSError` original (nao envelopado) — evita mascarar bugs de
      filesystem.
  - `tests/unit/indexer/test_embedding_load_float16.py` (novo, 1 teste):
    - `test_env_var_dfe_embedding_dtype_overrides_default`:
      `monkeypatch.setenv("DFE_EMBEDDING_DTYPE", "float16")`;
      instancia `EmbeddingProvider()`; assert
      `embedder._dtype == "float16"` e que `DEFAULT_EMBEDDING_DTYPE`
      foi lido do env.

- Criterios de aceitacao:
  - [ ] `pytest tests/unit/indexer/test_embedding_load_failure.py`
    passa (2 testes novos).
  - [ ] `pytest tests/unit/indexer/test_embedding_load_float16.py`
    passa (1 teste novo).
  - [ ] `DFE_EMBEDDING_DTYPE` documentada no docstring de
    `EmbeddingProvider` (`grep -c "DFE_EMBEDDING_DTYPE"
    src/indexer/embeddings.py` >= 1).
  - [ ] Suites previas (`tests/unit/indexer/test_embeddings_robust.py`,
    `tests/unit/indexer/test_embeddings.py`) continuam passando.
  - [ ] Cobertura de `src/indexer/embeddings.py` mantida >= 95%.

### Task F.2 — Guardrail do agente LLM contra improvisacao SQL (resolver IMPORTANTE I8)

- Agent: Prompt Engineer
- Input: F.1 completa (env var `DFE_EMBEDDING_DTYPE` precisa existir no codigo
  antes de ser citada na skill).
- Decisao previa (ja' confirmada pelo humano em 2026-08-25): os 4 scripts
  ad-hoc serao **descartados** (nao preservados em `storage/demo/`),
  pois nao tem cobertura de teste e sao considerados artefatos descartaveis.
- Output:
  - `.opencode/skills/dfe-fiscal/SKILL.md`: nova secao "Diagnostico de
    `NO_EVIDENCE_MESSAGE` espurio" (apos a secao "Comandos invocaveis"):
    ```markdown
    ## Diagnostico de NO_EVIDENCE_MESSAGE espurio

    Se `python -m src.query "<pergunta>"` retornar
    `"answer": "Nao encontrei base para responder"` MAS o corpus
    possui documentos indexados (verificar com
    `python -m src.ragctl stats`), investigar nesta ordem:

    1. `python main.py --health` — confere se todos os modulos importam.
    2. `python -c "from src.indexer.embeddings import EmbeddingProvider;
        e = EmbeddingProvider(); print(e.dim)"` — dispara o load; se
       levantar `RuntimeError` com substring `DFE_EMBEDDING_DTYPE`,
       ver Task F.1.
    3. Workaround de ultimo recurso:
       `DFE_EMBEDDING_MODEL=all-MiniLM-L6-v2` (~80 MB, ingles-only —
       perde semantica em PT-BR).
    4. Hardening completo do ambiente:
       `pwsh scripts/check_env.ps1`.

    NUNCA escrever SQL raw em `scripts/` para "contornar" o RAG — isso
    viola o guardrail de veracidade. Usar sempre o CLI documentado.
    ```
  - `.claude/skills/dfe-agent-runner/SKILL.md`: Passo 4 (linhas 86-94)
    reescrever para chamar `python -m src.query` via `subprocess.run`
    em vez de instanciar `QueryEngine` diretamente. Justificativa: o
    CLI emite `NO_EVIDENCE_MESSAGE` canonico + exit codes previsiveis;
    a instanciação direta perde o fallback gracioso e a visibilidade
    do `OSError 1455` re-levantado por F.1.
  - Descarte dos scripts ad-hoc (executar nesta task):
    `Remove-Item scripts/answer_nf_e_10_2026.py,
    scripts/buscar_dfereferenciado.py, scripts/demo_query.py,
    scripts/demo_query_2026.py` (4 arquivos). `scripts/demo_cli.py`
    permanece (canonico, coberto por teste).
  - `.gitignore`: nova entrada
    `scripts/*.py` com whitelist `!scripts/demo_cli.py` para impedir
    que scripts ad-hoc futuros voltem a ser commitados por engano.
  - `tests/unit/test_scripts_whitelist.py` (novo, 1 teste):
    - `test_gitignore_blocks_adhoc_scripts`: le `.gitignore`; assert
      que `scripts/*.py` esta presente E `!scripts/demo_cli.py`
      tambem.
    - `test_scripts_dir_only_canonics`: lista `scripts/*.py`; assert
      que apenas `demo_cli.py` existe (sem ad-hoc residuais).

- Criterios de aceitacao:
  - [ ] `ls scripts/*.py` retorna apenas `demo_cli.py`.
  - [ ] `grep -c "NO_EVIDENCE_MESSAGE espurio"
    .opencode/skills/dfe-fiscal/SKILL.md` >= 1.
  - [ ] `pytest tests/unit/test_scripts_whitelist.py` passa.
  - [ ] `git grep "scripts/answer_nf_e_10_2026.py" .` retorna 0.

### Task F.3 — Script de hardening do ambiente Windows (resolver SUGESTAO S6)

- Agent: Prompt Engineer
- Input: F.1 completa (env var documentada no codigo).
- Output:
  - `.env.example`: apos a linha 28 (`DFE_EMBEDDING_MODEL=...`), adicionar:
    ```bash
    # Precisao numerica dos pesos do modelo de embedding.
    # Padrao: float32. Use float16 em Windows com page file limitado
    # (reduz ~50% o footprint com perda minima de precisao).
    DFE_EMBEDDING_DTYPE=float32
    ```
  - `AGENTS.md` (secao "Como rodar localmente"): apos o bloco "Backend /
    Skill (Python)", adicionar sub-secao "Variaveis de ambiente do
    embedding" com tabela:

    | Variavel | Default | Efeito |
    |---|---|---|
    | `DFE_EMBEDDING_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | Troca o modelo (ex.: `all-MiniLM-L6-v2` para ingles) |
    | `DFE_EMBEDDING_DTYPE` | `float32` | `float16` reduz ~50% o footprint em RAM/pagefile |

  - `scripts/check_env.ps1` (novo, escopo completo conforme decisao humana
    de 2026-08-25): script PowerShell que valida TUDO:

    1. **Memoria fisica**: `Get-CimInstance Win32_ComputerSystem |
       Select-Object TotalPhysicalMemory`. Emite WARNING se < 8 GB.
    2. **Page file**: `Get-CimInstance Win32_PageFileSetting` (ou
       `Win32_PageFileUsage`). Emite WARNING se `AllocatedBaseSize` <
       8192 MB; recomenda 16384 MB.
    3. **`python main.py --health`**: roda o smoke; exit code 0/1 com
       saida capturada.
    4. **Embedding load**:
       `python -c "from src.indexer.embeddings import EmbeddingProvider;
       EmbeddingProvider().dim"`. Exit code 0/1 com stderr capturado;
       se exit != 0, imprime sugestao de `DFE_EMBEDDING_DTYPE=float16`.
    5. **`storage/dfe.db` acessivel**: `Test-Path storage/dfe.db`;
       se FALSE, WARNING (base nao existe — `python -m src.ragctl
       migrate` resolve).
    6. **Saida**: JSON no stdout com shape
       `{memory_gb, pagefile_mb, health_ok, embedding_load_ok,
       db_accessible, recommendation}`.

    Script deve ser idempotente, sem efeitos colaterais (somente leitura
    via CIM/PowerShell + subprocess de `python --help` style invocations).
    Shebang `#!/usr/bin/env pwsh` no topo.
  - `tests/unit/test_check_env_script.py` (novo, 1 teste):
    - `test_check_env_script_artifact_exists_and_has_shebang`: le
      `scripts/check_env.ps1`; assert primeira linha comeca com
      `#!/usr/bin/env pwsh` OU termina com `.ps1`; assert tamanho
      >= 500 bytes (sanity check de conteudo real, nao placeholder).

- Criterios de aceitacao:
  - [ ] `.env.example` contem `DFE_EMBEDDING_DTYPE`.
  - [ ] `grep -c "DFE_EMBEDDING_DTYPE" AGENTS.md` >= 1.
  - [ ] `scripts/check_env.ps1` existe, tem sintaxe valida
    (`pwsh -NoProfile -Command "Test-Path scripts/check_env.ps1"`
    retorna `True`) e cobre os 5 escopos listados.
  - [ ] `pytest tests/unit/test_check_env_script.py` passa.
  - [ ] Suites previas continuam passando.

---

## Resumo de paralelismo e agents

### Tasks paralelas por fase

| Fase | Tasks em paralelo | Pico de paralelismo |
|------|-------------------|---------------------|
| A    | A.1 ‖ A.2 ‖ A.3 (A.3 depende de A.1) | 2 |
| B    | B.1 ‖ B.2 ‖ B.3 (todas independentes) | **3** |
| C    | C.1; depois C.2 (sequencial) | 1 |
| D    | D.1 ‖ D.2 (D.2 depende de B.1) | 2 |
| E    | E.1 ‖ E.2 ‖ E.3 | **3** |
| F    | F.1 ‖ F.2 ‖ F.3 (F.2 depende de F.1) | 2 |

**Pico absoluto**: 3 agents simultaneos (Fase B ou Fase E).

### Total de tasks e agents

- **Total de tasks**: 16 (3 + 3 + 2 + 2 + 3 + 3).
- **Papeis necessarios**:
  - **Backend Engineer** — A.1, A.2, A.3, C.2, E.1, F.1 (6 tasks, 37,5%).
  - **Prompt Engineer** — B.1, B.2, B.3, C.1, E.3, F.2, F.3 (7 tasks, 43,75%).
  - **QA Engineer** — D.1, D.2, E.2 (3 tasks, 18,75%).
  - **code-reviewer** — revisao final antes de marcar done (1 task recorrente).

### Criterios de aceitacao globais

- [ ] Todos os 16 checkboxes de fases marcados.
- [ ] `pytest tests/ --cov=src --cov-fail-under=80` exit 0 em CI limpo.
- [ ] 2 verificacoes manuais (uma por BLOQUEANTE) executadas e registradas.
- [ ] Verificacao manual de F.1 (mensagem de erro contem
  `DFE_EMBEDDING_DTYPE`) registrada no Apêndice A.
- [ ] `code-reviewer` re-convocado na conclusao emite relatorio final sem novos BLOQUEANTE.

---

## Apêndice A — Verificacao manual dos BLOQUEANTE

Comandos shell a serem executados **apos** todas as fases concluidas:

```bash
# BLOQUEANTE B1: guard HTTP instalado em runtime
python -c "
import sys
sys.path.insert(0, '.opencode/hooks')
import subprocess
r = subprocess.run([sys.executable, '-c', 'import requests; requests.get(\"https://evil.com/x\")'], capture_output=True, text=True)
print('stdout:', r.stdout)
print('stderr:', r.stderr)
print('rc:', r.returncode)
# esperado: PermissionError em stderr OU returncode != 0
"
# OU mais deterministico:
python -c "
from src.utils import http_guard
http_guard.install_http_guard()
import requests
try:
    requests.get('https://evil.com/x')
    print('FAIL: deveria ter levantado PermissionError')
except PermissionError as e:
    print('OK:', e)
"

# BLOQUEANTE B2: www.gov.br nao esta em ALLOWED_DOMAINS
grep "www.gov.br" .opencode/hooks/allowed_domains.py
# esperado: 0 matches
python -c "
import sys
sys.path.insert(0, '.opencode/hooks')
from allowed_domains import ALLOWED_DOMAINS
assert 'www.gov.br' not in ALLOWED_DOMAINS, 'www.gov.br ainda presente'
print('OK: www.gov.br removido')
"

# F.1 — mensagem acionavel quando o embedding load falha
python -c "
import sys
from unittest.mock import patch
with patch('sentence_transformers.SentenceTransformer',
           side_effect=OSError(1455, 'page file too small')):
    try:
        from src.indexer.embeddings import EmbeddingProvider
        EmbeddingProvider().dim
        print('FAIL: RuntimeError nao foi levantado')
        sys.exit(1)
    except RuntimeError as e:
        msg = str(e)
        assert 'DFE_EMBEDDING_DTYPE=float16' in msg, f'mensagem sem workaround: {msg}'
        print('OK: mensagem contem DFE_EMBEDDING_DTYPE=float16')
"
# esperado: 'OK: mensagem contem DFE_EMBEDDING_DTYPE=float16'
```

## Apêndice B — Riscos conhecidos e mitigacoes

| Risco | Probabilidade | Impacto | Mitigacao |
|-------|---------------|---------|-----------|
| A.1 quebra testes existentes que monkeypatcham `requests.get` | Media | Medio | Idempotencia de `install_http_guard` ja' documentada em `http_guard.py:108-114`; `uninstall_http_guard()` no teardown dos testes. |
| A.2 descobre que SPED nao tem host exato canonico | Alta | Baixo | Voltar para `sped.rfb.gov.br` (ja' na lista) e reverter URL em `portal_index.py:46`. |
| B.1 descobre ambiguidade em "legislacao fiscal eletronica oficial" sem CONFAZ | Baixa | Baixo | Listar dominios remanescentes explicitamente (NF-e, NFC-e, CT-e, MDF-e, SPED). |
| B.2 descobre que opencode CLI deste usuario nao aceita `dfe-fiscal/SKILL.md` nem `dfe-fiscal.md` | Baixa | Alto | Documentar em AGENTS.md como decisao pendente; skill pode ficar inativa ate decisao humana. |
| C.1 descobre que opencode CLI nao suporta `plugin` field em `opencode.json` | Media | Alto | Fallback: distribuir plugin via `opencode plugin install` CLI ou como patch externo. |
| D.2 descobre que nenhuma URL em `eval_set.json` bate com corpus real | Alta | Baixo | Modo defensivo de `run_benchmark` (ja' implementado em `src/eval/runner.py:210-218`) zera metricas sem falhar. |
| F.1 `try/except (OSError, RuntimeError)` em `_load` quebra import do `sentence-transformers` em versoes >= 4.50 onde `SentenceTransformer` levanta excecoes customizadas nao capturadas | Media | Medio | Scope do except limitado a `(OSError, RuntimeError)`; teste `test_load_other_oserror_passes_through_unmodified` protege contra mascaramento de erros de filesystem. |
| F.2 descarte dos scripts ad-hoc quebra git log de artefatos historicos uteis para debugging futuro | Baixa | Baixo | Decisao humana ja' tomada em 2026-08-25: artefatos sao descartaveis (sem cobertura de teste); o conhecimento do problema fica preservado no proprio PLAN_SPRINT5.md (Fase F origem) e no comentario do `answer_nf_e_10_2026.py:71-77` antes do descarte. |

## Apêndice C — Decisoes humanas pendentes

Itens que NAO podem ser resolvidos sem input humano antes de comecar a fase:

1. **A.2**: confirmar host canonico do SPED em 2026 (`sped.rfb.gov.br` vs `sped.gov.br` vs `www.gov.br/sped`).
2. **B.1**: confirmar se "legislacao do CONFAZ" deve sair do SPEC.md ou se a secao de "Funcionalidades essenciais" deve apenas remover a mencao (mantendo o espaco para futuro reativacao).
3. **B.2**: padrao de skill aceito pelo opencode CLI deste usuario (`kebab.md` vs `kebab/SKILL.md`).
4. **C.1**: campo correto em `opencode.json` para registrar plugins inline (`plugin` vs `plugins` vs nenhum).

**Decisoes humanas ja' resolvidas (2026-08-25):**
- **F.2 destino dos scripts ad-hoc**: **descartar** (sem cobertura de teste, considerados artefatos descartaveis). Nao mover para `storage/demo/`.

Recomendacao: resolver (1)-(4) antes de iniciar a execucao; caso contrario,
implementar tarefas com placeholders explicitos e documentar em AGENTS.md.

---

**Fim do PLAN_SPRINT5.md** — pronto para execucao apos aprovacao humana das
decisoes do Apendice C.
