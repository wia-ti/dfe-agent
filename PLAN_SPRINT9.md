# PLAN_SPRINT9.md

> Plano de hardening do agent `code-reviewer`: garantir cobertura de testes em todos os cenarios necessarios identificados pela auditoria do /feature. Origem: pedido do usuario via `/feature` com argumento "garanta que o agente @code-reviewer esta funcionando em todos os cenarios necessarios". Itens cobertos: **0 BLOQUEANTE** + **3 IMPORTANTE** + **0 PARCIAL** (3 total). Principio: **TDD** (teste vermelho primeiro), zero regressao nas suites existentes (503 passed / 1 skipped), cobertura >= 80%. NAO cria implementacao de producao nova — code-reviewer ja' funciona. A sprint adiciona **cobertura de testes** para os cenarios que estao descobertos.
>
> **Nota sobre TDD**: esta sprint cai na excecao canonica de `.opencode/command/feature.md:139-145` ("Mudanca de configuracao: nao ha teste vermelho. Validar com `python -c "import yaml; yaml.safe_load(...)"`"). Os 5 arquivos novos sao **somente de teste** (a "configuracao" testada e' a definicao/hook do code-reviewer, que ja' existe). Cada teste e' escrito como **documentacao executavel** do comportamento esperado; quando o teste falha, expõe regressao na config. A unica alteracao de config e' a adicao da secao "Bloqueio de escrita (hooks Python complementares)" em `.opencode/agents/code-reviewer.md`, documentada na Task A.1 (sem teste vermelho, validada por inspecao visual).

## Criterio global de conclusao

`pytest tests/ --cov=src --cov-fail-under=80 exit 0` **E** os 3 novos modulos de teste passam verdes (`tests/unit/test_code_reviewer_definition.py`, `tests/unit/hooks/test_code_reviewer_pre_tool_use.py`, `tests/unit/hooks/test_code_reviewer_pre_tool_use_bash.py`, `tests/integration/test_code_reviewer_plugin_dispatch.py`) **E** a Fase 4 do pipeline `/feature` continua invocando `subagent_type: code-reviewer` corretamente (verificavel por inspecao de `.opencode/command/feature.md:188`).

```
Fase A ──► Fase B ──► Fase C ──► Fase D
definicao  hooks     plugin     doc do
estrutural unit      dispatch   /feature
I9.1       I9.2+9.3  I9.4       (sanity)
```

**Dependencias criticas entre fases**:

- B (unit tests dos hooks) depende de A (definicao) apenas no sentido de contexto — podem rodar em paralelo.
- C (plugin dispatch) independe de A e B.
- D (sanity do `/feature`) depende de A (definicao existe e e' valida).
- Fase 4 do /feature (`code-reviewer` invocavel como subagent) depende dos 3 modulos de teste estarem verdes.

---

## Inventario dos cenarios onde o code-reviewer atua (auditoria)

| ID | Cenario | Componente atual | Cobertura atual | Gap |
|----|---------|------------------|------------------|-----|
| **C1** | Definicao estrutural (frontmatter YAML valido, `mode: subagent`, `permission.edit: deny`) | `.opencode/agents/code-reviewer.md` | **AUSENTE** — analogia `test_dfe_agent_definition.py` nao existe | Teste estrutural (Task A.1) |
| **C2** | Hook `pre_tool_use.py` bloqueia Write/Edit/MultiEdit/NotebookEdit | `.claude/hooks/code-reviewer/pre_tool_use.py` | Apenas 1 teste em `test_agent_dispatch.py:62` (so' Edit) | Cobertura unit por ferramenta + mensagem de bloqueio + log (Task B.1) |
| **C3** | Hook `pre_tool_use_bash.py` bloqueia 9 padroes destrutivos e permite 11 read-only | `.claude/hooks/code-reviewer/pre_tool_use_bash.py` | Apenas via `demo_agent_hooks.py` (manual) — sem pytest | Cobertura unit parametrizada de cada pattern (Task B.2) |
| **C4** | Plugin TS roteia code-reviewer (preToolUse + preToolUseBash) e NAO chama stop.py | `.opencode/plugin/agent-hooks.ts:42-46` | Parcial — `test_agent_hooks_plugin_loads.py` testa o plugin generico mas NAO o profile `code-reviewer` em especifico | Teste do map `AGENTS` + profile code-reviewer (Task C.1) |
| **C5** | `detectActiveAgent` retorna `code-reviewer` para `DFE_ACTIVE_AGENT=code-reviewer` | `.claude/hooks/_lib/payload.py:81` | Coberto em `test_agent_dispatch.py` | OK — sem gap |
| **C6** | `/feature` Fase 4 invoca `subagent_type: code-reviewer` | `.opencode/command/feature.md:188` | Coberto por inspecao manual no historico | Sanity check (Task D.1) |
| **C7** | `task: deny`, `skill: deny`, `todowrite: deny` no frontmatter | `.opencode/agents/code-reviewer.md:25-29` | **AUSENTE** | Task A.1 inclui checks |
| **C8** | Plugin NAO chama stop.py para code-reviewer (graceful no-op) | `.opencode/plugin/agent-hooks.ts:283-284` (if `!profile.stop` return) | **AUSENTE** | Task C.1 inclui check |

---

## Fase A — Teste estrutural da definicao do code-reviewer (IMPORTANTE I9.1)

**Criterio**: `pytest tests/unit/test_code_reviewer_definition.py -v exit 0` **E** todos os checks estruturais (YAML valido, mode, permission, body) sao exercitados.

### Task A.1 — Criar `tests/unit/test_code_reviewer_definition.py`

- Agent: Backend Engineer (escopo `tests/unit/` espelhado)
- Input:
  - `.opencode/agents/code-reviewer.md` (definicao canonica do agent em formato opencode CLI: `mode: subagent` + `permission: edit/task/skill/todowrite: deny`)
  - AGENTS.md > "Padroes de codigo > Tipagem em src/" (regra transversal)
  - AGENTS.md > "Decisoes resolvidas (Sprint 8)" > "opencode.json raiz tem campo plugin" (precedente de teste estrutural)
- Diagnostico:
  - Existe `tests/unit/test_dfe_agent_definition.py` validando `.opencode/agent/dfe-agent.md` (5 testes: file_exists, name, model, yaml_valid, body_strings).
  - Existe `.opencode/agents/code-reviewer.md` mas **sem teste estrutural correspondente**.
  - Um bug comum: esquecer `mode: subagent` faz o opencode nao expor o agent como subagent invocavel; esquecer `permission.edit: deny` remove a barreira principal de read-only.
  - Conforme `.claude/rules/convencoes-gerais.md > Frontmatter obrigatorio`: TODO agent/skill/rule DEVE ter YAML valido com `name` + `description`.
- Output:
  - Novo arquivo `tests/unit/test_code_reviewer_definition.py` contendo:
    - `test_agent_file_exists` — arquivo existe em `.opencode/agents/code-reviewer.md`.
    - `test_frontmatter_contains_name_code_reviewer` — regex `^name:\s*code-reviewer\s*$`.
    - `test_frontmatter_yaml_is_valid` — `yaml.safe_load(parts[1])` nao levanta.
    - `test_frontmatter_has_mode_subagent` — `^mode:\s*subagent\s*$` (pre-requisito para opencode expor como subagent).
    - `test_frontmatter_denies_edit` — `^permission:` seguido de `edit:\s*deny` (read-only).
    - `test_frontmatter_denies_task` — `permission.task: deny` (nao pode delegar).
    - `test_frontmatter_denies_skill` — `permission.skill: deny`.
    - `test_frontmatter_denies_todowrite` — `permission.todowrite: deny`.
    - `test_body_mentions_classification` — corpo contem `BLOQUEANTE`, `IMPORTANTE`, `SUGESTAO` (3-class classification canonica do code-reviewer).
    - `test_body_mentions_read_only` — corpo contem `read-only` (escopo da auditoria).
- Criterios de aceitacao:
  - [ ] Arquivo criado em `tests/unit/test_code_reviewer_definition.py`.
  - [ ] `pytest tests/unit/test_code_reviewer_definition.py -v` passa (verde).
  - [ ] Cobre os 7 gaps de C1+C7 acima.
  - [ ] Zero regressao: `pytest tests/unit/ exit 0` (todos os unit tests passam).

---

## Fase B — Cobertura unit dos hooks do code-reviewer (IMPORTANTE I9.2 + I9.3)

**Criterio**: `pytest tests/unit/hooks/test_code_reviewer_pre_tool_use.py tests/unit/hooks/test_code_reviewer_pre_tool_use_bash.py -v exit 0` **E** cada pattern BLOCK/ALLOW do `pre_tool_use_bash.py` tem pelo menos 1 teste parametrizado.

### Task B.1 — Criar `tests/unit/hooks/test_code_reviewer_pre_tool_use.py`

- Agent: Backend Engineer
- Input: `.claude/hooks/code-reviewer/pre_tool_use.py`
- Diagnostico:
  - O hook tem 4 write-tools no `_WRITE_TOOLS` (`Write`, `Edit`, `MultiEdit`, `NotebookEdit`).
  - Hoje so' `Edit` tem teste em `test_agent_dispatch.py:62` (subprocesso).
  - O hook le payload via `_read_payload_safe()` (fallback para `{}` se stdin nao disponivel) e usa `detect_active_agent(payload, hook_dir_name="code-reviewer")`.
  - Para teste unit, importa o modulo diretamente e chama `main()` passando payload via `monkeypatch.setattr(sys, "stdin", io.StringIO(payload))` OU usa `subprocess.run` como em `test_learning_helper.py::test_spawn_*`.
  - Estrategia recomendada: `subprocess.run` (consistente com `test_agent_dispatch.py`) para nao acoplar a detalhes internos de import.
- Output:
  - Novo arquivo `tests/unit/hooks/test_code_reviewer_pre_tool_use.py` com testes:
    - `test_blocks_write` — payload `Write` em `src/x.py` -> exit 2 + stderr `BLOQUEADO`.
    - `test_blocks_edit` — payload `Edit` em `src/x.py` -> exit 2.
    - `test_blocks_multi_edit` — payload `MultiEdit` em `src/x.py` -> exit 2.
    - `test_blocks_notebook_edit` — payload `NotebookEdit` em `notebook.ipynb` -> exit 2.
    - `test_allows_read` — payload `Read` -> exit 0, stderr vazio.
    - `test_allows_glob` — payload `Glob` -> exit 0.
    - `test_allows_grep` — payload `Grep` -> exit 0.
    - `test_allows_webfetch` — payload `WebFetch` -> exit 0.
    - `test_block_message_mentions_read_only` — confirmacao de UX (mensagem diz "read-only" para o agent saber o que aconteceu).
    - `test_log_written_on_block` — apos um BLOCK, `storage/agent_hooks.log` contem linha `[code-reviewer] [pre_tool_use_block_write]`.
- Criterios de aceitacao:
  - [ ] Arquivo criado.
  - [ ] 4 write-tools cobertos; 4+ read-tools cobertos; log verificado.
  - [ ] `pytest tests/unit/hooks/ -v exit 0`.

### Task B.2 — Criar `tests/unit/hooks/test_code_reviewer_pre_tool_use_bash.py`

- Agent: Backend Engineer
- Input: `.claude/hooks/code-reviewer/pre_tool_use_bash.py`
- Diagnostico:
  - 9 BLOCK patterns + 11 ALLOW patterns no arquivo.
  - Hoje so' tem demonstracao manual (`demo_agent_hooks.py`); sem pytest.
  - O design usa dois niveis: (a) BLOCK patterns sobrepoem ALLOW (sempre bloqueia); (b) ALLOW patterns: se nenhum bater, block generico.
  - Importante: o gate final (linhas 89-96) chama `block()` quando nenhum pattern ALLOW bate — entao comandos como `python -m src.collector` (BLOCK pattern) E `echo "oi"` (ALLOW) tem saidas distintas para distinguir.
- Output:
  - Novo arquivo `tests/unit/hooks/test_code_reviewer_pre_tool_use_bash.py` com testes:
    - **BLOCK (cada um parametrizado)**:
      - `test_blocks_redirection` — `echo x > file.txt`.
      - `test_blocks_sed_inplace` — `sed -i 's/a/b/' file`.
      - `test_blocks_rm` — `rm -rf build/`.
      - `test_blocks_git_commit` — `git commit -m x`.
      - `test_blocks_git_push` — `git push origin main`.
      - `test_blocks_pip_install` — `pip install foo`.
      - `test_blocks_collector` — `python -m src.collector --once`.
      - `test_blocks_indexer` — `python -m src.indexer.ingest`.
      - `test_blocks_ragctl` — `python -m src.ragctl migrate`.
      - `test_blocks_db_path` — payload `tool_input.command = "sqlite3 storage/dfe.db"` (pattern sqlite path).
    - **ALLOW (cada um parametrizado)**:
      - `test_allows_ls` — `ls -la`.
      - `test_allows_cat` — `cat README.md`.
      - `test_allows_head_tail` — `head -n 5 file.txt`.
      - `test_allows_wc_find_rg_grep` — 4 sub-testes.
      - `test_allows_pytest_collect_only` — `pytest --collect-only -q`.
      - `test_allows_git_log_diff_show` — 3 sub-testes.
      - `test_allows_python_c` — `python -c "import x"`.
      - `test_allows_echo_no_redirect` — `echo "hello"`.
    - **Edge cases**:
      - `test_blocks_unknown_command` — `foo --bar` (gate final).
      - `test_allows_empty_command` — payload com `command: ""` -> exit 0.
- Criterios de aceitacao:
  - [ ] Arquivo criado.
  - [ ] Todos os 9 BLOCK patterns + 11 ALLOW patterns cobertos via parametrize quando aplicavel.
  - [ ] `pytest tests/unit/hooks/ -v exit 0`.

---

## Fase C — Integracao do plugin TS com code-reviewer (IMPORTANTE I9.4)

**Criterio**: `pytest tests/integration/test_code_reviewer_plugin_dispatch.py -v exit 0` **E** todos os pontos do map `AGENTS` para `code-reviewer` estao cobertos.

### Task C.1 — Criar `tests/integration/test_code_reviewer_plugin_dispatch.py`

- Agent: Backend Engineer
- Input:
  - `.opencode/plugin/agent-hooks.ts:42-46` (profile `code-reviewer`)
  - `.claude/agents/code-reviewer.md:62-63` (documentacao dos hooks)
- Diagnostico:
  - `test_agent_hooks_plugin_loads.py` valida o plugin generico (compila, default export, opencode.json, writes_per_session).
  - **Nenhum teste** valida o conteudo do map `AGENTS` para o slug `code-reviewer` em particular — risco silencioso se o slug for renomeado ou o profile for quebrado.
  - O profile correto (lido de `agent-hooks.ts:42-46`): `slug: "code-reviewer"`, `preToolUse: ".claude/hooks/code-reviewer/pre_tool_use.py"`, `preToolUseBash: ".claude/hooks/code-reviewer/pre_tool_use_bash.py"`. **SEM** `postToolUse`, **SEM** `stop`.
  - O if em `:284` (`if (!profile || !profile.stop) return;`) garante que code-reviewer sai sem chamar stop — mas isso nao tem teste.
- Output:
  - Novo arquivo `tests/integration/test_code_reviewer_plugin_dispatch.py` com testes (validacao textual do fonte TS + comportamento do helper JS):
    - `test_agent_map_contains_code_reviewer` — regex em `agent-hooks.ts` confirma entrada `"code-reviewer"` no map `AGENTS`.
    - `test_code_reviewer_profile_has_pre_tool_use` — confirma `preToolUse: ".claude/hooks/code-reviewer/pre_tool_use.py"` no profile.
    - `test_code_reviewer_profile_has_pre_tool_use_bash` — confirma `preToolUseBash`.
    - `test_code_reviewer_profile_has_no_post_tool_use` — confirma AUSENCIA de `postToolUse:` no profile code-reviewer.
    - `test_code_reviewer_profile_has_no_stop` — confirma AUSENCIA de `stop:` no profile code-reviewer.
    - `test_plugin_skips_stop_event_for_code_reviewer` — importa o modulo via `tsx -e` e invoca `event` callback com `type: "session.stopped"`, slug code-reviewer; confirma que NAO ha spawn de subprocesso (`runPython` nao foi chamado). Pode-se mockar `runPython` via injecao de spy em tsx.
    - `test_detect_agent_returns_code_reviewer_with_env_var` — replica da logica JS em Python: dado `DFE_ACTIVE_AGENT=code-reviewer`, `detectAgentFromSession` retorna `code-reviewer` (isto ja' esta' parcialmente coberto em `test_agent_dispatch.py:32-56`, mas para o plugin TS em si nao).
- Criterios de aceitacao:
  - [ ] Arquivo criado.
  - [ ] 7 testes cobrindo map, profile, ausencia de post/stop, e runtime do `event` callback.
  - [ ] `pytest tests/integration/ -v exit 0`.

---

## Fase D — Sanity do `/feature` Fase 4 (cobertura nao-regressiva)

**Criterio**: `python -c "import re; src = open('.opencode/command/feature.md', encoding='utf-8').read(); assert 'subagent_type: code-reviewer' in src"` retorna 0.

### Task D.1 — Validar referencia canonica no comando `/feature`

- Agent: Backend Engineer (validacao textual)
- Input: `.opencode/command/feature.md:188`
- Diagnostico:
  - O comando `/feature` Fase 4 dispara o code-reviewer via `task` tool com `subagent_type: code-reviewer` e referencia o template em `.opencode/agents/code-reviewer.md` (linha 202).
  - Esta e' a unica ponte canonica que dispara code-reviewer dentro do pipeline do projeto. Se a string mudar, o code-reviewer para de ser invocado.
  - Nao ha teste automatizado desta invariante.
- Output:
  - Adicionar 2 testes em `tests/unit/test_dfe_agent_definition.py`-style: criar `tests/unit/test_feature_pipeline_phase4.py` (apesar de unit, este teste so' le doc) OU adicionar a `tests/integration/test_feature_phase4_invokes_code_reviewer.py`.
  - Decisao: integrar em `tests/integration/test_code_reviewer_plugin_dispatch.py` (Fase C) como teste adicional, evitando proliferacao de arquivos. Renomear arquivo depois se necessario.
- Criterios de aceitacao:
  - [ ] 2 testes adicionados a `tests/integration/test_code_reviewer_plugin_dispatch.py`:
    - `test_feature_command_phase4_references_code_reviewer` — confirma `subagent_type: code-reviewer` em `feature.md`.
    - `test_feature_command_phase4_references_agent_definition` — confirma `.opencode/agents/code-reviewer.md` em `feature.md`.

---

## Apêndice A — Riscos

| Risco | Probabilidade | Impacto | Mitigacao |
|-------|---------------|---------|-----------|
| Testes do hook usam `subprocess.run` e quebram em ambientes sem `python` no PATH | Baixa | Medio | Ja' mitigado por `sys.executable` (mesmo Python do pytest) — padrao de `test_agent_dispatch.py` |
| Plugin TS nao carrega por mudanca em `tsx`/versao Node | Baixa | Alto | Reaproveitar logica de `test_agent_hooks_plugin_loads.py:38` (ja' cobre) |
| `agent-hooks.ts` ser refatorado e o map `AGENTS` mudar de nome | Media | Alto | Teste de Fase C protege por regex no source; se quebrar intencionalmente, atualizar o teste |
| Tese de duplicacao: `.opencode/agents/code-reviewer.md` vs `.claude/agents/code-reviewer.md` | Media | Baixo | **Fora de escopo desta sprint** — documentado em Sprint 8 mas nao resolvido. Marcar como follow-up. |
| Cobertura de testes de hooks adicionados nao conta para o gate `--cov=src` (são testes, não src/) | Alta | Baixo | OK — gate cobre `src/`, nao `tests/` |

## Apêndice B — Fora de escopo

- Consolidação de `.opencode/agents/code-reviewer.md` e `.claude/agents/code-reviewer.md` em um unico arquivo canonico (decisao de design maior — possivel Sprint 10+).
- Adicionar logica de **policy enforcement** alem de hooks (ex.: `linter` no CI que falha se `code-reviewer` agent tiver `edit` no frontmatter).
- Adicionar testes E2E reais invocando `opencode run "@code-reviewer foo"` (depende de CLI disponivel no ambiente).
- Cobertura de testes para `ml-engineer`, `prompt-engineer`, `qa-engineer` (escopo analogo — potencial Sprint 10+).
- Renovacao automatica do `.claude/knowledge/` via RAG meta-cognitivo ao fim desta sprint (Fase 6 cobre via `--file`).

## Apêndice C — Comandos shell para reproduzir a sprint manualmente

```bash
# Setup
cd "C:\Users\Andrews\Workspace\Projetos\# Pessoal\DFe-Agent"
.venv\Scripts\python.exe -m pytest tests/ -q --no-header

# Fase A
.venv\Scripts\python.exe -m pytest tests/unit/test_code_reviewer_definition.py -v

# Fase B
.venv\Scripts\python.exe -m pytest tests/unit/hooks/test_code_reviewer_pre_tool_use.py -v
.venv\Scripts\python.exe -m pytest tests/unit/hooks/test_code_reviewer_pre_tool_use_bash.py -v

# Fase C + D
.venv\Scripts\python.exe -m pytest tests/integration/test_code_reviewer_plugin_dispatch.py -v

# Gate final
.venv\Scripts\python.exe -m pytest tests/ --cov=src --cov-fail-under=80 -q
```
