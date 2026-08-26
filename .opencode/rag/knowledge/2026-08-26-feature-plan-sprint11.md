# Aprendizados -- feature plan-sprint11 -- 2026-08-26

> Origem: /feature plan-sprint11
> Plano: PLAN_SPRINT11.md
> Relatorio final do code-reviewer: 0 BLOQUEANTE / 0 IMPORTANTE / 0 SUGESTAO (1 BLOQUEANTE + 7 IMPORTANTE + 3 SUGESTAO identificados no primeiro review; todos resolvidos na Fase 5)
> Iteracoes do loop corretivo: 1

## Bugs resolvidos com causa raiz

- **B11.1 -- off-by-one em `_lib/learning.py:37`**. `_lib/learning.py:37`
  usava `parents[2]` (=`.claude/`) em vez de `parents[3]` (=DFe-Agent root).
  Consequencia: `_knowledge_dir()` resolvia para `.claude/.claude/knowledge/`
  e `LOG_PATH` para `.claude/storage/agent_hooks.log` -- artefatos reais
  visiveis no disco ate 2026-08-26 (6 arquivos `_pending-*.md` no diretorio
  aninhado + 431 linhas de log legado). Sintoma: tests monkeypatchavam
  `PROJECT_ROOT`, entao CI nao detectava. Fix: trocar `parents[2]` por
  `parents[3]` em `learning.py:37` + o mesmo bug latente em
  `_lib/test_runner.py:29` (apenas corrigido na Fase 5 do code-review).
  Arquivo: `tests/unit/hooks/test_learning_helper.py::test_project_root_resolves_to_dfe_agent_root`
  (vermelho -> verde).

- **B11.2 -- `manifest.json` + 3 scripts `learning_*.py` orfaos**. Opencode
  nao suporta nativamente `pre_request`/`subagent_end`/`session.stopped`
  (Sprint 5 C.1); plugin TS `agent-hooks.ts` ja' tinha dispatch proprio.
  Manifest + scripts rodavam apenas sob testes (subprocess), mas tests
  defendiam o "contrato sombra" como se fosse runtime. Fix: remover
  `.opencode/hooks/manifest.json`, 3 `learning_*.py` e `src/utils/manifest_loader.py`.
  `domain_guard.py` mantido (módulo Python vivo importado por `src/utils/http_guard.py`)
  -- removido apenas o bloco `if __name__ == "__main__":` (CLI morto).

- **B11.4 -- `.opencode/node_modules/` nao coberto por `.gitignore`**.
  Latente ate inicializar git repo (env atual: nao e' git repo). 55 MB
  de deps do SDK `@opencode-ai/plugin` seriam commitados. Fix: adicionar
  `.opencode/node_modules/` + `.opencode/package-lock.json` ao `.gitignore`.
  Cobertura: `tests/integration/test_gitignore_opencode.py` (3 testes).

- **B11.5 + I11.1 -- `code-reviewer.md` no path errado + `model:` sem prefixo**.
  Path `.opencode/agents/` (plural) tinha apenas o code-reviewer orfao;
  resto do projeto usa `.opencode/agent/` (singular). Frontmatter
  `model: MiniMax-M3` quebrava Task tool (sintoma `Model not found`).
  Fix: mover para path singular + adicionar prefixo `PROVIDER/`.
  Cobertura: `tests/unit/test_code_reviewer_definition.py::test_frontmatter_has_model_field`
  exige formato `^\S+/\S+$`.

## Decisoes de arquitetura e o porque

- **C.3 -- `_AGENT_HINTS` reduzido para 2 slugs canonicos**. Era uma
  heuristica de deteccao de agent ativo (em `_lib/payload.py`) com 5
  slugs (`code-reviewer`, `backend-engineer`, `ml-engineer`,
  `prompt-engineer`, `qa-engineer`). Como os 4 slugs de implementacao
  foram removidos (C.1) e consolidados em `dev`, o helper reconhece
  apenas `code-reviewer` + `dev`. Solucao DRY: usar `_AGENT_HINTS` como
  referencia estavel + `detect_active_agent` como dispatcher canonico.
  Anti-regressao: `tests/integration/test_no_legacy_agents.py`.

- **Plugin TS reduzido de 6 para 2 slugs**. O map `AGENTS` em
  `.opencode/plugin/agent-hooks.ts:42-76` lista apenas `code-reviewer`
  e `dev` pos Sprint 11. Antes, tinha 4 slugs legacy (Sprint 10 fechou
  a interface, mas o dispatch permanecia). Todos os 4 hooks Python
  correspondentes (`.claude/hooks/{backend,ml,prompt,qa}-engineer/`)
  foram removidos (~625 LoC duplicadas). Plug-in TS continua sendo
  carregado via CLI (`opencode plugin add .opencode/plugin/agent-hooks.ts`),
  com dispatch implementado em `tool.execute.before/after` +
  `event.session.stopped`.

- **Suite de testes como gate anti-regressao**. A Sprint 11 introduz
  `tests/integration/test_no_legacy_agents.py` (7 testes) que verifica:
  apenas `dev.md` e `code-reviewer.md` em `.claude/agents/`; apenas
  `dev/` e `code-reviewer/` em `.claude/hooks/` (alem de `_lib/`);
  plugin TS roteia apenas 2 slugs; `_AGENT_HINTS` reduzido;
  `test_runner.py` sem branch para `backend-engineer`/`ml-engineer`.
  Impede ressurreicao de agentes legacy (problema recorrente que
  Sprint 10 ja' tinha documentado como follow-up SUGESTAO).

- **Regra 3 do dfe-rules.md removida**. "Sempre executar
  `python -m src.collector --once` antes de qualquer resposta"
  contradizia o gate `dev/pre_tool_use.py` que BLOQUEIA exatamente esse
  comando (defesa em profundidade para impedir scraping nao-autorizado).
  Skill `.opencode/skills/dfe-fiscal/SKILL.md` ja' documenta o Passo 2
  do workflow canonico. Solucao: remover regra + nota explicativa
  + atualizar `test_dfe_rules_definition.py::test_rules_has_exactly_4_ordered_items`.

## Padroes adotados pelo time

- **Convencao TDD vermelho-primeiro para bugs off-by-one**: escrever
  teste que falha ANTES do fix (e nao so' verificacao pos-hoc). O bug
  B11.1 so' foi detectado porque o teste vermelho (`PROJECT_ROOT !=
  DFe-Agent root`) ja' demonstraria a falha mesmo sem monkeypatch --
  eh o tipo de teste que protege contra regressao silenciosa de CI.

- **Anti-regressao explicita no nome do teste**: sufixo `*_no_legacy_*`
  ou `*_canonical*` deixa claro que o teste NAO verifica feature
  adicionada, mas garante que codigo removido nao volta (cleanup
  archive). Aplicado a `test_no_legacy_agents.py`,
  `test_project_root_resolves_to_dfe_agent_root`,
  `test_knowledge_dir_is_canonical`, `test_log_path_is_storage_root`.

- **Sprint 11 marca transicao para harness minimo**: de 6 agents + manifest
  orfao + 3 scripts dead para 2 agents canonicos (dev + code-reviewer)
  sem codigo morto. O "letra morta" e' explicitamente combatido pelo
  test runner que verifica redacao de testes = redacao de origem.

## O que nao funcionou e por que

- **`scripts/demo_cli.py` removido acidentalmente em cleanup PowerShell**.
  O comando `Remove-Item -LiteralPath "scripts\demo_cli.py" -ErrorAction SilentlyContinue`
  removeu o arquivo canonico pre-existente. Suite detectou no gate de
  whitelist (`tests/unit/test_scripts_whitelist.py::test_scripts_dir_only_canonics`)
  com mensagem `"scripts/ deveria conter apenas 'demo_cli.py'"`. Fix:
  recriar `scripts/demo_cli.py` com demo do CLI `python -m src.query`
  (4 cenarios: semantica, hibrida, cache, stats). Licao: nunca usar
  `-ErrorAction SilentlyContinue` em scripts de cleanup -- preferir
  `Test-Path -LiteralPath X` antes de `Remove-Item`.

- **Code-reviewer subagent nao invocavel via Task tool**. O subagent
  `code-reviewer` retorna `Model not found: MiniMax-M3/.` quando
  invocado (Sprint 9 gap conhecido). Frontmatter foi corrigido em D.2
  (`model: PROVIDER/MiniMax-M3`), mas o provider real nao foi
  confirmado. Workaround aplicado na Fase 4: invocar subagent `general`
  com prompt que carrega o template canonico do code-reviewer. O gap
  segue como follow-up Sprint 12+ (definir provider MiniMax-M3).

- **Coverage tool timeout (~5min)** em suite completa com `--cov`. O
  `coverage combine` demora para gerar `.coverage.*` files paralelos
  (documentado por AGENTS.md Sprint 9 como "Coverage tool branch vs
  statement conflito"). Workaround: rodar suite sem `--cov` para
  verificacao rapida de pass/fail (96s para 715 passed), depois
  rodar com `--cov --no-cov-on-fail` em batch separado (276s para
  cobertura + 715 passed). Cleanup de `.coverage.*` files deve
  virar automatica via `pyproject.toml::tool.coverage.run.cleanup = true`.

## Arquivos modificados

### Sprint 11 -- fase de implementacao

**Plano**:
- `PLAN_SPRINT11.md` (novo; plano da sprint)

**Codigo (1 fix + 6 reducoes + 1 remocao)**:
- `.claude/hooks/_lib/learning.py` (fix off-by-one)
- `.claude/hooks/_lib/test_runner.py` (fix off-by-one; aplicado na Fase 5)
- `.claude/hooks/_lib/payload.py` (reduz `_AGENT_HINTS` para 2 slugs)
- `.claude/hooks/code-reviewer/pre_tool_use.py` (msg de bloqueio aponta para dev)
- `.opencode/hooks/domain_guard.py` (remove `if __name__ == "__main__"`; adicionado `__all__`)
- `.opencode/plugin/agent-hooks.ts` (reduz map `AGENTS` para 2; atualiza comentarios)
- `.opencode/agent/code-reviewer.md` (frontmatter `model: PROVIDER/MiniMax-M3` + path canonico)
- `.opencode/agent/dfe-agent.md` (remove Passo 2 collector)
- `.opencode/rules/dfe-rules.md` (remove regra 3; 4 regras restantes + nota historica)
- `.opencode/agent/dev.md` (atualiza ref code-reviewer)
- `.opencode/command/{feature,bug}.md` (atualiza ref code-reviewer)
- `.opencode/{README,command/README,agent/README}.md` (atualiza refs)
- `.opencode/hooks/__pycache__/` (limpeza automatica)
- `.claude/README.md` (atualiza diagrama de hooks + tabela de agents)
- `.claude/rules/seguranca.md` (atualiza ref guardrail)
- `.claude/agents/dev.md` (atualiza ref code-reviewer)
- `AGENTS.md` (bloco "Decisoes resolvidas (Sprint 11)" + atualizacoes de diagrama e estrutura)
- `.gitignore` (adiciona `.opencode/node_modules/` + `.opencode/package-lock.json`)

**Remocoes (codigo morto / consolidados)**:
- `.opencode/hooks/manifest.json`
- `.opencode/hooks/learning_prompt_submit.py`
- `.opencode/hooks/learning_subagent_stop.py`
- `.opencode/hooks/learning_stop.py`
- `src/utils/manifest_loader.py`
- `.claude/agents/{backend,ml,prompt,qa}-engineer.md` (4 files)
- `.claude/hooks/{backend,ml,prompt,qa}-engineer/` (4 dirs; ~625 LoC)
- `.opencode/agents/` (diretorio; arquivo movido para `.opencode/agent/`)
- `.claude/.claude/`, `.claude/storage/agent_hooks.log`, `.claude/.cache/hook-smoke/`

**Testes (3 novos + 9 atualizados + 3 removidos + 1 reconstruido)**:
- `tests/integration/test_no_legacy_agents.py` (novo; 7 testes)
- `tests/integration/test_gitignore_opencode.py` (novo; 3 testes)
- `tests/unit/hooks/test_learning_helper.py` (3 testes adicionados: path safety)
- `tests/integration/test_learning_stop_hook.py` (reescrito; 6 testes focados em `dev/stop.py`)
- `tests/unit/hooks/test_test_runner.py` (atualizado; parametrizado para `dev`)
- `tests/unit/hooks/test_payload.py` (atualizado; usa slug canonico)
- `tests/unit/hooks/test_code_reviewer_pre_tool_use.py` (atualizado; 2 agents em vez de 5)
- `tests/unit/test_code_reviewer_definition.py` (exige `PROVIDER/MiniMax-M3`)
- `tests/unit/test_dfe_rules_definition.py` (exige 4 regras; gate anti-regressao para regra 3)
- `tests/unit/test_dfe_agent_definition.py` (remove referencia a "collector --once" como literal)
- `tests/integration/test_domain_guard_plugin.py` (remove testes de manifest)
- `tests/integration/test_code_reviewer_plugin_dispatch.py` (path canonico singular + comentario corrigido)
- `tests/unit/test_domain_guard.py` (remove 2 testes CLI)
- `tests/integration/test_learning_hooks_dispatch.py` (REMOVIDO -- manifest morto)
- `tests/integration/test_learning_hooks_idempotent.py` (REMOVIDO -- scripts orfaos)
- `tests/unit/test_learning_prompt_submit.py` (REMOVIDO -- script orfao)
- `scripts/demo_cli.py` (reconstruido apos remocao acidental em cleanup)
