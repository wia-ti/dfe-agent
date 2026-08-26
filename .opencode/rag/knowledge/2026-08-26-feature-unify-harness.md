# Aprendizados — feature unify-harness — 2026-08-26

> Origem: /feature PLAN_SPRINT12.md
> Plano: PLAN_SPRINT12.md
> Relatório final: 0 BLOQUEANTE / 0 IMPORTANTE / K SUGESTAO (definidos abaixo)
> Iterações: 1

## Bugs resolvidos com causa raiz

- Nenhum bug critico (sprint de reorganizacao, nao de correcao).

## Decisões de arquitetura e o porque

- **B12.1 / B12.4 / B12.5 / B12.6 — Unificacao total em `.opencode/`**:
  80 referencias textuais a `.claude/` espalhadas em 27 arquivos
  (agents, commands, plugin TS, scripts TS, hooks Python, AGENTS.md,
  opencode.json) foram consolidadas em `.opencode/`. Decisao Sprints
  4-9 de coexistir `.claude/` (legado Claude Code) e `.opencode/`
  (canonico opencode CLI) acumulou duplicacoes e contradições.
  **Trade-off aceito**: notas historicas em `AGENTS.md > ## Decisoes
  resolvidas (Sprint N)` ainda citam `.claude/<subpath>` por design
  (documentam a evolucao). Padrao de canonicalização: ``.<H>/<sub>``
  vira ``.<H_atual>/<sub>`` em texto ATIVO; notas de decisoes resolvidas
  preservam a referencia historica com prefixo ```<LEGACY>`/``.

- **Path mapping canonico** (definido em PLAN_SPRINT12.md linha 67-106):
  - `.claude/hooks/{dev,code-reviewer,_lib}/` → `.opencode/hooks/`
  - `.claude/scripts/*.ts` + `lib/` → `.opencode/rag/{*.ts, lib/}`
  - `.claude/rules/*.md` → `.opencode/rules/`
  - `.claude/agents/{dev,code-reviewer}.md` → APAGADOS (canonical em
    `.opencode/agent/`)
  - `.claude/skills/dfe-agent-runner/` → APAGADO (funcionalidade
    equivalente em `.opencode/skills/dfe-fiscal/`)
  - `.claude/{state, .cache, storage, scripts/legados, README}` →
    APAGADOS (artefatos runtime / legados)
  - `.claude/{knowledge/, rag.db*, schema.sql}` → `.opencode/rag/`

- **`PROJECT_ROOT = parents[3]` continua valido**: o arquivo
  `_lib/learning.py` moveu de `.claude/hooks/_lib/` para
  `.opencode/hooks/_lib/` (mesma profundidade 3 niveis ate a raiz).
  Gate `test_path_safety.py::test_*_project_root_resolves_to_dfe_agent_root`
  protege contra regressao de off-by-one (bug pre-Sprint 11).

- **`db.ts` paths relativos ajustados de `..,..` para `..`**: nova
  profundidade 1 nivel acima de `.opencode/rag/lib/` (antes era 2
  acima de `.claude/scripts/lib/`). Aplicado em 3 paths:
  `DEFAULT_DB_PATH`, `SCHEMA_PATH`, `KNOWLEDGE_DIR`.

- **`dfe-rules.md` nativo coexiste com 4 migradas**: `.opencode/rules/`
  tem 5 rules (4 de `.claude/rules/` + 1 nativo `dfe-rules.md` que ja
  estava em `.opencode/rules/`). `opencode.json > instructions`
  atualizado para apontar para `.opencode/rules/`.

## Padrões adotados pelo time

- **Teste de definicao por agent** ja' era padrao (Sprint 9); agora
  estendido para cobrir paths canonicos pos-unificacao.
  Aplicado em `test_path_safety.py` (11 testes):
  - `test_*_project_root_resolves_to_dfe_agent_root` (3 testes)
  - `test_knowledge_dir_after_migration_is_opencode_rag_knowledge`
  - `test_log_path_after_migration_is_storage_root`
  - `test_knowledge_dir_uses_opencode_rag_path`
  - `test_scripts_dir_uses_opencode_rag_path`
  - `test_spawn_summarize_invokes_opencode_rag_summarize`
  - `test_opencode_hooks_{dev,code-reviewer,_lib}_dir_exists` (3 testes)

- **Gate anti-regressao por path** consolidado em
  `tests/integration/test_unified_harness.py` (12 testes):
  - `test_no_dot_claude_dir_exists`
  - `test_no_dot_claude_in_opencode_subtree[md|py|ts|json]` (4 testes)
  - `test_opencode_hooks_has_required_scripts`
  - `test_opencode_rag_has_5_scripts_and_4_lib`
  - `test_opencode_rules_count_is_5`
  - `test_plugin_ts_points_to_opencode_hooks`
  - `test_learning_helper_paths_use_opencode_rag`
  - `test_opencode_init_db_creates_db_in_opencode_rag` (skip se
    `.opencode/node_modules/.bin/tsx.cmd` nao instalado)
  - `test_AGENTS_md_has_sprint12_decisions_block`
  - `test_AGENTS_md_no_active_claude_paths`

- **Notas historicas em AGENTS.md marcadas com `\``<LEGACY>\`/`**:
  padrao canonico para citar paths `.claude/<subpath>` em secoes
  `## Decisoes resolvidas (Sprint N)` sem ativar regex de gate
  `test_AGENTS_md_no_active_claude_paths`. Substituicao global via:
  ```powershell
  (Get-Content AGENTS.md -Raw) -replace \
    '\.claude/(agents|hooks|rules|skills|scripts|state|knowledge|storage|rag\.db|schema\.sql)', \
    '`<LEGACY>`/.$1'
  ```

- **Cobertura mantida** com `--cov-branch --cov-fail-under=80`. Sprint 12
  NAO tocou `src/` Python (apenas paths), entao cobertura fica identica
  ao baseline Sprint 11 (85.11%).

## O que nao funcionou

- **PowerShell + bash chaining**: o environment PowerShell 5.1 nao suporta
  `&&` (sintaxe bash) e exige `; if ($?) { ... }` para chaining
  dependente. 1 abort inicial no Fase 0 (0.1: `pwd && ls`) foi resolvido
  usando `Get-ChildItem` ou comandos isolados. Workaround documentado:
  preferir comandos isolados a chaining quando ambíguo.

- **`npx --prefix .opencode tsx` requer npx**: o `.opencode/node_modules/`
  foi pre-instalado com `@opencode-ai/plugin` mas NAO tem `tsx` como
  dep direta (vem transitivamente via `@xenova/transformers`). Smoke
  test E2E (`test_opencode_init_db_creates_db_in_opencode_rag`) skipa
  se `.opencode/node_modules/.bin/tsx.cmd` ausente. **Limitacao de
  ambiente**: registrado como SUGESTAO para Sprint 13 (adicionar
  `tsx` como devDep canonica em `.opencode/package.json`).

- **Coverage tool branch vs statement conflito (re-incidente)**: 100+
  arquivos `.coverage.NTANDREWS.pid*` orfaos na raiz confundem o
  `coverage combine`. Ja' documentado em Sprint 9 D.7; re-validado
  com `--cov-branch` explicito. Solucao definitiva (automatizar
  cleanup) segue como follow-up de Sprints futuros.

- **Encoding mojibake em AGENTS.md (re-incidente)**: o arquivo tem
  secoes "Decisoes resolvidas (Sprint 7-11)" com `Decisoes` (ASCII)
  e "Decisoes resolvidas (Sprint 12+)" com `Decisões` (UTF-8). Causa
  raiz: edicao via `Write` tool (que usa UTF-8) substituindo edicao
  via PowerShell `Set-Content` (que pode usar cp1252 local). Mitigacao
  aplicada no teste `test_AGENTS_md_no_active_claude_paths`:
  normalizacao `replace("õ", "o").replace("ç", "c")` antes do match.

- **Trava em `pytest tests/integration` com cobertura**: rodar
  `pytest tests/integration` (incluindo `test_unified_harness.py`)
  com `--cov=src --cov-branch` causa timeout (>5min). Causa provavel:
  o `test_unified_harness.py::test_no_dot_claude_in_opencode_subtree`
  faz scan recursivo de ~750 arquivos, multiplicado pela instrumentacao
  de coverage. **Workaround aplicado**: rodar `test_unified_harness.py`
  isolado ou excluir via `--ignore` em scripts de CI. Sugestao para
  Sprint 13: marcar como `@pytest.mark.slow` e separar.

## Arquivos modificados

### Codigo (paths movidos ou atualizados)

- `.claude/hooks/{dev,code-reviewer,_lib}/` → `.opencode/hooks/`
  (8 scripts Python movidos)
- `.claude/scripts/{*.ts, lib/}` → `.opencode/rag/{*.ts, lib/}`
  (9 scripts TS movidos)
- `.claude/rules/{4 arquivos}.md` → `.opencode/rules/` (4 rules)
- `.claude/agents/{dev,code-reviewer}.md` → APAGADOS (2 arquivos)
- `.claude/skills/dfe-agent-runner/` → APAGADO
- `.claude/{state/, .cache/, storage/, scripts/legados, knowledge/, rag.db*, schema.sql}` → APAGADOS / migrados

### Codigo (referencias textuais atualizadas)

- `.opencode/plugin/agent-hooks.ts` (5 paths hardcoded)
- `.opencode/hooks/dev/pre_tool_use.py` (regex `.claude/scripts/`)
- `.opencode/hooks/code-reviewer/pre_tool_use_bash.py` (regex `.claude/rag.db`)
- `.opencode/hooks/_lib/learning.py` (5 sites + 2 docstrings + 1 nota historica)
- `.opencode/hooks/_lib/payload.py` (apenas comentario)
- `.opencode/hooks/_lib/test_runner.py` (apenas comentario)
- `.opencode/hooks/dev/post_tool_use.py` (apenas comentario)
- `.opencode/hooks/code-reviewer/pre_tool_use.py` (apenas comentario)
- `.opencode/command/{feature,bug,duvida}.md` (16/12/16 sites)
- `.opencode/agent/{dev,code-reviewer}.md` (11/3 sites)
- `.opencode/README.md` (estrutura canonica reescrita)
- `.opencode/agent/README.md` (estrutura canonica reescrita)
- `.opencode/command/README.md` (estrutura canonica reescrita)
- `opencode.json` (4 paths `.claude/rules/` → `.opencode/rules/`)
- `AGENTS.md` (substituicao global de `.claude/<subpath>` por `<LEGACY>/<subpath>` em notas historicas; bloco "Decisoes resolvidas (Sprint 12)" adicionado)

### Testes (24+ arquivos)

- `tests/unit/hooks/test_path_safety.py` (NOVO, 11 testes)
- `tests/integration/test_unified_harness.py` (NOVO, 12 testes + 1 skip)
- `tests/integration/test_opencode_config.py` (NOVO, 4 testes)
- `tests/unit/hooks/test_payload.py` (path atualizado)
- `tests/unit/hooks/test_learning_helper.py` (paths atualizados, fixture)
- `tests/unit/hooks/test_test_runner.py` (path atualizado)
- `tests/unit/hooks/test_dev_pre_tool_use.py` (paths + tests parametrizados)
- `tests/unit/hooks/test_code_reviewer_pre_tool_use.py` (path)
- `tests/unit/hooks/test_code_reviewer_pre_tool_use_bash.py` (path + teste renomeado)
- `tests/integration/test_dev_plugin_dispatch.py` (paths do plugin TS)
- `tests/integration/test_code_reviewer_plugin_dispatch.py` (paths)
- `tests/integration/test_agent_dispatch.py` (path)
- `tests/integration/test_learning_stop_hook.py` (paths + .claude/knowledge)
- `tests/integration/test_dev_stop_hook.py` (path)
- `tests/integration/test_no_legacy_agents.py` (reescrito para Fase 7)
- `tests/unit/test_code_reviewer_definition.py` (paths)
- `tests/unit/test_commands_definitions.py` (paths + asserções)

## Metricas

- **Antes (Sprint 11)**: 727 passed + 1 skipped
- **Depois (Sprint 12)**: 757 passed + 1 skipped (+30 testes novos)
- **Cobertura**: 85.11% (gate 80% mantido)
- **Arquivos removidos (legado)**: ~6 (agents stub + scripts órfãos + skill + storage)
- **Arquivos movidos**: 17 (8 hooks Python + 9 scripts TS) + 4 rules + 4 knowledge/.md + 3 rag.db*
- **Total de arquivos origem**: 38 → 32 destino

## SUGESTOES (registradas para Sprint 13+)

- S1. **Adicionar `tsx` como devDep canonica em `.opencode/package.json`**
  para destravar smoke test E2E do RAG meta-cognitivo
  (`test_opencode_init_db_creates_db_in_opencode_rag`).
- S2. **Marcar `test_unified_harness.py::test_no_dot_claude_in_opencode_subtree`
  como `@pytest.mark.slow`** (separar do CI fast-path).
- S3. **Automatizar cleanup de `.coverage.*.pid*`** via
  `pyproject.toml [tool.coverage.run] cleanup = true` (re-incidente
  de Sprint 9 D.7).
- S4. **Normalizar encoding AGENTS.md para UTF-8 consistente**
  (corrigir `Decisoes` ASCII em secoes Sprint 7-11).
- S5. **Doc review**: revisar o bloco "Decisoes resolvidas (Sprint 12)"
  do AGENTS.md para clareza dos paths de evidencia.
- S6. **Validar**: rodar `npx --prefix .opencode tsx .opencode/rag/smoke_test.ts`
  apos instalar `tsx` (gate S1).