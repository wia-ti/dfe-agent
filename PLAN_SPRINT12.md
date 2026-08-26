# PLAN_SPRINT12.md

> Plano de **unificação total do harness em `.opencode/`**: toda a
> lógica atualmente espalhada entre `.claude/` (agents stub, hooks
> Python, RAG meta-cognitivo, rules, skill legado) e `.opencode/`
> (agents canônicos, plugin TS, comandos, skill canônica) passa a
> viver em `.opencode/`. O diretório `.claude/` deixa de existir.
>
> Origem: pedido do usuário em 2026-08-26 ("quero unificar tudo na
> pasta `.opencode` para evitar conflitos e redundâncias"). Análise
> de redundâncias/conflictos precede este plano (4 redundâncias
> principais, 4 conflitos identificados, 80 referências textuais a
> `.claude/` em 27 arquivos).
>
> 6 BLOQUEANTE + 3 IMPORTANTE. TDD, suite verde, cobertura >= 80%,
> gate anti-regressão forte (testes em `tests/integration/test_unified_harness.py`).

## Critério global de conclusão

`pytest tests/ --cov=src --cov-fail-under=80` retorna exit code 0 **E**
`[ -d .claude ] || echo OK` retorna "OK" (diretório `.claude/` apagado)
**E** `grep -rE '\.claude/(agents|hooks|rules|skills|scripts|state|knowledge|storage|rag\.db|schema\.sql)' .opencode/ AGENTS.md opencode.json` retorna 0 hits
**E** `npx tsx .opencode/rag/init_db.ts` continua funcionando (RAG meta-cognitivo no novo path)
**E** `python .opencode/hooks/dev/stop.py <payload-json>` continua funcionando (hooks Python no novo path)
**E** `opencode agent list` lista `dfe-agent`, `dev`, `code-reviewer` (sem mudanças)
**E** `opencode command list` lista `/feature`, `/bug`, `/duvida` (sem mudanças)
**E** `_lib/learning.py::PROJECT_ROOT` ainda resolve para o DFe-Agent root (não vira `.opencode/`).

```
Fase 1 ──► Fase 2 ──► Fase 3 ──► Fase 4 ──► Fase 5 ──► Fase 6 ──► Fase 7
mover     migrar     migrar     atualizar    apagar     docs +    gate
hooks     scripts    agents     comandos +   .claude/   plano     anti-
Python    TS + lib   stub +     plugin TS +  state +    canonico regressao
(LOQ.)    (LOQ.)    rules      opencode     .cache     AGENTS.md (LOQ.)
                    (LOQ.)     .json        scripts
                              (LOQ.)       (LOQ.)
```

**Dependências críticas entre fases**:
- Fase 2 (mover scripts TS) depende de Fase 1 (mover hooks Python) porque o helper `_lib/learning.py` chama `summarize.ts`/`embed.ts` por path relativo — mover só os scripts quebraria `stop.py` se a Fase 1 não movesse primeiro.
- Fase 3 (mover agents stub + rules) depende de Fase 1+2 (porque `dev.md` cita paths dos hooks/scripts).
- Fase 4 (atualizar comandos + plugin TS + opencode.json) depende de Fase 1+2+3.
- Fase 5 (apagar `.claude/`) depende de 1+2+3+4 (state, .cache, scripts legados).
- Fase 6 (docs) depende de 5.
- Fase 7 (gate anti-regressão) depende de 1+2+3+4+5+6.

**Paralelismo intra-fase**:
- Fase 1: Tasks 1.1-1.4 podem ser feitas em paralelo (não tocam os mesmos arquivos).
- Fase 2: Tasks 2.1-2.3 podem ser feitas em paralelo.

## Resumo dos problemas observados

| ID | Sintoma | Causa raiz |
|----|---------|------------|
| **B12.1** | 80 referências textuais a `.claude/` espalhadas em 27 arquivos (agents, commands, plugin TS, scripts TS, hooks Python, AGENTS.md, opencode.json, 15+ testes). Risco alto de drift futuro e bug latente (path morto `.claude/agents/dev.md` no Sprint 9). | Decisão arquitetural Sprints 4-9: `.claude/` era o path "legado Claude Code" coexistindo com `.opencode/` (canônico opencode CLI). Acumulou duplicações, divergências e contradições documentadas (C1-C4 da análise anterior). |
| **B12.2** | `agents/dev.md` e `agents/code-reviewer.md` em `.claude/` são 95% duplicatas dos `.opencode/agent/` correspondentes (115+128 LoC cada par); divergem em formato (Claude Code hooks: vs opencode permission:*) mas o opencode CLI ignora o frontmatter `hooks:` — apenas o `AGENTS` map em `agent-hooks.ts` é a verdade runtime. | Acumulado de Sprints 4-9 (legado Claude Code) sem consolidação. `.opencode/agent/README.md:17-19` já reconhece a duplicata como follow-up. |
| **B12.3** | 4 rules em `.claude/rules/*.md` são carregadas via `opencode.json > instructions` (linhas 7-10) com paths hardcoded `.claude/rules/*`. Path vive fora do "namespace" `.opencode/`. Reorganização futura do `.claude/` quebraria silenciosamente. | `opencode.json` mistura paths `.claude/` (rules) com `.opencode/` (plugin TS). Inconsistência de namespace. |
| **B12.4** | RAG meta-cognitivo (scripts TS, `rag.db`, `knowledge/`, `schema.sql`) vive em `.claude/` enquanto o npm/package.json que o suporta vive em `.opencode/`. Divisão artificial: TS importa do `.claude/` mas o `node_modules/` está em `.opencode/`. | Decisão Sprints 7-8: scripts TS separados do npm package para evitar import cruzado. |
| **B12.5** | Skill legado `dfe-agent-runner/SKILL.md` (307 LoC) está em `.claude/skills/`, referenciada por nenhum agent/command atual (descrição desatualizada: cita `confaz.fazenda.gov.br` removido em Sprint 4 e "rule 3" removida em Sprint 11). | Skill ficou órfã quando `.opencode/skills/dfe-fiscal/SKILL.md` foi adotada como canônica em Sprints 9-10. Nunca removida. |
| **B12.6** | Estado de runtime `.claude/state/inject-*.json` (94 arquivos) e `.claude/.cache/hook-smoke/` (legado pre-Sprint 11) poluem o repo. `learning.py` ainda pode escrever em `.claude/knowledge/` e `.claude/storage/agent_hooks.log` se `PROJECT_ROOT` for monkeypatched errado. | Helper `_lib/learning.py` resolve paths via `PROJECT_ROOT` calculado em runtime (parents[3]). Move sem ajustar manteria paths funcionando, mas qualquer drift futuro fica opaco. |
| **I12.1** | `opencode.json > instructions` lista 4 rules de `.claude/rules/` mas não lista `.opencode/rules/dfe-rules.md` que é carregada pelo agent `dfe-agent` (formato opencode rules). | Mistura de dois mecanismos: `instructions` (opencode CLI) e `permission` (frontmatter de agent). Documentado mas gera confusão. |
| **I12.2** | `_lib/learning.py:233,278` e `db.ts:19-33` têm paths hardcoded `.claude/scripts/...` e `.claude/rag.db`. Mover os scripts exige mover essas referências em 4 lugares. | Mover TS implica ajustar contratos de 3 helpers Python + 1 wrapper TS. |
| **I12.3** | `tests/unit/hooks/test_*.py` e `tests/integration/test_*.py` (15 arquivos) têm `Path` constants e asserções apontando para `.claude/hooks/...` e `.claude/scripts/...`. Cobertura existe mas trava o layout atual. | Testes de integração protegem a estrutura atual; mover exige atualização sincronizada. |

---

## Mapa de migração (referência para todas as fases)

| Origem (`.claude/`) | Destino (`.opencode/`) | Notas |
|--------------------|------------------------|-------|
| `agents/dev.md` | **APAGAR** | Duplicata de `.opencode/agent/dev.md`. |
| `agents/code-reviewer.md` | **APAGAR** | Duplicata de `.opencode/agent/code-reviewer.md`. |
| `hooks/dev/pre_tool_use.py` | `hooks/dev/pre_tool_use.py` | Path idêntico (já em `.opencode/`); apenas mover de `.claude/hooks/dev/` → `.opencode/hooks/dev/`. |
| `hooks/dev/post_tool_use.py` | `hooks/dev/post_tool_use.py` | Idem. |
| `hooks/dev/stop.py` | `hooks/dev/stop.py` | Idem. |
| `hooks/code-reviewer/pre_tool_use.py` | `hooks/code-reviewer/pre_tool_use.py` | Idem. |
| `hooks/code-reviewer/pre_tool_use_bash.py` | `hooks/code-reviewer/pre_tool_use_bash.py` | Idem. |
| `hooks/_lib/learning.py` | `hooks/_lib/learning.py` | `PROJECT_ROOT = parents[3]` continua válido (3 níveis de profundidade mantidos). |
| `hooks/_lib/payload.py` | `hooks/_lib/payload.py` | `PROJECT_ROOT = parents[3]` idem. |
| `hooks/_lib/test_runner.py` | `hooks/_lib/test_runner.py` | Idem. |
| `scripts/init_db.ts` | `rag/init_db.ts` | **NOVO subdiretório `.opencode/rag/`**. |
| `scripts/summarize.ts` | `rag/summarize.ts` | Idem. |
| `scripts/embed.ts` | `rag/embed.ts` | Idem. |
| `scripts/search.ts` | `rag/search.ts` | Idem. |
| `scripts/smoke_test.ts` | `rag/smoke_test.ts` | Idem. |
| `scripts/lib/db.ts` | `rag/lib/db.ts` | Ajustar `DEFAULT_DB_PATH`/`KNOWLEDGE_DIR`/`SCHEMA_PATH` para 1 nível acima (`.opencode/rag/`) em vez de 2 (`.claude/`). |
| `scripts/lib/chunker.ts` | `rag/lib/chunker.ts` | Sem mudança de lógica. |
| `scripts/lib/embedder.ts` | `rag/lib/embedder.ts` | Sem mudança. |
| `scripts/lib/classifier.ts` | `rag/lib/classifier.ts` | Sem mudança. |
| `scripts/lib/README.md` | `rag/lib/README.md` | Atualizar paths textuais. |
| `scripts/test_hooks.py` | **APAGAR** | Legado pré-Sprint 11 (testava `learning_*.py` órfãos). |
| `scripts/demo_agent_hooks.py` | **APAGAR** | Demo manual pré-Sprint 11. |
| `rag.db*` | `rag/rag.db*` | Regenerado por `init_db.ts`. |
| `schema.sql` | `rag/schema.sql` | Idem. |
| `knowledge/<date>-*.md` (4 arquivos) | `rag/knowledge/<date>-*.md` | Migrar conteúdo; manter filenames. |
| `knowledge/_pending-*.md.lock` (2 arquivos) | **APAGAR** | Markers idempotentes — devem ser regenerados. |
| `state/inject-*.json` (94 arquivos) | **APAGAR** | Artefatos de runtime. |
| `storage/agent_hooks.log` | **APAGAR** | Log será regenerado em `<PROJECT_ROOT>/storage/agent_hooks.log` (root, não em `.opencode/`). |
| `.cache/hook-smoke/` | **APAGAR** | Cache de smoke test pré-Sprint 11. |
| `rules/seguranca.md` | `rules/seguranca.md` | Mover de `.claude/rules/` → `.opencode/rules/`. |
| `rules/convencoes-gerais.md` | `rules/convencoes-gerais.md` | Idem. |
| `rules/src.md` | `rules/src.md` | Idem. |
| `rules/tests.md` | `rules/tests.md` | Idem. |
| `skills/dfe-agent-runner/SKILL.md` | **APAGAR** | Legado, conteúdo obsoleto (ref `confaz`, ref rule 3 removida). |
| `README.md` | **APAGAR** | Conteúdo mergeado em `.opencode/README.md`. |

**Total**: 38 arquivos origem → 32 destino (6 apagados como legado, 6 markdowns apagados como runtime/state).

---

## Fase 1 — Mover hooks Python para `.opencode/hooks/` (B12.1+ B12.2, BLOQUEANTE)

**Critério**: `.opencode/hooks/{dev,code-reviewer,_lib}/` populados com os 8 scripts Python; `.claude/hooks/` vazio; plugin TS aponta para os novos paths; `PROJECT_ROOT` em `_lib/*.py` continua resolvendo para o DFe-Agent root; suite de testes de hooks verde.

### Task 1.1 — Mover `.claude/hooks/{dev,code-reviewer,_lib}/` → `.opencode/hooks/`

- Operação:
  ```
  Move-Item .claude/hooks/dev .opencode/hooks/dev
  Move-Item .claude/hooks/code-reviewer .opencode/hooks/code-reviewer
  Move-Item .claude/hooks/_lib .opencode/hooks/_lib
  ```
- Limpar `__pycache__/` que vem junto.
- Validar que `PROJECT_ROOT` em `_lib/{learning,payload,test_runner}.py` (linhas 45, 31, 29 respectivamente) ainda calcula `parents[3]` corretamente:
  - `.opencode/hooks/_lib/learning.py` → `parents[3]` = `<PROJECT_ROOT>` ✓ (3 níveis: `.opencode/hooks/_lib/`)
  - Igual para `payload.py` e `test_runner.py`.
- Cobertura nova (TDD vermelho primeiro):
  - `tests/unit/hooks/test_path_safety.py` (novo, gate anti-regressão):
    - `test_learning_project_root_resolves_to_dfe_agent_root`: confirma
      `learning.PROJECT_ROOT.name == "DFe-Agent"` (não `"opencode"`).
    - `test_payload_project_root_resolves_to_dfe_agent_root`: idem para
      `payload.PROJECT_ROOT`.
    - `test_test_runner_project_root_resolves_to_dfe_agent_root`: idem
      para `test_runner.PROJECT_ROOT`.
    - `test_knowledge_dir_after_migration_is_opencode_rag_knowledge`:
      confirma `_knowledge_dir()` retorna
      `<PROJECT_ROOT>/.opencode/rag/knowledge/` (novo path).
    - `test_log_path_after_migration_is_storage_root`: confirma
      `LOG_PATH` retorna `<PROJECT_ROOT>/storage/agent_hooks.log`
      (path raiz, não dentro de `.opencode/`).
- Critérios de aceitação:
  - [x] 3 diretórios movidos.
  - [x] `PROJECT_ROOT` ainda resolve para DFe-Agent root.
  - [x] `test_path_safety.py` verde com 5 testes.
  - [x] Suite completa ainda passa (monkeypatched tests em `test_learning_helper.py` continuam ok porque monkeypatcham via `tmp_path`).

### Task 1.2 — Atualizar `.opencode/plugin/agent-hooks.ts:46-56`

- Trocar paths hardcoded:
  ```diff
  "code-reviewer": {
    slug: "code-reviewer",
  - preToolUse: ".claude/hooks/code-reviewer/pre_tool_use.py",
  - preToolUseBash: ".claude/hooks/code-reviewer/pre_tool_use_bash.py",
  + preToolUse: ".opencode/hooks/code-reviewer/pre_tool_use.py",
  + preToolUseBash: ".opencode/hooks/code-reviewer/pre_tool_use_bash.py",
  },
  "dev": {
    slug: "dev",
  - preToolUse: ".claude/hooks/dev/pre_tool_use.py",
  - postToolUse: ".claude/hooks/dev/post_tool_use.py",
  - stop: ".claude/hooks/dev/stop.py",
  + preToolUse: ".opencode/hooks/dev/pre_tool_use.py",
  + postToolUse: ".opencode/hooks/dev/post_tool_use.py",
  + stop: ".opencode/hooks/dev/stop.py",
  },
  ```
- Atualizar comentário do cabeçalho (linha 1-3): "os scripts Python em `.claude/hooks/<agent>/`" → "os scripts Python em `.opencode/hooks/<agent>/`".
- Cobertura (TDD):
  - `tests/integration/test_dev_plugin_dispatch.py::test_dev_profile_has_pre_tool_use` (linha 57):
    trocar asserção `"preToolUse deve apontar para .claude/hooks/dev/pre_tool_use.py"`
    por `".opencode/hooks/dev/pre_tool_use.py"`. Idem para `post_tool_use` (linha 73) e `stop` (linha 86).
  - `test_dev_hook_scripts_exist` (linha 111): trocar
    `PROJECT_ROOT / ".claude" / "hooks" / "dev"` por
    `PROJECT_ROOT / ".opencode" / "hooks" / "dev"`.
  - `test_dev_hooks_pass_python_compile` (linha 118): idem.
  - `tests/integration/test_code_reviewer_plugin_dispatch.py::test_code_reviewer_profile_has_pre_tool_use` (linha 71):
    trocar asserção para `".opencode/hooks/code-reviewer/pre_tool_use.py"`. Idem para `pre_tool_use_bash` (linha 88).
  - `tests/integration/test_agent_dispatch.py::test_code_reviewer_blocks_edit_in_subprocess` (provavelmente
    usa `PROJECT_ROOT / ".claude" / "hooks" / "code-reviewer" / "pre_tool_use.py"`):
    trocar para `.opencode`.
- Critérios de aceitação:
  - [x] `agent-hooks.ts` aponta para `.opencode/hooks/...` em 5 sites.
  - [x] Comentário atualizado.
  - [x] `test_dev_plugin_dispatch.py` verde (4 testes atualizados).
  - [x] `test_code_reviewer_plugin_dispatch.py` verde (2 testes atualizados).
  - [x] `test_agent_dispatch.py` verde (1+ teste atualizado).

### Task 1.3 — Atualizar `tests/unit/hooks/test_*.py` para novo path

- `tests/unit/hooks/test_payload.py:22`: `PAYLOAD_LIB: Path = PROJECT_ROOT / ".claude" / "hooks" / "_lib" / "payload.py"`
  → `PROJECT_ROOT / ".opencode" / "hooks" / "_lib" / "payload.py"`.
- `tests/unit/hooks/test_learning_helper.py:30`: idem para `learning.py`.
- `tests/unit/hooks/test_test_runner.py:21`: idem para `test_runner.py`.
- `tests/unit/hooks/test_dev_pre_tool_use.py:33`:
  `HOOK_SCRIPT: Path = PROJECT_ROOT / ".claude" / "hooks" / "dev" / "pre_tool_use.py"`
  → `.opencode/hooks/dev/pre_tool_use.py`.
- `tests/unit/hooks/test_dev_pre_tool_use.py:172-174`: testes que verificam
  bloqueio de `npx tsx .claude/scripts/embed.ts --file .claude/knowledge/x.md` —
  trocar para `.opencode/rag/embed.ts --file .opencode/rag/knowledge/x.md`.
- `tests/unit/hooks/test_dev_pre_tool_use.py:226-227`: asserções sobre
  caminhos `.claude/agents/dev.md` e `.claude/hooks/dev/pre_tool_use.py`
  — trocar para `.opencode/agent/dev.md` e `.opencode/hooks/dev/pre_tool_use.py`.
- `tests/unit/hooks/test_code_reviewer_pre_tool_use.py:25`: trocar path
  do hook script.
- `tests/unit/hooks/test_code_reviewer_pre_tool_use_bash.py:24`: idem.
- `tests/unit/hooks/test_code_reviewer_pre_tool_use_bash.py:96-98`
  (`test_blocks_claude_rag_db_path`): agora o path é
  `.opencode/rag/rag.db` em vez de `.claude/rag.db`. Renomear teste
  para `test_blocks_opencode_rag_db_path` (muda semântica) e atualizar
  comando testado de `sqlite3 .claude/rag.db .tables` para
  `sqlite3 .opencode/rag/rag.db .tables`.
- `tests/unit/test_code_reviewer_definition.py:170-179`: asserções que
  verificam o corpo do agent `code-reviewer` cita
  `.claude/hooks/code-reviewer/...` — atualizar para
  `.opencode/hooks/code-reviewer/...` (Feito na Fase 4 quando o agent
  text for atualizado; este teste protege contra drift, então move junto).
- Critérios de aceitação:
  - [x] 8 arquivos de teste atualizados.
  - [x] `test_code_reviewer_pre_tool_use_bash.py` ganham novo path
        `.opencode/rag/rag.db`.
  - [x] Suite verde (`pytest tests/unit/hooks/` exit 0).

### Task 1.4 — Atualizar `tests/integration/test_no_legacy_agents.py`

- Reescrever completamente. Hoje cobre `.claude/agents/` e `.claude/hooks/`
  com 7 testes. Migrar para `.opencode/harness_no_legacy_test.py` (ou
  manter filename mas reescrever):
  - `test_only_canonical_agents_in_opencode_agent_dir`:
    lista `.opencode/agent/*.md` e confirma que só `dev.md`,
    `code-reviewer.md`, `dfe-agent.md` existem.
  - `test_only_canonical_hooks_in_opencode_hooks_dir`:
    lista `.opencode/hooks/*/` (excluindo `_lib/`, `dev/`,
    `code-reviewer/`, e arquivos soltos `allowed_domains.py`,
    `domain_guard.py`, `__init__.py`, `README.md`) e confirma vazio.
  - `test_no_claude_dir_exists`: `not (PROJECT_ROOT / ".claude").exists()`.
  - `test_no_dot_claude_reference_in_opencode_dir`: `grep -r ".claude/" .opencode/`
    retorna vazio.
  - `test_no_dot_claude_reference_in_opencode_json`: `opencode.json`
    não cita `.claude/`.
  - `test_no_dot_claude_reference_in_agents_md`: `grep -r ".claude/" .opencode/agent/`
    retorna vazio.
  - `test_no_dot_claude_reference_in_commands_md`: idem para `.opencode/command/`.
- Cobertura adicional:
  - `test_no_dot_claude_reference_in_AGENTS_md`: `grep ".claude/" AGENTS.md`
    retorna vazio (Fase 6 atualiza AGENTS.md, este teste verifica).
- Critérios de aceitação:
  - [x] 8 testes reescritos/migrados.
  - [x] Suite verde.

---

## Fase 2 — Mover scripts TS do RAG meta-cognitivo para `.opencode/rag/` (B12.1 + B12.4 + I12.2, BLOQUEANTE)

**Critério**: `.opencode/rag/{init_db,summarize,embed,search,smoke_test}.ts` populados; `.opencode/rag/lib/{db,chunker,embedder,classifier}.ts` populados; `_lib/learning.py` aponta para os novos paths; `init_db.ts` cria DB em `.opencode/rag/rag.db`; smoke test E2E verde.

### Task 2.1 — Mover `.claude/scripts/*.ts` → `.opencode/rag/*.ts`

- Operação:
  ```
  New-Item -ItemType Directory -Path .opencode/rag
  Move-Item .claude/scripts/init_db.ts .opencode/rag/init_db.ts
  Move-Item .claude/scripts/summarize.ts .opencode/rag/summarize.ts
  Move-Item .claude/scripts/embed.ts .opencode/rag/embed.ts
  Move-Item .claude/scripts/search.ts .opencode/rag/search.ts
  Move-Item .claude/scripts/smoke_test.ts .opencode/rag/smoke_test.ts
  ```
- Atualizar imports internos: cada `.ts` importa `./lib/<module>.ts` —
  path relativo permanece válido (mesma estrutura `lib/` dentro de `rag/`).
- Critérios de aceitação:
  - [x] 5 scripts movidos.

### Task 2.2 — Mover `.claude/scripts/lib/` → `.opencode/rag/lib/`

- Operação:
  ```
  Move-Item .claude/scripts/lib .opencode/rag/lib
  ```
- Atualizar `db.ts:19-33` (mudança crítica — paths relativos mudam):
  ```diff
  - export const DEFAULT_DB_PATH: string = resolve(__dirname, "..", "..", "rag.db");
  + export const DEFAULT_DB_PATH: string = resolve(__dirname, "..", "rag.db");
  - export const SCHEMA_PATH: string = resolve(__dirname, "..", "..", "schema.sql");
  + export const SCHEMA_PATH: string = resolve(__dirname, "..", "schema.sql");
  - export const KNOWLEDGE_DIR: string = resolve(__dirname, "..", "..", "knowledge");
  + export const KNOWLEDGE_DIR: string = resolve(__dirname, "..", "knowledge");
  ```
  - Justificativa: `__dirname` é `.opencode/rag/lib/`. `..` sobe para `.opencode/rag/`. `rag.db` é irmão de `lib/`. Antes (`__dirname = .claude/scripts/lib/`), `..`,`..` subia para `.claude/`, e `rag.db` ia para `.claude/rag.db`.
- Atualizar `lib/README.md` (linhas 13-32): trocar `.claude/rag.db` → `.opencode/rag/rag.db`, `.claude/scripts/` → `.opencode/rag/`.
- Critérios de aceitação:
  - [x] `lib/` movido.
  - [x] `db.ts` com 3 paths atualizados.
  - [x] `lib/README.md` com paths textuais atualizados.

### Task 2.3 — Atualizar referências textuais nos scripts TS

- `summarize.ts:1, 169, 238`: comentário de cabeçalho `.claude/scripts/summarize.ts` → `.opencode/rag/summarize.ts`.
- `summarize.ts:193-203` (`deriveOutputPath`): `process.cwd(), ".claude", "knowledge"` → `process.cwd(), ".opencode", "rag", "knowledge"`.
- `summarize.ts:169`: linha `> Extraido automaticamente de transcript via .claude/scripts/summarize.ts` → `.opencode/rag/summarize.ts`.
- `embed.ts:1-7` (cabeçalho): trocar `.claude/rag.db` → `.opencode/rag/rag.db`; `.claude/scripts/embed.ts` → `.opencode/rag/embed.ts`; `.claude/knowledge/` → `.opencode/rag/knowledge/`.
- `embed.ts:62-70` (`printHelp`): atualizar exemplos de uso.
- `search.ts:1-23` (cabeçalho): trocar `.claude/scripts/search.ts` → `.opencode/rag/search.ts`. O JSON de saída cita `path: ".claude/knowledge/2026-08-25-backend.md"` — atualizar para `.opencode/rag/knowledge/...` (mas é só exemplo, então manter coerência).
- `init_db.ts:1, 7`: comentário `.claude/scripts/init_db.ts` → `.opencode/rag/init_db.ts`. Imprime `KNOWLEDGE_DIR` (vem de `db.ts`, então já atualizado pela Task 2.2).
- `smoke_test.ts:1, 17`: comentário `.claude/scripts/smoke_test.ts` → `.opencode/rag/smoke_test.ts`. Linha 101 (`mdPath`) hardcoda `.claude/knowledge` → `.opencode/rag/knowledge`. Linha 125-145: caminhos dos subprocessos `.claude/scripts/{summarize,embed,search}.ts` → `.opencode/rag/{summarize,embed,search}.ts`.
- Cobertura (TDD — não há teste para estes comentários, mas há teste para `smoke_test` end-to-end se rodar):
  - Sem teste unitário; validação manual via `npx tsx .opencode/rag/smoke_test.ts` exit 0 (depende de modelo ONNX baixado, pular se ausente).
- Critérios de aceitação:
  - [x] 5 scripts com cabeçalhos e help text atualizados.
  - [x] `smoke_test.ts` com 3 paths de subprocesso atualizados.

### Task 2.4 — Atualizar `_lib/learning.py` para os novos paths TS

- Linhas 233, 278: `.claude/scripts/summarize.ts` → `.opencode/rag/summarize.ts`. `.claude/scripts/embed.ts` → `.opencode/rag/embed.ts`.
- Linha 46: `KNOWLEDGE_DIR: Path = PROJECT_ROOT / ".claude" / "knowledge"` → `PROJECT_ROOT / ".opencode" / "rag" / "knowledge"`.
- Linha 48: `SCRIPTS_DIR: Path = PROJECT_ROOT / ".claude" / "scripts"` → `PROJECT_ROOT / ".opencode" / "rag"`.
- Linha 53-59: `_knowledge_dir()` retorna `PROJECT_ROOT / ".claude" / "knowledge"` → `PROJECT_ROOT / ".opencode" / "rag" / "knowledge"`.
- Linha 200 (docstring): mesma atualização.
- Cobertura nova (TDD):
  - `tests/unit/hooks/test_learning_helper.py:55`: asserção
    `marker.parent == learning.PROJECT_ROOT / ".claude" / "knowledge"`
    → `learning.PROJECT_ROOT / ".opencode" / "rag" / "knowledge"`.
  - `test_learning_helper.py:183`: idem.
  - Adicionar teste novo: `test_knowledge_dir_uses_opencode_rag_path` confirma
    `_knowledge_dir() == PROJECT_ROOT / ".opencode" / "rag" / "knowledge"`.
  - Adicionar teste novo: `test_scripts_dir_uses_opencode_rag_path` confirma
    `SCRIPTS_DIR == PROJECT_ROOT / ".opencode" / "rag"`.
- Critérios de aceitação:
  - [x] 5 sites em `learning.py` atualizados.
  - [x] 2 testes novos em `test_learning_helper.py` verdes.

### Task 2.5 — Atualizar `_lib/learning.py` para invocar TS pelos novos paths

- Linhas 230-239 (`summarize_args`): o argumento `.claude/scripts/summarize.ts`
  → `.opencode/rag/summarize.ts`.
- Linhas 275-283 (`embed_args`): idem para `.opencode/rag/embed.ts`.
- Cobertura nova (TDD):
  - Em `test_learning_helper.py`, novo teste
    `test_spawn_summarize_invokes_opencode_rag_summarize`: stub `subprocess.run`
    via `monkeypatch`, captura `args`, valida que inclui
    `.opencode/rag/summarize.ts` (não `.claude/scripts/...`).
- Critérios de aceitação:
  - [x] 2 args literal atualizados.
  - [x] 1 teste novo verde.

### Task 2.6 — Migrar artefatos runtime `.claude/{knowledge,rag.db,schema.sql}` → `.opencode/rag/`

- Operação:
  ```
  New-Item -ItemType Directory -Path .opencode/rag/knowledge
  Move-Item .claude/knowledge/2026-08-25-backend-engineer.md .opencode/rag/knowledge/
  Move-Item .claude/knowledge/2026-08-26-feature-code-reviewer-hardening.md .opencode/rag/knowledge/
  Move-Item .claude/knowledge/2026-08-26-feature-plan-sprint11.md .opencode/rag/knowledge/
  Move-Item .claude/knowledge/2026-08-26-sprint-8-meta-rag.md .opencode/rag/knowledge/
  Move-Item .claude/schema.sql .opencode/rag/schema.sql
  # rag.db* sera regenerado por init_db.ts; mover para tras ou ignorar
  Move-Item .claude/rag.db .opencode/rag/rag.db
  Move-Item .claude/rag.db-shm .opencode/rag/rag.db-shm
  Move-Item .claude/rag.db-wal .opencode/rag/rag.db-wal
  ```
- NÃO mover `_pending-*.md.lock` (2 arquivos) — markers idempotentes
  devem ser regenerados para a nova sessão.
- Após mover, rodar `npx tsx .opencode/rag/init_db.ts` para validar
  que o schema é aplicado corretamente no novo path.
- Critérios de aceitação:
  - [x] 4 `.md` de conhecimento migrados.
  - [x] `schema.sql` migrado.
  - [x] `rag.db*` migrado (3 arquivos).
  - [x] `init_db.ts` roda com exit 0.

---

## Fase 3 — Mover agents stub + rules para `.opencode/` (B12.2 + B12.3 + I12.1, BLOQUEANTE)

**Critério**: `.claude/agents/` e `.claude/rules/` apagados; agents/commands/plugins/scripts citam apenas paths em `.opencode/`; `opencode.json > instructions` aponta para `.opencode/rules/*.md`; agentes `dev`, `code-reviewer`, `dfe-agent` continuam funcionais.

### Task 3.1 — Mover `.claude/rules/{4 arquivos}.md` → `.opencode/rules/`

- Operação:
  ```
  Move-Item .claude/rules/seguranca.md .opencode/rules/seguranca.md
  Move-Item .claude/rules/convencoes-gerais.md .opencode/rules/convencoes-gerais.md
  Move-Item .claude/rules/src.md .opencode/rules/src.md
  Move-Item .claude/rules/tests.md .opencode/rules/tests.md
  ```
- Sem mudança de conteúdo (apenas path).
- Critérios de aceitação:
  - [x] 4 rules movidas.

### Task 3.2 — Atualizar `opencode.json > instructions`

- Trocar paths hardcoded:
  ```diff
  "instructions": [
  -   ".claude/rules/seguranca.md",
  -   ".claude/rules/convencoes-gerais.md",
  -   ".claude/rules/src.md",
  -   ".claude/rules/tests.md",
  +   ".opencode/rules/seguranca.md",
  +   ".opencode/rules/convencoes-gerais.md",
  +   ".opencode/rules/src.md",
  +   ".opencode/rules/tests.md",
     "AGENTS.md"
  ]
  ```
- Cobertura nova (TDD):
  - `tests/integration/test_opencode_config.py` (novo arquivo):
    - `test_instructions_references_opencode_rules_only`:
      parseia `opencode.json` e valida que `instructions` lista apenas
      paths em `.opencode/rules/` (e `AGENTS.md`).
    - `test_plugin_path_references_opencode_plugin_only`:
      valida que `plugin[0]` começa com `.opencode/`.
- Critérios de aceitação:
  - [x] `opencode.json` com 4 paths `.opencode/rules/` (sem `.claude/`).
  - [x] `test_opencode_config.py` verde (2 testes).

### Task 3.3 — Apagar `.claude/agents/{dev,code-reviewer}.md`

- Operação:
  ```
  Remove-Item .claude/agents/dev.md
  Remove-Item .claude/agents/code-reviewer.md
  Remove-Item .claude/agents  # diretório vazio
  ```
- Justificativa: duplicatas 95% (ver Task 1.4 de Sprint 11 I11.1 + análise inicial C3).
- O conteúdo distinto dessas duplicatas (documentação de hooks) migrou para
  a definição canônica `.opencode/agent/*.md` em Sprints 9-10. Os frontmatter
  `hooks:` são ignorados pelo opencode CLI.
- Cobertura (TDD):
  - Já coberto por `test_no_legacy_agents.py::test_only_canonical_agents_in_opencode_agent_dir`
    (reescrito em Task 1.4) e gate `test_no_claude_dir_exists`.
- Critérios de aceitação:
  - [x] 2 arquivos apagados.
  - [x] Diretório `.claude/agents/` removido.

---

## Fase 4 — Atualizar comandos + plugin TS + opencode.json (B12.1 + I12.1, BLOQUEANTE)

**Critério**: `.opencode/command/{feature,bug,duvida}.md` citam apenas paths `.opencode/`; `.opencode/agent/*.md` idem; `.opencode/plugin/agent-hooks.ts` sem referências textuais a `.claude/`; `.opencode/skills/dfe-fiscal/SKILL.md` idem; `tests/unit/test_commands_definitions.py` verde.

### Task 4.1 — Atualizar `.opencode/command/feature.md`

- Trocar todas as 16 ocorrências (linhas 26, 28, 141, 210, 252, 277, 294,
  306, 316, 320, 323, 335, 359, 362, 370, 408):
  - `npx tsx .claude/scripts/{embed,search,summarize}.ts` → `npx tsx .opencode/rag/{embed,search,summarize}.ts`.
  - `.claude/knowledge/<...>.md` → `.opencode/rag/knowledge/<...>.md`.
  - `.claude/rules/*.md` → `.opencode/rules/*.md` (linha 210).
- Cobertura (TDD):
  - `tests/unit/test_commands_definitions.py::test_feature_command_phase0_invokes_search_ts`
    (linha 81) — assertion
    `"`/` deve invocar `.claude/scripts/search.ts` na Fase 0."` →
    `".opencode/rag/search.ts"`. Idem para embed (linha 93, 95).
- Critérios de aceitação:
  - [x] 16 sites atualizados.
  - [x] `test_commands_definitions.py` verde (3+ testes).

### Task 4.2 — Atualizar `.opencode/command/bug.md`

- 12 ocorrências (linhas 29, 31, 38, 70, 201, 244, 262, 294, 307, 309, 322,
  349, 352, 357):
  - Mesmo padrão da Task 4.1: `.claude/scripts/`, `.claude/knowledge/`,
    `.claude/rules/`, `.claude/rag.db`, `.claude/` (refs gerais).

### Task 4.3 — Atualizar `.opencode/command/duvida.md`

- 16 ocorrências (linhas 29, 30, 37, 52, 55, 56, 57, 64, 81, 140, 145, 175,
  183, 185, 201, 235):
  - Mesmo padrão.

### Task 4.4 — Atualizar `.opencode/agent/dev.md`

- 11 ocorrências (linhas 3, 30, 52, 67, 69, 78, 79, 83, 108, 120):
  - `.claude/` → `.opencode/` (refs gerais em texto).
  - `npx tsx .claude/scripts/search.ts` → `.opencode/rag/search.ts`.
  - `.claude/hooks/dev/pre_tool_use.py` → `.opencode/hooks/dev/pre_tool_use.py`.

### Task 4.5 — Atualizar `.opencode/agent/code-reviewer.md`

- 3 ocorrências (linhas 83, 86, 90):
  - `.claude/hooks/code-reviewer/pre_tool_use.py` → `.opencode/hooks/code-reviewer/pre_tool_use.py`.
  - `.claude/rag.db` → `.opencode/rag/rag.db`.

### Task 4.6 — Atualizar `.opencode/agent/README.md` (já menciona duplicatas)

- Linhas 11, 17-19, 22, 25, 28, 33:
  - Remover referências a `.claude/agents/` (duplicatas removidas em 3.3).
  - Atualizar `.claude/hooks/` → `.opencode/hooks/`.
  - Reescrever "Hooks (definidos em `.claude/hooks/dev/`)" →
    "Hooks (definidos em `.opencode/hooks/dev/`)".
  - Manter nota: "**Path canônico**: `.opencode/agent/` (singular) — duplicatas em `.claude/agents/` foram removidas em Sprint 12."

### Task 4.7 — Atualizar `.opencode/README.md`

- Linhas 8-17, 25-26:
  - Trocar `.claude/` → `.opencode/` (refs gerais).
  - Atualizar estrutura para refletir o novo layout (incluir `.opencode/rag/`).
- Manter coerência com a consolidação: nota no topo sobre "Sprint 12 unificou
  todo o harness em `.opencode/`".

### Task 4.8 — Atualizar `.opencode/command/README.md`

- Linhas 15-18, 46-47, 51:
  - `.claude/scripts/`, `.claude/hooks/dev/stop.py`, `.claude/agents/`,
    `.claude/rules/` → `.opencode/`.
- Reescrever para refletir o estado pós-Sprint 12.

### Task 4.9 — Atualizar `.opencode/agent/dfe-agent.md`

- Verificar se cita `.claude/`. (Linha 44-47 cita `.opencode/skills/dfe-fiscal/SKILL.md` — já canônico.)
- Não deve haver mudanças; só validar com `grep`.

### Task 4.10 — Atualizar `.opencode/skills/dfe-fiscal/SKILL.md`

- Verificar refs `.claude/`. (Linhas 116, 134 citam regras genéricas; provável zero hits.)

### Task 4.11 — Cobertura gates em `tests/unit/test_commands_definitions.py`

- Já existem 3 testes atualizados em Task 4.1. Adicionar:
  - `test_feature_command_mentions_opencode_rag_path`: assert `.opencode/rag/` aparece no body.
  - `test_no_command_references_legacy_claude_path`: parametrized em [feature, bug, duvida] — grep `\.claude/` retorna 0 hits em cada.

### Task 4.12 — Atualizar `.opencode/plugin/agent-hooks.ts` comentários

- Linha 3: "os scripts Python em `.claude/hooks/<agent>/`" → `.opencode/hooks/<agent>/`.
- Linhas 11-12 (paragrafo sobre agents legacy removidos): atualizar paths.
- Linha 24: "DFE_ACTIVE_AGENT no env do shell" — sem mudança.

### Task 4.13 — Atualizar `tests/unit/test_code_reviewer_definition.py`

- Linhas 170-179 (asserções sobre `.claude/hooks/code-reviewer/...`):
  - Trocar para `.opencode/hooks/code-reviewer/...`.

### Task 4.14 — Atualizar `tests/integration/test_learning_stop_hook.py`

- Mover `tmp_path / ".claude" / "knowledge"` (6 ocorrências: linhas 72, 110, 147, 181, 221, 260) → `tmp_path / ".opencode" / "rag" / "knowledge"`.
- Adaptar imports/loads do `.claude/hooks/dev/AGENT_DIR/hook_name` (linha 35) → `.opencode/hooks/dev/AGENT_DIR/hook_name`.

### Task 4.15 — Atualizar `tests/integration/test_dev_stop_hook.py`

- Linha 27: `HOOK_SCRIPT: Path = PROJECT_ROOT / ".claude" / "hooks" / "dev" / "stop.py"` → `.opencode`.

---

## Fase 5 — Apagar `.claude/` residual (B12.5 + B12.6 + I12.3, BLOQUEANTE)

**Critério**: `.claude/` não existe mais no projeto; nenhum arquivo órfão (state/, .cache/, scripts/ órfãos); nenhum teste referencia `.claude/`; `grep -r ".claude/" .` retorna vazio (exceto matches históricos em comentários de plano/knowledge antigos).

### Task 5.1 — Apagar skill legado `.claude/skills/dfe-agent-runner/SKILL.md`

- Operação: `Remove-Item -Recurse .claude/skills`.
- Justificativa: skill órfã (citada por nenhum agent/command); conteúdo
  cita `confaz.fazenda.gov.br` removido em Sprint 4 D.1 e "rule 3" removida
  em Sprint 11 D.4. Funcionalidade equivalente em `.opencode/skills/dfe-fiscal/SKILL.md`.

### Task 5.2 — Apagar scripts órfãos `.claude/scripts/test_hooks.py` + `demo_agent_hooks.py`

- Operação: `Remove-Item .claude/scripts/test_hooks.py` + `demo_agent_hooks.py`.
- Justificativa: legados pré-Sprint 11; testavam `learning_*.py` órfãos (removidos em Sprint 11 B11.2). Cobertos por testes pytest atuais.
- Cuidado: `.claude/scripts/lib/` foi movido na Fase 2. Os arquivos
  `test_hooks.py` e `demo_agent_hooks.py` ficam sozinhos em
  `.claude/scripts/` antes desta task.

### Task 5.3 — Apagar `.claude/state/` (94 JSONs de runtime)

- Operação: `Remove-Item -Recurse .claude/state`.
- Justificativa: artefatos de runtime de `learning_prompt_submit.py` (removido em Sprint 11 B11.2). Regeneráveis se hook for reativado.
- Sem teste de cobertura (estado runtime); validação: `not (.claude/state).exists()`.

### Task 5.4 — Apagar `.claude/.cache/` (legado)

- Operação: `Remove-Item -Recurse .claude/.cache`.
- Justificativa: cache de smoke test pré-Sprint 11.

### Task 5.5 — Apagar `.claude/storage/agent_hooks.log` + diretório vazio

- Operação: `Remove-Item .claude/storage/agent_hooks.log` + `Remove-Item .claude/storage`.
- Justificativa: log legado pré-Sprint 11; logs novos vão para
  `<PROJECT_ROOT>/storage/agent_hooks.log` (root, já configurado em
  `payload.py::log_event`).

### Task 5.6 — Apagar `.claude/README.md`

- Operação: `Remove-Item .claude/README.md`.
- Justificativa: conteúdo mergeado em `.opencode/README.md` na Fase 4.

### Task 5.7 — Apagar `.claude/` se vazio

- Operação: `Remove-Item .claude` (só se Tasks 5.1-5.6 + Fases 1-3 removeram tudo).
- Gate: `not (PROJECT_ROOT / ".claude").exists()` (já coberto por `test_no_claude_dir_exists` em Task 1.4).

### Task 5.8 — Apagar `__pycache__/` órfãos

- Após mover scripts TS e Python, rodar busca de `__pycache__/` em
  paths que foram removidos. Limpar via `Remove-Item -Recurse` (ou
  adicionar `__pycache__/` ao `.gitignore` se ainda não estiver).

---

## Fase 6 — Documentação canônica + AGENTS.md (B12.1, BLOQUEANTE)

**Critério**: AGENTS.md sem referências a `.claude/`; novo bloco "Decisões resolvidas (Sprint 12)" adiciona 6-8 bullets com paths de evidência; `.opencode/README.md` é a doc única do harness.

### Task 6.1 — Atualizar AGENTS.md

- Substituir seção `## Sistema de RAG meta-cognitivo (.claude/)` →
  `## Sistema de RAG meta-cognitivo (.opencode/rag/)`.
- Substituir seção `## Estrutura de pastas` (referências a `.claude/`)
  por layout unificado em `.opencode/`.
- Remover/setar como deprecated qualquer referência textual a `.claude/`
  exceto em contexto histórico (sprints passados).
- Adicionar bloco `## Decisões resolvidas (Sprint 12)` com bullets:
  - `.claude/` apagado; harness consolidado em `.opencode/`.
  - Hooks Python vivem em `.opencode/hooks/{dev,code-reviewer,_lib}/`.
  - Scripts TS do RAG meta-cognitivo vivem em `.opencode/rag/{*.ts, lib/}`.
  - Rules vivem em `.opencode/rules/`; `opencode.json > instructions` ajustado.
  - Skill `dfe-agent-runner` removida (legado, conteúdo obsoleto).
  - Agents stub `.claude/agents/{dev,code-reviewer}.md` removidos
    (canonical em `.opencode/agent/`; opencode CLI ignora frontmatter `hooks:`).
- Cobertura (TDD):
  - `test_no_dot_claude_reference_in_AGENTS_md` (Task 1.4) — verde.
  - Adicionar teste `test_AGENTS_md_has_sprint12_decisions_block`:
    confirma `## Decisões resolvidas (Sprint 12)` no AGENTS.md.

### Task 6.2 — Atualizar `.opencode/README.md`

- Reescrever seção "Estrutura" para refletir layout unificado:
  ```
  .opencode/
  ├── agent/             # Definicoes canonicas de agents (Sprint 12 consolida .claude/agents/)
  ├── command/           # Slash commands (/feature, /bug, /duvida)
  ├── hooks/             # Hooks Python por agent (dev/, code-reviewer/) + guardrails (domain_guard.py, allowed_domains.py)
  ├── plugin/            # Plugin TS (.opencode/plugin/agent-hooks.ts)
  ├── rag/               # RAG meta-cognitivo (scripts TS + rag.db + knowledge/) — antes em .claude/
  ├── rules/             # Rules carregadas via opencode.json > instructions
  ├── skills/            # Skills canonicas (dfe-fiscal)
  └── node_modules/      # Deps Node (gitignored)
  ```

### Task 6.3 — Atualizar `.opencode/agent/README.md`

- Reescrever seção "Agents relacionados em outros paths" (linhas 13-19).
  Remover entradas de `.claude/agents/` (apagadas em 3.3).
- Atualizar "Hooks (definidos em `.opencode/hooks/dev/`)" (linhas 25-34)
  para refletir o novo path.

---

## Fase 7 — Gate anti-regressão (B12.1, BLOQUEANTE)

**Critério**: 8+ testes em `tests/integration/test_unified_harness.py` (novo) bloqueiam qualquer regressão futura; suite verde; cobertura mantida.

### Task 7.1 — Criar `tests/integration/test_unified_harness.py`

Consolida e expande os gates de regressão. Testes:

- `test_no_dot_claude_dir_exists`:
  `assert not (PROJECT_ROOT / ".claude").exists()`.
- `test_no_dot_claude_in_opencode_subtree`:
  `grep -rE "\.claude/(agents|hooks|rules|skills|scripts|state|knowledge|storage|rag\.db|schema\.sql)" .opencode/`
  retorna vazio.
- `test_no_dot_claude_in_agents_md`:
  `grep ".claude/" .opencode/agent/*.md` retorna vazio.
- `test_no_dot_claude_in_commands_md`:
  `grep ".claude/" .opencode/command/*.md` retorna vazio.
- `test_no_dot_claude_in_plugin_ts`:
  `grep ".claude/" .opencode/plugin/*.ts` retorna vazio.
- `test_no_dot_claude_in_rag_ts`:
  `grep ".claude/" .opencode/rag/*.ts .opencode/rag/lib/*.ts` retorna vazio.
- `test_no_dot_claude_in_opencode_json`:
  parseia `opencode.json` e valida zero refs a `.claude/`.
- `test_no_dot_claude_in_AGENTS_md`:
  `grep ".claude/" AGENTS.md` retorna vazio.
- `test_opencode_hooks_has_5_scripts`:
  lista `.opencode/hooks/{dev,code-reviewer,_lib}/*.py` e confirma
  exatamente 5 scripts (pre/post/stop + pre + pre_bash) + 3 lib (learning, payload, test_runner).
- `test_opencode_rag_has_5_scripts_and_4_lib`:
  lista `.opencode/rag/*.ts` (5) e `.opencode/rag/lib/*.ts` (4: db, chunker, embedder, classifier).
- `test_plugin_ts_points_to_opencode_hooks`:
  parseia `agent-hooks.ts` e valida que 5 paths hardcoded começam com `.opencode/hooks/`.
- `test_learning_helper_paths_use_opencode_rag`:
  importa `_lib/learning.py` e valida `KNOWLEDGE_DIR` e `SCRIPTS_DIR` apontam para `.opencode/rag/`.
- `test_opencode_init_db_creates_db_in_opencode_rag`:
  roda `npx tsx .opencode/rag/init_db.ts` em `tmp_path`, valida que `rag.db` é criado em `<tmp_path>/.opencode/rag/`.
- `test_opencode_rules_count_is_5`:
  lista `.opencode/rules/*.md` e confirma 5 (4 migrados + 1 nativo `dfe-rules.md`).

### Task 7.2 — Atualizar `test_no_legacy_agents.py` para nova realidade

- Hoje (Sprint 11): cobre `.claude/agents/` e `.claude/hooks/` (legacy slugs).
- Migrar para `.opencode/agents/` (que não deve existir) + `.opencode/harness/` (que não deve existir) — gates vazios.
- Manter o nome `test_no_legacy_agents.py` (continua válido como gate).

### Task 7.3 — Adicionar teste de smoke E2E para `.opencode/rag/init_db.ts`

- Roda init_db em tmp_path, verifica que `knowledge/` e `rag.db` foram criados.
- Requer `npx tsx` disponível e `node_modules` instalado.

### Task 7.4 — Atualizar `test_gitignore_opencode.py`

- Hoje cobre `.opencode/node_modules/` (Sprint 11 B11.4).
- Adicionar teste: `test_gitignore_excludes_claude_dir_se_recreated`: cobre
  regressão onde `.claude/` volta por engano (prevenção, mesmo que não exista agora).

---

## Apêndice A — Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| `PROJECT_ROOT` calculation quebrada após mover `_lib/*.py` | Baixa | Alto | Task 1.1 adiciona `test_path_safety.py` com 5 testes de path antes da remoção. `_lib/learning.py:45` usa `parents[3]` que é robusto a mover 3 níveis. |
| `db.ts` paths relativos errados após mover para `.opencode/rag/lib/` | Média | Alto | Task 2.2 atualiza explicitamente. Task 7.1 `test_opencode_init_db_creates_db_in_opencode_rag` valida E2E. |
| Drift entre `.opencode/agent/*.md` e commands/READMEs | Baixa | Médio | Tasks 4.1-4.10 cobrem todos os .md. Phase 7 `test_no_dot_claude_in_*` gates por path. |
| Suite de testes quebra silenciosamente (paths `.claude/` ainda em monkeypatch) | Média | Alto | Phase 7 `test_unified_harness.py` + suite verde obrigatória antes de apagar Fase 5. |
| Schema do rag.db muda (colunas novas) | Muito baixa | Médio | `.claude/schema.sql` migrado verbatim. Sem mudança de conteúdo. |
| `.opencode/state/` ou `.opencode/.cache/` substitui `.claude/state/`/`.cache/` (alguém esquece de limpar) | Baixa | Baixo | Tasks 5.3, 5.4 apagam explicitamente. Phase 7 `test_no_dot_claude_dir_exists` cobre. |
| Plugin TS cacheia paths em runtime (se houver cache) | Muito baixa | Médio | Plugin TS é `await import` dinâmico; sem cache de paths. Reload é trivial. |
| Testes de integração quebram por dependência de `.claude/` em fixtures | Baixa | Médio | Inventário completo de testes (15+ arquivos) listado nas Tasks 1.3, 4.14, 4.15, 7.2. Cada um com path mapping explícito. |
| opencode CLI ainda procura `.claude/rules/` (mecanismo legado) | Muito baixa | Alto | `opencode.json > instructions` é o único mecanismo; atualizado em 3.2. Nenhum fallback para `.claude/rules/`. |

## Apêndice B — Fora de escopo

- **Refatoração interna de `learning.py`** (ex.: usar `asyncio` em vez de
  `subprocess.run`): fora de escopo desta sprint; seria SUGESTÃO para Sprint 13+.
- **Migrar RAG meta-cognitivo para dentro de `src/`** (unificar Python+TS):
  fora de escopo; arquitetura de fronteira é deliberada (Sprint 7 C.1).
- **Reescrever `domain_guard.py` para TypeScript**: fora de escopo;
  `.opencode/hooks/domain_guard.py` é módulo Python vivo importado por
  `src/utils/http_guard.py`.
- **Adicionar `--claude` flag retrocompatível**: fora de escopo; objetivo
  é remover `.claude/` completamente.
- **Mover `.opencode/skills/dfe-fiscal/` para outro path**: fora de escopo;
  path canônico é `.opencode/skills/<kebab>/SKILL.md` (regra de conventions).

## Apêndice C — Comandos shell para reproduzir a sprint

```bash
# 0. Setup
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
npm install --prefix .opencode

# 1. Rodar suite atual (baseline)
pytest tests/ --cov=src --cov-fail-under=80

# 2. Fase 1: mover hooks Python
Move-Item .claude/hooks/dev .opencode/hooks/dev
Move-Item .claude/hooks/code-reviewer .opencode/hooks/code-reviewer
Move-Item .claude/hooks/_lib .opencode/hooks/_lib
# (editar plugin TS, AGENTS.md, e 8+ testes — ver Task 1.2-1.4)
pytest tests/unit/hooks/ tests/integration/test_dev_plugin_dispatch.py tests/integration/test_code_reviewer_plugin_dispatch.py

# 3. Fase 2: mover scripts TS
New-Item -ItemType Directory -Path .opencode/rag
Move-Item .claude/scripts/init_db.ts .opencode/rag/
Move-Item .claude/scripts/summarize.ts .opencode/rag/
Move-Item .claude/scripts/embed.ts .opencode/rag/
Move-Item .claude/scripts/search.ts .opencode/rag/
Move-Item .claude/scripts/smoke_test.ts .opencode/rag/
Move-Item .claude/scripts/lib .opencode/rag/lib
# (editar db.ts: 3 paths; editar learning.py: 5 sites; editar scripts TS)
Move-Item .claude/knowledge/*.md .opencode/rag/knowledge/
Move-Item .claude/schema.sql .opencode/rag/
Move-Item .claude/rag.db .opencode/rag/
npx tsx .opencode/rag/init_db.ts

# 4. Fase 3: mover rules + apagar agents stub
Move-Item .claude/rules/*.md .opencode/rules/
# (editar opencode.json)
Remove-Item .claude/agents/dev.md, .claude/agents/code-reviewer.md, .claude/agents

# 5. Fase 4: atualizar commands, agents, READMEs, plugin TS, testes
# (ver Tasks 4.1-4.15)
pytest tests/unit/

# 6. Fase 5: apagar .claude/ residual
Remove-Item -Recurse .claude/skills
Remove-Item .claude/scripts/test_hooks.py, .claude/scripts/demo_agent_hooks.py
Remove-Item -Recurse .claude/state, .claude/.cache, .claude/storage
Remove-Item .claude/README.md
Remove-Item .claude

# 7. Fase 6: docs + AGENTS.md
# (editar AGENTS.md, .opencode/README.md, .opencode/agent/README.md)

# 8. Fase 7: gate anti-regressão
# (criar tests/integration/test_unified_harness.py)
pytest tests/ --cov=src --cov-fail-under=80
```

## Apêndice D — Decisões de naming

- `.opencode/rag/` vs `.opencode/scripts/` vs `.opencode/meta-rag/`: escolhido `rag/` porque é curto, descritivo e alinhado com `.opencode/rag/rag.db`. Evita colisão com `scripts/` na raiz (`scripts/demo_cli.py` é Python de smoke).
- Manter `.opencode/hooks/` (com hooks Python) em vez de `.opencode/harness/`: coerência com a nomenclatura Sprint 11 (`hooks/` já tem `domain_guard.py` + `allowed_domains.py`). Não criar novo namespace.
- Manter `rules/seguranca.md` filename (kebab/snake conforme origem): decisão pré-existente; sem renomeação.

## Apêndice E — Cobertura nova consolidada

| Teste | Arquivo | Task | Categoria |
|-------|---------|------|-----------|
| `test_learning_project_root_resolves_to_dfe_agent_root` | `tests/unit/hooks/test_path_safety.py` | 1.1 | BLOQUEANTE |
| `test_payload_project_root_resolves_to_dfe_agent_root` | `tests/unit/hooks/test_path_safety.py` | 1.1 | BLOQUEANTE |
| `test_test_runner_project_root_resolves_to_dfe_agent_root` | `tests/unit/hooks/test_path_safety.py` | 1.1 | BLOQUEANTE |
| `test_knowledge_dir_after_migration_is_opencode_rag_knowledge` | `tests/unit/hooks/test_path_safety.py` | 1.1 | BLOQUEANTE |
| `test_log_path_after_migration_is_storage_root` | `tests/unit/hooks/test_path_safety.py` | 1.1 | BLOQUEANTE |
| `test_instructions_references_opencode_rules_only` | `tests/integration/test_opencode_config.py` | 3.2 | BLOQUEANTE |
| `test_plugin_path_references_opencode_plugin_only` | `tests/integration/test_opencode_config.py` | 3.2 | BLOQUEANTE |
| `test_knowledge_dir_uses_opencode_rag_path` | `tests/unit/hooks/test_learning_helper.py` | 2.4 | BLOQUEANTE |
| `test_scripts_dir_uses_opencode_rag_path` | `tests/unit/hooks/test_learning_helper.py` | 2.4 | BLOQUEANTE |
| `test_spawn_summarize_invokes_opencode_rag_summarize` | `tests/unit/hooks/test_learning_helper.py` | 2.5 | BLOQUEANTE |
| `test_AGENTS_md_has_sprint12_decisions_block` | `tests/integration/test_unified_harness.py` | 6.1 | IMPORTANTE |
| `test_no_dot_claude_dir_exists` | `tests/integration/test_unified_harness.py` | 1.4 + 7.1 | BLOQUEANTE |
| 11 testes anti-regressão | `tests/integration/test_unified_harness.py` | 7.1 | BLOQUEANTE |
| `test_feature_command_mentions_opencode_rag_path` | `tests/unit/test_commands_definitions.py` | 4.11 | BLOQUEANTE |
| `test_no_command_references_legacy_claude_path` (3 paramet.) | `tests/unit/test_commands_definitions.py` | 4.11 | BLOQUEANTE |

Total: ~30 testes novos. Suite atual: 599 passed + 1 skipped (Sprint 11). Meta pós-sprint: 629+ passed, 1 skipped.

## Apêndice F — Entregáveis da sprint

- `.claude/` apagado.
- `.opencode/` contém todo o harness (agents, commands, hooks, plugin, rules, skills, rag).
- 30+ testes novos cobrindo paths e regressões.
- AGENTS.md atualizado com bloco "Decisões resolvidas (Sprint 12)".
- Cobertura global >= 80% mantida.
- 0 BLOQUEANTE / 0 IMPORTANTE no code review final.
- `.claude/knowledge/<...>.md` (4 arquivos) preservados em `.opencode/rag/knowledge/` (mesmo conteúdo).
