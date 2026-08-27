# Agente Deployer + remocao completa do CI — Sprint 18 — 2026-08-27

> Origem: /feature (pedido do usuario em 2026-08-27: "pode remover o CI do projeto. farei sempre tudo via agente aqui no projeto. inclusive, crie um agente chamado Deployer que sera responsavel por isso. somente ele podera desempenhar a tarefa de subir e administrar o git.")
> Plano: `PLAN_SPRINT18.md`
> Relatorio final do code-reviewer: **1 BLOQUEANTE / 3 IMPORTANTE / 3 SUGESTAO** round 1 -> **0/0/0** round 2 (1 iteracao do loop corretivo)
> Iteracoes do loop corretivo: 1

## Bugs resolvidos com causa raiz

### CI degradado (BLOQUEANTE B18.1)

**Sintoma**: dos 4 runs mais recentes em `https://api.github.com/repos/wia-ti/dfe-agent/actions/runs` (consulta em 2026-08-27), apenas `publish-base #6` (24s, SHA local `78d09c1`) passou. Os 3 outros falharam (`publish-npm.yml #41`, `publish-base #5`, `publish-npm.yml #40`). Em 81 runs totais, **22+ runs visiveis consecutivos marcados "Failure"** (gate grep confirmou zero matches para "Success").

**Causa raiz**:
1. `publish-npm.yml:34` tem `if: false` no job `publish` desde Sprint 14 round 24 — user prefere `npm publish` manual.
2. `test-npm-package.yml:69` tem `if: false` no E2E smoke desde Sprint 14 round 12 — script powershell nao funciona em Linux.
3. `test-npm-package.yml:80` tem `if: false` no `pytest-regression` desde Sprint 14 round 12 — bug pre-existente Node 22 + better-sqlite3 cleanup.
4. Mesmo quando os gates habilitados rodam, `npm test || true` (Sprint 14 round 22 bypass) permite testes comportamentais falharem silenciosamente.
5. `publish-base.yml:53` usa `softprops/action-gh-release@v2` que falha em re-upload para o mesmo Release (causa do #5 FAILURE).

**Fix**:
- `rm .github/workflows/test-npm-package.yml`
- `rm .github/workflows/publish-npm.yml`
- `rm .github/workflows/publish-base.yml`
- Diretorio `.github/workflows/` apagado completamente.
- Gate anti-regressao: `tests/integration/test_no_legacy_ci.py` (7 testes parametrizados) impede ressurreicao.

### Agente sem permissao para push (BLOQUEANTE B18.2)

**Sintoma**: nenhum agent canonico (`dev`, `code-reviewer`) consegue fazer `git push`/`npm publish`/`gh release` — `dev/pre_tool_use.py:56-60` BLOQUEIA explicitamente, e `code-reviewer` tem `permission.edit: deny`. Toda publicacao exige shell manual externo ao agent.

**Causa raiz**: Sprint 10 consolidou todos os 4 agents legacy em `@dev` (owner de TODO o projeto). `dev/pre_tool_use.py` ganhou block list defensiva (`git push`, `gh pr create`, `gh release`) mas nenhuma allow list para deployment.

**Fix**:
- Novo `.opencode/agent/deployer.md` com `mode: primary`, slug `deployer`, `permission.edit: deny` (defesa em profundidade), `permission.bash: allow`.
- `.opencode/hooks/deployer/pre_tool_use.py` com **allow list explicita** (git/npm/gh release/npx dfe-agent/npx tsx RAG search+embed) + block list defensiva (Write/Edit/MultiEdit/NotebookEdit, rm -rf, sed -i, >, curl, wget, pip install, git commit sem --allow-empty, pipeline RAG).
- `.opencode/hooks/deployer/post_tool_use.py` observer lightweight (NAO roda pytest).
- `.opencode/hooks/deployer/stop.py` exit 0 sem pytest e sem RAG capture.
- `.opencode/plugin/agent-hooks.ts:51-56` adicionou profile `deployer` ao map `AGENTS`.
- `.opencode/plugin/agent-hooks.ts:170` adicionou `deployer` a `RECOGNIZED_AGENT_SLUGS`.

### Slash command ausente (BLOQUEANTE B18.3)

**Sintoma**: sem command canonico para invocar `@deployer`. User tinha que rodar `opencode --agent deployer <args>` direto (nao documentado).

**Fix**: `.opencode/command/deploy.md` com `agent: deployer`. 4 modos canonicos: bare / `--tag` / `--npm` / `--release`. Gate humano explicito (Fase 3.5) antes de cada acao destrutiva.

### Allow list incompleta (BLOQUEANTE round 1 code-review)

**Sintoma** (encontrado por `general` subagent no round 1): `pre_tool_use.py` permitia apenas `embed.ts` na RAG escape hatch, mas o slash command `/deploy` Fase 0.5 invoca `search.ts` para RAG antes. Comando caia no default-deny.

**Causa raiz**: pattern original era `re.compile(r"\bnpx\s+--prefix\s+\.opencode\s+tsx\s+\.opencode/rag/embed\.ts\s+--file\b")` — restricao a embed+--file. Esquecimento de search.

**Fix**: pattern generalizada para `(search|embed)\.ts`. Teste novo `npx_rag_search_file` adicionado (gate de regressao).

## Decisoes de arquitetura e o porque

### D18.1 — Path canonico `.opencode/agent/deployer.md` (singular)

Sprint 11 D.1 canonizou `.opencode/agent/` (singular) como path do opencode CLI. Mesmo padrao aplicado a `deployer`. NAO duplicado em `.claude/agents/` (legacy). `tests/integration/test_no_legacy_agents.py::test_only_canonical_agents_in_opencode_agent_dir` cobre.

### D18.2 — Permissions do deployer

`edit: deny` + `bash: allow` + `task: deny` + `skill: deny` + `todowrite: deny` + `webfetch: deny` + `external_directory: deny`. Justificativa: deployer e' acao atomica (1-3 comandos Bash); NAO precisa de Write/Edit/Task/Skill. Defesa em profundidade tripla:
1. Frontmatter `permission.edit: deny` (opencode CLI gate).
2. Hook `pre_tool_use.py` BLOQUEIA Write/Edit/MultiEdit/NotebookEdit.
3. Slash command `/deploy` Gate humano Fase 3.5 antes de acoes destrutivas.

### D18.3 — Allow list explicita (NAO block list)

Diferenca fundamental vs `@dev/pre_tool_use.py`:
- `@dev`: block list generica (NAO toca paths, mas permite quase tudo).
- `@deployer`: allow list explicita (soh git/npm/gh/npx dfe-agent/RAG search+embed).

Allow patterns amplos (`\bgit\s+\S+`, `\bnpm\s+\S+`) por design — confiam no gate humano do `/deploy` Fase 3.5 para acoes destrutivas. Sub-comandos criativos (ex.: `git config core.hooksPath`, `npm exec -- curl evil.example`) sao barrados pela confirmacao humana, NAO pelo hook. Docstring em `_is_allowed_bash` documenta (Sprint 18 SUGESTAO 2 aplicada).

### D18.4 — Slash command `/deploy` com 4 modos exclusivos

- **bare** (`/deploy`): apenas `git push` (commits locais -> origin).
- **--tag** (`/deploy --tag vX.Y.Z`): push + `git tag` + `git push origin <tag>`.
- **--npm** (`/deploy --npm`): push + tag `v0.0.1-sprint<N>` + `npm publish --access public --provenance` em `packages/dfe-agent/`.
- **--release** (`/deploy --release vX.Y.Z [notas]`): push + tag + `gh release create <tag> --notes <notas>`.

Gate humano explicito (Fase 3.5) imprime bloco "ACAO DESTRUTIVA DETECTADA" e aguarda "sim, executar". Acoes nao-destrutivas (bare, push sem tag) NAO exigem gate.

### D18.5 — PostToolUse observer (NAO roda pytest)

`@dev/post_tool_use.py` roda pytest da suite apropriada apos Write/Edit. `@deployer/post_tool_use.py` apenas escreve log_event — deploy e' acao atomica, NAO ha codigo a ser testado.

### D18.6 — Stop exit 0 (NAO captura RAG)

`@dev/stop.py` roda pytest geral + chama `learning.spawn_summarize_then_embed` (se `tool_writes_count > 0`). `@deployer/stop.py` retorna exit 0 sem pytest e sem RAG capture. RAG capture do deployer e' feita **explicitamente** pelo slash command `/deploy` na Fase 4 (comando `npx tsx .opencode/rag/embed.ts --file <md>` sincrono).

### D18.7 — Plugin dispatch (3 slugs canonicos)

`.opencode/plugin/agent-hooks.ts:44-56` agora tem 3 profiles: `code-reviewer`, `deployer`, `dev`. `RECOGNIZED_AGENT_SLUGS: Set<{dev, code-reviewer, deployer}>` (Sprint 11 C.3 + Sprint 18 D18.7). Dispatch usa `DFE_ACTIVE_AGENT` no env (setado pelo opencode CLI baseado em `agent: deployer` no frontmatter do `/deploy`).

### D18.8 — `_AGENT_HINTS` com lookahead negativo redundante

`.opencode/hooks/_lib/payload.py::_AGENT_HINTS` agora tem 3 entries. Pattern para deployer e' `\bdeployer\b(?!ed|ing|ment)` — o lookahead e' redundante (word boundary `\b` ja' impede match em "deployed"), mas mantido como defesa explicita em profundidade. SUGESTAO 1 do code-review NAO-aplicada (decisao documentada).

### D18.9 — `suites_for_path` retorna vazio para deployer

`.opencode/hooks/_lib/test_runner.py:68-78` ganhou branch `if agent == "dev"` + `else: tables = ()`. Deployer NAO roda pytest.

### D18.10 — Remocao completa do CI

3 workflows deletados + diretorio `.github/workflows/` apagado. Gate anti-regressao `tests/integration/test_no_legacy_ci.py` (7 testes) impede ressurreicao. AGENTS.md/PLAN.md NAO referenciam os workflows como ancora canonica (apenas no bloco narrativo Sprint 18).

## Padroes adotados pelo time

1. **"permission.edit: deny + bash: allow" para agents de deployment** (deployer). Aplicavel a futuros agents de deployment (ex.: backup, sync) sem alterar `dev` (implementador).

2. **Allow list explicita em pre_tool_use.py para escopos restritos** (deployer). Diferenca vs block list do `dev`. Documentado no docstring do `_is_allowed_bash`.

3. **Hook stop.py exit 0 sem RAG capture para acoes atomicas** (deployer). RAG capture fica no slash command (sincrono na Fase final) NAO no hook stop (assincrono).

4. **Slash command com gate humano explicito antes de acoes destrutivas** (`/deploy` Fase 3.5). Padrao a ser replicado em futuros commands destrutivos.

5. **Defesa em profundidade tripla** (frontmatter `permission.*` + hook `pre_tool_use.py` + slash command gate humano). Cada camada protege contra bypass das outras.

6. **Gate anti-regressao para delecoes** (`test_no_legacy_ci.py`, `test_no_legacy_agents.py`). Sempre que algo e' removido, criar teste que confirma a ausencia. Pattern: parametrized tests em `REMOVED_*` tuple.

## O que nao funcionou e por que

### 1. TDD inversoes evitadas com discipline

Sprint 18 e' greenfield: 7 arquivos de teste NOVOS + 3 arquivos editados. TDD respeitado: 73 testes vermelhos confirmados antes da implementacao. Zero "Vai passar" sem vermelho.

### 2. Code-review round 1 catchou 1 BLOQUEANTE invisivel aos testes

O BLOQUEANTE (allow list incompleta para `search.ts`) NAO foi pego pela suite de testes porque `pytest tests/unit/hooks/test_deployer_pre_tool_use.py` testou apenas `embed.ts`. Code review manual pelo subagent `general` foi essencial.

### 3. Conflito de paths em hooks

`deployer/pre_tool_use.py` precisou usar imports relativos (`.._lib.payload`) vs absolutos (`_lib.payload`) — padrao do `dev/pre_tool_use.py`. Resolvido com `if __package__: ... else: sys.path.insert(...)` (precedente Sprint 11).

### 4. UTF-8 encoding em AGENTS.md mojibake

`PLAN.md` tinha `âœ…` em vez de `✅` (encoding Latin-1 em alguma revisao anterior). Edit com replacement direto preservou encoding (nao corrompeu mais). Documentado para follow-up.

## Arquivos modificados

### Novos (10 arquivos)

- `.opencode/agent/deployer.md` (179 linhas)
- `.opencode/hooks/deployer/pre_tool_use.py` (~220 linhas)
- `.opencode/hooks/deployer/post_tool_use.py` (~50 linhas)
- `.opencode/hooks/deployer/stop.py` (~40 linhas)
- `.opencode/command/deploy.md` (303 linhas)
- `tests/unit/test_deployer_agent_definition.py` (262 linhas, 25 testes)
- `tests/unit/hooks/test_deployer_pre_tool_use.py` (~395 linhas, 75 testes)
- `tests/unit/hooks/test_deployer_post_tool_use.py` (~75 linhas, 4 testes)
- `tests/unit/hooks/test_deployer_stop.py` (~80 linhas, 4 testes)
- `tests/unit/hooks/test_deployer_payload_detection.py` (~140 linhas, 8 testes)
- `tests/integration/test_no_legacy_ci.py` (~110 linhas, 7 testes)
- `tests/integration/test_deployer_plugin_dispatch.py` (~190 linhas, 11 testes)
- `PLAN_SPRINT18.md` (356 linhas)
- `.opencode/rag/knowledge/2026-08-27-dev-feature-deployer-agent.md` (este arquivo)

### Editados (5 arquivos)

- `.opencode/plugin/agent-hooks.ts` (map `AGENTS` + `RECOGNIZED_AGENT_SLUGS`)
- `.opencode/hooks/_lib/payload.py` (`_AGENT_HINTS`)
- `.opencode/hooks/_lib/test_runner.py` (branch deployer)
- `tests/unit/test_commands_definitions.py` (8 testes novos para `/deploy`)
- `tests/integration/test_no_legacy_agents.py` (`CANONICAL_SLUGS` agora tem 3)
- `AGENTS.md` (Sprint 18 block + ajustes CI removido)
- `PLAN.md` (status table atualizada)

### Deletados (3 arquivos)

- `.github/workflows/test-npm-package.yml`
- `.github/workflows/publish-npm.yml`
- `.github/workflows/publish-base.yml`

## Metricas finais

- Suite Python: **890 passed / 1 skipped (CONFAZ) / 0 failed** (baseline Sprint 17: 761; **+129 testes Sprint 18**).
- Cobertura: **84.99%** (baseline Sprint 17: 85.07%, -0.08pp margin; gate 80% verde).
- Suite Node: **64 passed / 5 skipped (gate nativo) / 69 total** (baseline mantido).
- Code review: **0 BLOQUEANTE / 0 IMPORTANTE / 0 SUGESTAO** round 2 final.
- Iteracoes do loop corretivo: 1.

## FOLLOW-UPS Sprint 19+

1. **Criar `tests/e2e/smoke-test-deploy.ps1`** (gate E2E do `/deploy` end-to-end: bare push, tag, npm publish em test registry, gh release create).
2. **Estender `tests/integration/test_deployer_plugin_dispatch.py`** com gate end-to-end que dispara pre_tool_use + post_tool_use + stop via plugin TS em subprocesso real (sem mock).
3. **Re-habilitar Windows na CI matrix do `packages/dfe-agent/`** (gate FOLLOW-UP Sprint 14 #2, agora via `tests/query/cache.test.ts` BEHAVIORAL apos upgrade `better-sqlite3`).
4. **Documentar em `.opencode/agent/dfe-agent.md`** que o agent `dfe-agent` agora responde via CLI publicado `@wiati/dfe-agent` (instalacao via `/deploy --npm`).
5. **Migrar `npm publish` de manual para `/deploy --npm`** (gate humano continua, mas agora via agent).
6. **Fechar a divergencia local/remoto atual** (`git pull --rebase && git push` resolve 1 byte em `storage/dfe.db.gz.sha256`).
7. **Adicionar `*.tgz` ao `.gitignore`** (limpar `wiati-dfe-agent-0.1.5.tgz` untracked).
