# PLAN_SPRINT11.md

> Plano de **consolidação do harness** `.claude/` + `.opencode/`: remove
> agents/hooks legacy, fecha shadow contracts do `manifest.json`,
> corrige bugs latentes do RAG meta-cognitivo e do `.gitignore`.
> Origem: auditoria read-only em 2026-08-26 ("verifique a pasta `.claude`
> e `.opencode` e me alerte sobre possíveis redundâncias e bugs").
> 5 BLOQUEANTE + 2 IMPORTANTE. TDD, suite verde ~599+ passed,
> cobertura >= 80%.

## Critério global de conclusão

`pytest tests/ --cov=src --cov-fail-under=80` retorna exit code 0 **E**
`opencode agent list` lista apenas `dfe-agent`, `dev`, `code-reviewer`
**E** o `_lib/learning.py::PROJECT_ROOT` resolve para o DFe-Agent root
(não para `.claude/`) **E** `git check-ignore .opencode/node_modules`
retorna exit 0 (ou `grep` no `.gitignore` casa com a regra) **E** o
`.claude/.claude/` não existe (gate anti-regressão).

```
Fase A ──► Fase B ──► Fase C ──► Fase D ──► Fase E ──► Fase F
fix       remove     mover       docs +
learning  legacy     code-rev    gitignore
.py:37    hooks + 3  singular    cleanup
BLOQ.     manifest   BLOQ.       IMP.
BLOQ.     BLOQ.
```

**Dependências críticas entre fases**:
- B (remover manifest + learning_*.py órfãos) depende de A (fix
  `learning.py`) — sem o fix, a remoção deixa `_lib/learning.py` órfão.
- C (consolidação legacy) depende de A e B — remove dependências que
  podem ser reativadas pelos hooks legacy.
- D (mover code-reviewer + corrigir `model:`) independente de A-C.
- E (`.gitignore` para `.opencode/node_modules/`) independente.
- F (docs/housekeeping) depende de A-E.

## Resumo dos problemas observados

| ID | Sintoma | Causa raiz |
|----|---------|------------|
| **B11.1** | `.claude/.claude/knowledge/_pending-*.md` (6 arq) e `.claude/storage/agent_hooks.log` (431 linhas) — artefatos em paths errados | `_lib/learning.py:37` calcula `PROJECT_ROOT = parents[2]` (=`.claude/`) em vez de `parents[3]` (=DFe-Agent). Tests monkeypatcham `PROJECT_ROOT`, então CI não detecta. |
| **B11.2** | `manifest.json` (37 linhas) + 3 scripts `learning_*.py` (~530 LoC) são "letra morta" mas testados como se fossem runtime | opencode não suporta nativamente `pre_request`/`subagent_end`/`session.stopped`; plugin TS `agent-hooks.ts` tem seu próprio dispatch hardcoded. Documentado em PLAN_SPRINT5 C.1 e PLAN_SPRINT8 B8.3 mas nunca removido. |
| **B11.3** | `src/utils/manifest_loader.py` (59 LoC) tem zero consumidores em `src/` — só tests | Consequência de B11.2. Código morto, mas testes (6+) defendem a "fonte da verdade dos hooks" que não existe. |
| **B11.4** | `.opencode/node_modules/` (55 MB, 3938 arquivos) não está no `.gitignore`; `.opencode/package-lock.json` também não | `.gitignore:82-85` exclui `.claude/node_modules/` e `node_modules/` raiz, mas não `.opencode/node_modules/`. Latente até inicializar git repo. |
| **B11.5** | `.opencode/agents/code-reviewer.md:5` tem `model: MiniMax-M3` sem prefixo de provider; quebra Task tool `subagent_type="code-reviewer"` (sintoma: `Model not found: MiniMax-M3/.`) | Path errado (`.opencode/agents/` plural vs `.opencode/agent/` singular canônico) + inconsistência do `model:` (Sprint 9 follow-up não fechado). |
| **I11.1** | `.opencode/agents/` (plural) tem só `code-reviewer.md` órfão; resto do projeto usa `.opencode/agent/` (singular) | Drift acumulado entre Sprints 4-9 (legado Claude Code) e Sprint 10 (canônico opencode CLI). |
| **I11.2** | 4 agents legacy (`backend/ml/prompt/qa-engineer`) + 4 hooks Python (~625 LoC duplicadas) ainda roteados pelo plugin TS | Sprint 10 fechou a interface (`/feature`/`/bug`/`/duvida` → `agent: dev`), mas o `AGENTS` map em `agent-hooks.ts:42-76` ainda inclui os 4 slugs. |

---

## Fase A — Fix `learning.py` PROJECT_ROOT + limpeza de artefatos (B11.1, BLOQUEANTE)

**Critério**: `learning.PROJECT_ROOT` resolve para o DFe-Agent root;
suíte completa verde; novo gate em `test_learning_path_safety.py`
detecta criação futura de `.claude/.claude/`.

### Task A.1 — Corrigir `_lib/learning.py:37` (off-by-one)

- Agent: `@dev` (escopo `.claude/hooks/_lib/`)
- Diagnóstico:
  - `_lib/payload.py:31` usa `parents[3]` (correto: DFe-Agent root)
  - `_lib/learning.py:37` usa `parents[2]` (BUG: vira `.claude/`)
  - Consequência: `_knowledge_dir()` retorna `.claude/.claude/knowledge/`
    e `LOG_PATH` retorna `.claude/storage/agent_hooks.log`
  - Tests monkeypatcham `PROJECT_ROOT` em
    `tests/integration/test_learning_stop_hook.py` (9 sites) e
    `test_learning_hooks_idempotent.py` (5 sites), então bug não
    aparece em CI.
- Mudança: trocar `parents[2]` por `parents[3]` em `learning.py:37`.
- Cobertura nova (TDD vermelho primeiro):
  - `tests/unit/hooks/test_learning_helper.py::test_project_root_resolves_to_dfe_agent_root`
    — confirma via sentinel de path (ex.: assert
    `learning.PROJECT_ROOT.name == "DFe-Agent"`).
- Critérios de aceitação:
  - [ ] Teste novo verde.
  - [ ] Sem regressão nos 9 sites de monkeypatch existentes
        (suite continua passando com `tmp_path`).

### Task A.2 — Limpar artefatos de runs anteriores em paths errados

- Operação manual (após A.1 commit):
  - Remover `.claude/.claude/` (diretório aninhado, recriado pelo bug).
  - Remover `.claude/storage/agent_hooks.log` (431 linhas, legado pre-Sprint 8).
  - Remover `.claude/.cache/hook-smoke/` (fixtures de smoke test).
- Adicionar `tests/integration/test_learning_path_safety.py` (novo):
  - `test_knowledge_dir_is_canonical`: confirma `_knowledge_dir()` ==
    `<PROJECT_ROOT>/.claude/knowledge` (não `.claude/.claude/knowledge`).
  - `test_log_path_is_storage_root`: confirma `LOG_PATH` ==
    `<PROJECT_ROOT>/storage/agent_hooks.log` (não
    `.claude/storage/agent_hooks.log`).
  - Gate CI: suite falha se voltar a criar `.claude/.claude/`.
- Critérios de aceitação:
  - [ ] `.claude/.claude/` removido.
  - [ ] `.claude/storage/agent_hooks.log` removido.
  - [ ] `.claude/.cache/hook-smoke/` removido.
  - [ ] `test_learning_path_safety.py` verde.

---

## Fase B — Apagar `manifest.json` + 3 `learning_*.py` órfãos (B11.2 + B11.3, BLOQUEANTE)

**Critério**: `.opencode/hooks/manifest.json` removido; os 3 scripts
`learning_*.py` órfãos removidos; `src/utils/manifest_loader.py`
removido; testes correspondentes reescritos/removidos; suite verde.

### Task B.1 — Apagar `manifest.json` e 3 scripts Python órfãos

- Remover:
  - `.opencode/hooks/manifest.json` (37 linhas)
  - `.opencode/hooks/learning_prompt_submit.py` (171 linhas)
  - `.opencode/hooks/learning_subagent_stop.py`
  - `.opencode/hooks/learning_stop.py`
- Atualizar referências documentais:
  - `.claude/README.md:146` ("Todos estao registrados em
    `.opencode/hooks/manifest.json`") — reescrever.
  - `.claude/rules/seguranca.md:17` ("Nunca edite
    `.opencode/hooks/manifest.json`") — reescrever.
  - AGENTS.md `> Sistema de RAG meta-cognitivo (.claude/)` — remover
    setas "manifest" e o trecho "Hooks (opencode) wrappers Python
    que disparam os scripts TS via subprocess".
- Manter `.opencode/hooks/domain_guard.py` (módulo Python vivo, usado
  por `src/utils/http_guard.py`); remover apenas o bloco
  `if __name__ == "__main__":` (CLI morto, era disparado pelo manifest).
- Critérios de aceitação:
  - [ ] 4 arquivos removidos do disco.
  - [ ] Documentação não menciona mais o manifest nem os 3 scripts.
  - [ ] Suite verde (após reescrita dos testes em C.4).

### Task B.2 — Apagar `src/utils/manifest_loader.py`

- 59 linhas, zero consumidores em `src/` (só tests).
- `grep -r "load_manifest" src/` retorna apenas a própria definição
  da função — confirmar antes da remoção.
- Remover `src/utils/manifest_loader.py`.
- Remover testes dependentes:
  - `tests/integration/test_domain_guard_plugin.py::test_manifest_loads_and_registers_domain_guard`
  - `tests/integration/test_domain_guard_plugin.py::test_manifest_loader_warns_when_missing`
- Manter:
  - `tests/integration/test_domain_guard_plugin.py::test_http_guard_blocks_evil_url`
  - `test_http_guard_allows_nfe_url`
  - `test_safe_session_get_does_not_recurse`
  - `test_safe_get_does_not_recurse`
  - `test_src_has_no_direct_domain_guard_import`
- Critérios de aceitação:
  - [ ] `src/utils/manifest_loader.py` removido.
  - [ ] `tests/integration/test_domain_guard_plugin.py` reduzido.

---

## Fase C — Consolidação de harness: remover 4 agents/hooks legacy (I11.2, BLOQUEANTE)

**Critério**: `.claude/agents/{backend,ml,prompt,qa}-engineer.md`
removidos; `.claude/hooks/{backend,ml,prompt,qa}-engineer/`
removidos; plugin TS `AGENTS` map reduzido de 6 para 2; testes
reescritos; suite verde; gate anti-regressão em `test_no_legacy_agents.py`.

### Task C.1 — Remover 4 agents legacy de `.claude/agents/`

- Remover:
  - `.claude/agents/backend-engineer.md` (102 linhas)
  - `.claude/agents/ml-engineer.md`
  - `.claude/agents/prompt-engineer.md`
  - `.claude/agents/qa-engineer.md`
- Manter: `.claude/agents/dev.md` (canônico) e
  `.claude/agents/code-reviewer.md` (read-only).

### Task C.2 — Remover 4 hooks Python legacy de `.claude/hooks/`

- Remover diretórios inteiros (e seus `__pycache__/`):
  - `.claude/hooks/backend-engineer/` (pre_tool_use.py + post_tool_use.py + stop.py)
  - `.claude/hooks/ml-engineer/`
  - `.claude/hooks/prompt-engineer/`
  - `.claude/hooks/qa-engineer/` (pre_tool_use.py apenas)
- Total: ~625 linhas de código hook Python.
- Manter: `.claude/hooks/dev/` (canônico) e `.claude/hooks/code-reviewer/`
  (read-only, ainda usado).
- Atualizar `.claude/hooks/_lib/payload.py`:
  - `_AGENT_HINTS` (linhas 46-52): remover entradas `backend-engineer`,
    `ml-engineer`, `prompt-engineer`, `qa-engineer`. Manter apenas
    `code-reviewer` e `dev`.
- Atualizar `.claude/hooks/_lib/test_runner.py`:
  - `suites_for_path` (linhas 60-65): branch
    `elif agent == "backend-engineer":` vira morto; o fallback
    `_ML_SUITES` (linha 65) também fica morto (só `dev` restou).
    Manter apenas o branch `dev` e adicionar fallback para suite vazia
    (em vez de cair em `_ML_SUITES`).

### Task C.3 — Atualizar `.opencode/plugin/agent-hooks.ts`

- Map `AGENTS` (linhas 42-76): remover entradas `backend-engineer`,
  `ml-engineer`, `prompt-engineer`, `qa-engineer`.
- Sobrem apenas: `code-reviewer` (read-only) e `dev` (canônico).
- `RECOGNIZED_AGENT_SLUGS` (linhas 181-188): remover slugs legacy.
- `detectAgentFromSession` (linhas 144-176): o scan argv + heurística
  sobre sessionID pode ser simplificado — agora só 2 slugs válidos.
  Manter a estrutura, atualizar comentários.

### Task C.4 — Atualizar testes afetados

- `tests/integration/test_learning_stop_hook.py`: hoje cobre 3 hooks
  legacy (backend/ml/prompt) com ~9 testes parametrizados. Reescrever
  mantendo apenas:
  - `test_dev_stop_pytest_passes`
  - `test_dev_stop_blocks_when_pytest_fails`
  - `test_dev_stop_summarize_skipped_when_no_edits`
  - `test_dev_stop_summarize_spawned_when_edits_present`
  - `test_dev_stop_idempotent_across_sessions`
- `tests/integration/test_learning_hooks_idempotent.py`: cobre
  `_pending_marker_path` em scripts `.opencode/hooks/learning_*.py`
  órfãos. Reescrever contra `.claude/hooks/_lib/learning.py` (helper
  canônico) usando o mesmo padrão de marker composto
  `(agent_slug, session_id)`.
- `tests/integration/test_learning_hooks_dispatch.py`: **remover**.
  Testa manifest que foi apagado em B.1. A lógica coberta (event types)
  já migrou para `test_dev_plugin_dispatch.py` (Sprint 10).
- `tests/unit/hooks/test_code_reviewer_pre_tool_use.py:88`: parametrize
  itera sobre 5 agents. Reduzir para 2 (`code-reviewer`, `dev`).
- `tests/unit/hooks/test_payload.py:56`: teste verifica fallback para
  `hook_dir_name="backend-engineer"`. Substituir pelo slug canônico
  `dev` (já que `_AGENT_HINTS` foi limpo em C.2).
- `tests/unit/hooks/test_test_runner.py`: hoje cobre `backend-engineer`
  e `ml-engineer`. Substituir por testes para `dev` (retorna união
  das 2 tabelas: `_BACKEND_SUITES ∪ _ML_SUITES`).

### Task C.5 — Cobertura nova (gate "agent legacy não volta")

- `tests/integration/test_no_legacy_agents.py` (novo):
  - `test_no_legacy_agent_md_files`: lista `.claude/agents/*.md` e
    confirma que só `dev.md` e `code-reviewer.md` existem.
  - `test_no_legacy_hook_directories`: lista `.claude/hooks/*/`
    (excluindo `_lib/`, `dev/`, `code-reviewer/`) e confirma vazio.
  - `test_plugin_ts_only_routes_to_canonical_agents`: parseia
    `agent-hooks.ts` via regex e confirma que `AGENTS` tem apenas
    `code-reviewer` e `dev`.
  - `test_AGENT_HINTS_in_payload_has_no_legacy`: parseia
    `_lib/payload.py` e confirma que `_AGENT_HINTS` foi reduzido a
    `code-reviewer` e `dev`.
  - `test_test_runner_no_legacy_agent_branches`: confirma que
    `suites_for_path` não tem mais branch para `backend-engineer` ou
    `ml-engineer`.

### Task C.6 — Remover scripts ad-hoc legados (SUGESTAO S1)

- `.claude/scripts/test_hooks.py` (130 linhas) e
  `.claude/scripts/demo_agent_hooks.py` (140 linhas) ficam em
  `.claude/scripts/` junto com os `*.ts` canônicos, mas são Python
  de smoke (não cobertos por teste próprio).
- Decisão: mover para `scripts/` raiz (junto de `demo_cli.py`,
  canônico) ou remover. Recomenda-se mover para `scripts/` raiz
  com sufixo `_smoke_legacy.py` para histórico.
- Critérios de aceitação:
  - [ ] Decisão registrada em AGENTS.md > Decisões resolvidas (Sprint 11).

---

## Fase D — Mover `code-reviewer.md` para path canônico + corrigir `model:` (B11.5 + I11.1, BLOQUEANTE)

**Critério**: `.opencode/agent/code-reviewer.md` existe com frontmatter
`model: PROVIDER/MiniMax-M3`; `.opencode/agents/` removido;
referências em `.claude/agents/{dev,code-reviewer}.md` atualizadas;
test `test_frontmatter_has_model_with_provider` verde.

### Task D.1 — Mover `.opencode/agents/code-reviewer.md` → `.opencode/agent/code-reviewer.md`

- Operação: `Move-Item .opencode\agents\code-reviewer.md .opencode\agent\code-reviewer.md`
- Após mover, diretório `.opencode/agents/` fica vazio. Remover diretório.

### Task D.2 — Adicionar prefixo `PROVIDER/` no frontmatter

- Editar `.opencode/agent/code-reviewer.md:5`: trocar
  `model: MiniMax-M3` por `model: PROVIDER/MiniMax-M3` (consistente
  com `dev.md:5` e `dfe-agent.md:3`).
- Atualizar teste `tests/unit/test_code_reviewer_definition.py`:
  adicionar `test_frontmatter_has_model_with_provider` (Sprint 9
  follow-up explícito). Padrão regex: `^model:\s+\S+/\S+$`.

### Task D.3 — Atualizar referências documentais

- `.claude/agents/code-reviewer.md:105` (corpo do agent): referência
  `.opencode/agents/code-reviewer.md` → atualizar para
  `.opencode/agent/code-reviewer.md`.
- `.claude/agents/dev.md:105`: mesma referência — atualizar.
- AGENTS.md: buscar `code-reviewer` + `.opencode/agents` e ajustar.
- `.opencode/agents/README.md` (se existir): remover ou renomear para
  `.opencode/agent/README.md`.

### Task D.4 — Remover regra 3 contraditória (resolução IMPORTANTE I.5)

- `.opencode/rules/dfe-rules.md:9` regra 3 ("Sempre executar
  `python -m src.collector --once` antes de formular qualquer
  resposta") colide com `dev/pre_tool_use.py:79-90` (gate que
  bloqueia exatamente isso, exceto `--diagnose-net`).
- `.opencode/agent/dfe-agent.md:13` reproduz a mesma regra.
- Remover ambas as ocorrências. Skill `dfe-fiscal/SKILL.md` já
  documenta o Passo 2 (coletor) e continua como fonte canônica do
  fluxo.
- Critérios de aceitação:
  - [ ] `dfe-rules.md` tem 4 regras (era 5).
  - [ ] `dfe-agent.md` não menciona mais o collector automático.

---

## Fase E — `.gitignore`: cobrir `.opencode/node_modules/` (B11.4, BLOQUEANTE)

**Critério**: `.opencode/node_modules/` listado em `.gitignore`;
teste `test_gitignore_opencode.py` verde.

### Task E.1 — Estender `.gitignore`

- Editar `.gitignore` (após linha 82, dentro do bloco "# Sistema de
  RAG meta-cognitivo (.claude/)" ou criar bloco paralelo
  "# OpenCode CLI"):
  - Adicionar `.opencode/node_modules/`
  - Adicionar `.opencode/package-lock.json` (o `package.json` do
    opencode é gerado pelo `opencode plugin add`; deixar o
    `package.json` versionado é opcional, mas `package-lock.json`
    é output de `npm install` e deve ser ignorado).

### Task E.2 — Teste de gate de gitignore

- `tests/integration/test_gitignore_opencode.py` (novo):
  - `test_opencode_node_modules_ignored`: confirma que o path
    `.opencode/node_modules/` casa com alguma regra do `.gitignore`.
    Estratégia: regex sobre o conteúdo do `.gitignore`.
  - `test_opencode_package_lock_ignored`: idem para
    `.opencode/package-lock.json`.
- Critérios de aceitação:
  - [ ] Suite verde.
  - [ ] `Select-String -Path .gitignore -Pattern '\.opencode/node_modules/'`
        retorna match.

---

## Fase F — Documentação + housekeeping (IMPORTANTE)

**Critério**: AGENTS.md atualizado com bloco "Decisões resolvidas
(Sprint 11)"; artefatos de runtime documentados; `pyproject.toml`
com cleanup configurado.

### Task F.1 — Atualizar AGENTS.md > Decisões resolvidas (Sprint 11)

Adicionar bloco (após Sprint 10):

```markdown
## Decisões resolvidas (Sprint 11)

- [x] **Manifest.json + 3 learning_*.py órfãos removidos (B11.2)**. O
      `.opencode/hooks/manifest.json` era "letra morta" desde Sprint 5
      C.1 (decisão de mover dispatch para plugin TS). Os 3 scripts
      `learning_*.py` só rodavam sob testes via subprocess. Removidos
      em Sprint 11. Runtime RAG meta-cognitivo passa por
      `.claude/hooks/_lib/learning.py::spawn_summarize_then_embed`,
      chamado pelos `stop.py` de `dev` e `code-reviewer`.

- [x] **4 agents legacy (backend/ml/prompt/qa-engineer) removidos (I11.2)**.
      Plugin TS `agent-hooks.ts:42-76` reduz o map `AGENTS` de 6 para 2
      (`code-reviewer` + `dev`). ~625 LoC duplicadas apagadas em
      `.claude/hooks/{backend,ml,prompt,qa}-engineer/`. Tests
      correspondentes reescritos.

- [x] **`code-reviewer.md` consolidado em `.opencode/agent/` (B11.5 +
      I11.1)**. Path canônico é singular (`.opencode/agent/`, não
      `.opencode/agents/`). Frontmatter `model: PROVIDER/MiniMax-M3`
      adicionado (Sprint 9 follow-up fechado).

- [x] **`_lib/learning.py:37` off-by-one corrigido (B11.1)**. Trocado
      `parents[2]` por `parents[3]` (consistente com `_lib/payload.py`).
      Artefatos `.claude/.claude/` e `.claude/storage/agent_hooks.log`
      foram limpos. Novo gate em
      `tests/integration/test_learning_path_safety.py`.

- [x] **Regra 3 do dfe-rules.md removida (I.5)**. "Sempre executar
      `python -m src.collector --once`" contradizia gate do
      `dev/pre_tool_use.py`. Skill `dfe-fiscal/SKILL.md` já documenta
      o Passo 2 (coletor) e continua como fonte canônica do fluxo.

- [x] **`.opencode/node_modules/` adicionado ao `.gitignore` (B11.4)**.
      Latente até inicializar git repo; cobertura via
      `test_gitignore_opencode.py`.
```

### Task F.2 — Limpar artefatos de runtime (SUGESTAO S3)

- Não há política de retenção para `.claude/state/inject-*.json`
  (91 arquivos atualmente). `.gitignore` já cobre (linha 80). Em
  runtime local cresce indefinidamente.
- Decisão: manter como manual por enquanto (sem script de cleanup
  para evitar side-effects inesperados). Documentar em AGENTS.md
  > Decisões que limpeza periódica é responsabilidade do operador.

### Task F.3 — Configurar cleanup de cache (SUGESTAO S2)

- Hoje `__pycache__/` é coberto por `.gitignore` (linha 10).
- Adicionar ao `pyproject.toml` (seções existentes):
  ```toml
  [tool.coverage.run]
  # ... existente
  cleanup = true

  [tool.pytest.ini_options]
  # ... existente
  cache_dir = ".pytest_cache"
  ```
- Critérios de aceitação:
  - [ ] `pytest --co` não cria `__pycache__/` espúrios em paths
        customizados.

### Task F.4 — README do projeto

- Atualizar `README.md` raiz (se existir menção ao manifest,
  `learning_*.py`, ou agents legacy) para refletir a arquitetura
  pós-Sprint 11. Foco: 2 agents canônicos (`dev` + `code-reviewer`),
  harness consolidado, sem manifest órfão.

---

## Matriz de testes afetados

| Arquivo de teste | Ação | Fase |
|---|---|---|
| `tests/unit/hooks/test_learning_helper.py` | ATUALIZAR — adicionar A.1 | A |
| `tests/integration/test_learning_path_safety.py` | **NOVO** | A |
| `tests/unit/test_domain_guard.py` | REDUZIR — remover `test_cli_*` | B |
| `tests/integration/test_domain_guard_plugin.py` | REDUZIR — remover manifest tests | B |
| `tests/integration/test_learning_stop_hook.py` | REESCREVER — focar em `dev/` | C |
| `tests/integration/test_learning_hooks_idempotent.py` | REESCREVER — contra `_lib/learning.py` | C |
| `tests/integration/test_learning_hooks_dispatch.py` | **REMOVER** | C |
| `tests/unit/hooks/test_code_reviewer_pre_tool_use.py` | ATUALIZAR — 2 agents | C |
| `tests/unit/hooks/test_payload.py` | ATUALIZAR — `_AGENT_HINTS` reduzido | C |
| `tests/unit/hooks/test_test_runner.py` | ATUALIZAR — suite `dev` | C |
| `tests/integration/test_no_legacy_agents.py` | **NOVO** | C |
| `tests/unit/test_code_reviewer_definition.py` | ADICIONAR — `test_frontmatter_has_model_with_provider` | D |
| `tests/integration/test_gitignore_opencode.py` | **NOVO** | E |
| `tests/unit/test_commands_definitions.py` | ATUALIZAR — code-reviewer path canônico | D |

**Total estimado**: 14 arquivos de teste tocados, 3 novos, ~80 LoC
novos de gate, -625 LoC duplicadas removidas, ~150 LoC de testes
reescritos.

---

## Resumo de cobertura pós-sprint

| Métrica | Antes | Depois |
|---|---|---|
| Agentes no plugin TS `AGENTS` map | 6 (1 + 5 legacy) | 2 (`code-reviewer`, `dev`) |
| Hooks Python em `.claude/hooks/` | 5 dirs (`dev`, `code-reviewer`, +4 legacy) | 2 dirs (`dev`, `code-reviewer`) |
| Scripts `learning_*.py` em `.opencode/hooks/` | 3 órfãos | 0 |
| `manifest.json` | existe, órfão | removido |
| `.gitignore` cobre `.opencode/node_modules/` | ✗ | ✓ |
| `_lib/learning.py::PROJECT_ROOT` correto | ✗ | ✓ |
| Contradição regra 3 vs gate | sim | não |
| Tests | ~599+ passed | ~580-590 passed (-alguns reescritos, +alguns novos) |
| Cobertura `src/` | ~85% | ~85% (sem regressão) |

---

## Próximo passo

Após aprovação do plano, executar `/feature plan-sprint11` (ou
equivalente) com `agent: dev` seguindo o pipeline canônico em
`.opencode/command/feature.md` (Fase 0 → Fase 7).

Se Fase C for considerada grande demais para uma sprint única,
dividir em:
- **C.A** (remoção): C.1, C.2, C.3, C.4.
- **C.B** (gate anti-regressão): C.5.

Manter C.6 (scripts ad-hoc) como opcional — pode ir para Sprint 12.

---

## Apêndice A — Riscos conhecidos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| B11.1 (fix `_lib/learning.py`) quebra produção porque algum path externo dependia do `.claude/storage/agent_hooks.log` errado | Baixa | Médio | Limpar `.claude/.claude/` e `.claude/storage/agent_hooks.log` ANTES do fix; gate em `test_learning_path_safety.py` impede regressão. Se alguém tinha hookdownstream, vai falhar de forma visível (PathNotFound). |
| Remoção dos 4 agents legacy quebra algum teste que ainda importa slug (ex.: `backend-engineer` em fixture) | Média | Médio | Mapeado em C.4 (lista de 6 testes a reescrever). Gate `test_no_legacy_agents.py` impede ressurreição. |
| Plugin TS reduzido a 2 slugs causa regressão em ambiente onde opencode injeta `subagent_type` real | Baixa | Médio | Manter `detectAgentFromSession` com fallback para "session" (modo permissivo) — comportamento documentado no comment header do plugin. Sprint 9 follow-up documentou esse comportamento como aceitável. |
| `npx tsx` falha por dependência Node ausente em CI | Média | Alto | Já coberto por Sprint 5 (testes que rodam `npx tsx` em `test_dev_plugin_dispatch.py` e similares); garantir que `npm install` rode antes do pytest no CI. Esta sprint não muda essa superfície. |
| Limpar `.claude/state/inject-*.json` em massa remove auditória de execução anterior | Baixa | Baixo | Arquivos estão em `.gitignore` (linha 80); perder = perder cache de injeção RAG de prompts antigos, não aprenderizados. Documentado em F.2. |
| Mover `code-reviewer.md` quebra `task` tool que referencia path antigo | Baixa | Médio | Já documentado em Sprint 9 como "Subagent code-reviewer nao invocavel"; mover para path canônico não piora o status quo. Frontmatter `model:` corrigido simultaneamente (D.2). |
| Editar `.gitignore` manualmente introduz erro de regex/sintaxe | Baixa | Alto | Diff pequeno e isolado; revisar com `cat .gitignore | grep opencode` antes do commit. Sem ferramentas Git no repo (env: not a git repo), então validação é puramente visual. |
| Sprint 11 vira sprint grande (5 BLOQUEANTE + 2 IMPORTANTE + 6 fases) e perde foco | Média | Médio | Plano divide em fases com critério de saída próprio; cada fase termina com suite verde local. Se Fase C travar, parar e pedir arbitragem (não iterar às cegas). |
| Cobertura cai abaixo de 80% por remoção de testes que cobriam código morto | Baixa | Médio | Cobertura atual ~85%; código removido em B e C não era de `src/` (era `.claude/hooks/`, `.opencode/hooks/`, `manifest_loader.py`). Não toca `src/` exceto o fix de 1 linha em `learning.py`. Sem risco de regressão. |
| `pyproject.toml` cleanup (F.3) entra em conflito com config existente | Baixa | Baixo | Mudanças aditivas (`cleanup = true`, `cache_dir = ".pytest_cache"`); fallback se chave já existir é manter valor existente. |

## Apêndice B — Fora do escopo desta Sprint (registro para follow-up)

- **Remover scripts ad-hoc `.claude/scripts/test_hooks.py` e `.claude/scripts/demo_agent_hooks.py`** (SUGESTAO S1, Task C.6). Decisão registrada: mover para `scripts/` raiz como `_smoke_legacy.py` ou remover completamente em Sprint 12.
- **Política de retenção para `.claude/state/inject-*.json`** (SUGESTAO S3). Decisão F.2: manter como manual. Follow-up Sprint 12+ pode adicionar script de cleanup com TTL (ex.: 30 dias).
- **Auto-detecção de agent no plugin TS sem depender de env var** (SUGESTAO S4). Hoje o `detectAgentFromSession` em `agent-hooks.ts:144-176` depende de `DFE_ACTIVE_AGENT` propagado pelo shell (comportamento não documentado do opencode CLI). Pode causar fallback para modo permissivo. Follow-up Sprint 12+: instrumentar com logging detalhado para confirmar se `agent` é detectado em produção real.
- **Cobertura de testes para agents `backend/ml/prompt/qa-engineer`** (removidos em C.1, mas testes em `tests/integration/test_learning_stop_hook.py` cobriam os hooks correspondentes). O gate `test_no_legacy_agents.py` substitui parte dessa cobertura.
- **Dup de definition `code-reviewer.md` em 2 paths** (Sprint 9 follow-up): `.opencode/agent/code-reviewer.md` (canônico) e `.claude/agents/code-reviewer.md` (Claude Code legacy) coexistem. Consolidar em Sprint 12+ ou decidir formalmente qual path é canônico.
- **Subagent `code-reviewer` continua não invocável via Task tool** (mesmo com Sprint 11 D.2 adicionando `PROVIDER/MiniMax-M3`). O sintoma `Model not found: MiniMax-M3/.` depende de configuração de modelo do provedor, fora do escopo do DFe-Agent.

## Apêndice C — Comandos shell para reproduzir a sprint manualmente

```bash
# === Fase 0 — Briefing ===
pwd && ls AGENTS.md SPEC.md PLAN.md .opencode/ 2>/dev/null
npx tsx .claude/scripts/search.ts -q "plan-sprint11 harness" -a dev --top-k 5

# === Fase A — Fix learning.py:37 ===
# TDD vermelho:
pytest tests/unit/hooks/test_learning_helper.py::test_project_root_resolves_to_dfe_agent_root -x
# Implementar (parents[2] -> parents[3]):
#   Editar .claude/hooks/_lib/learning.py:37
# Verde:
pytest tests/unit/hooks/test_learning_helper.py -x
# Limpar artefatos:
Remove-Item -LiteralPath .claude\.claude -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath .claude\storage\agent_hooks.log -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath .claude\.cache\hook-smoke -Recurse -Force -ErrorAction SilentlyContinue

# === Fase B — Remover manifest.json + 3 learning_*.py ===
Remove-Item -LiteralPath .opencode\hooks\manifest.json -Force
Remove-Item -LiteralPath .opencode\hooks\learning_prompt_submit.py -Force
Remove-Item -LiteralPath .opencode\hooks\learning_subagent_stop.py -Force
Remove-Item -LiteralPath .opencode\hooks\learning_stop.py -Force
# Remover bloco if __name__ == "__main__": de domain_guard.py
# Remover src/utils/manifest_loader.py
Remove-Item -LiteralPath src\utils\manifest_loader.py -Force
pytest tests/integration/test_domain_guard_plugin.py -x

# === Fase C — Remover 4 agents/hooks legacy ===
Remove-Item -LiteralPath .claude\agents\backend-engineer.md -Force
Remove-Item -LiteralPath .claude\agents\ml-engineer.md -Force
Remove-Item -LiteralPath .claude\agents\prompt-engineer.md -Force
Remove-Item -LiteralPath .claude\agents\qa-engineer.md -Force
Remove-Item -LiteralPath .claude\hooks\backend-engineer -Recurse -Force
Remove-Item -LiteralPath .claude\hooks\ml-engineer -Recurse -Force
Remove-Item -LiteralPath .claude\hooks\prompt-engineer -Recurse -Force
Remove-Item -LiteralPath .claude\hooks\qa-engineer -Recurse -Force
Remove-Item -LiteralPath tests\integration\test_learning_hooks_dispatch.py -Force
# Editar _lib/payload.py (_AGENT_HINTS) + _lib/test_runner.py + agent-hooks.ts
pytest tests/integration/test_no_legacy_agents.py -x

# === Fase D — Mover code-reviewer + corrigir model: + remover regra 3 ===
Move-Item -LiteralPath .opencode\agents\code-reviewer.md .opencode\agent\code-reviewer.md -Force
# Editar frontmatter: model: PROVIDER/MiniMax-M3
# Editar .opencode/rules/dfe-rules.md (remover regra 3)
# Editar .opencode/agent/dfe-agent.md (remover Passo 2 collector)
# Editar .claude/agents/{dev,code-reviewer}.md (refs)
Remove-Item -LiteralPath .opencode\agents -Recurse -Force -ErrorAction SilentlyContinue
pytest tests/unit/test_code_reviewer_definition.py -x

# === Fase E — gitignore ===
# Editar .gitignore: adicionar .opencode/node_modules/ + .opencode/package-lock.json
pytest tests/integration/test_gitignore_opencode.py -x

# === Fase F — Docs + housekeeping ===
# Editar AGENTS.md > Decisoes resolvidas (Sprint 11)
# Editar pyproject.toml (cleanup + cache_dir)

# === Gate global ===
pytest tests/ --cov=src --cov-fail-under=80

# === Fase 6 — RAG depois ===
# Criar .claude/knowledge/2026-08-26-feature-plan-sprint11.md
npx tsx .claude/scripts/embed.ts --file .claude/knowledge/2026-08-26-feature-plan-sprint11.md
npx tsx .claude/scripts/search.ts -q "feature plan-sprint11" -a dev --top-k 3
```
