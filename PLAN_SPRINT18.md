# PLAN_SPRINT18.md

> Sprint 18 — Agente `Deployer` + remoção completa do CI (GitHub Actions).
> Origem: pedido do usuario em 2026-08-27 ("pode remover o CI do projeto. farei sempre tudo via agente aqui no projeto. inclusive, crie um agente chamado Deployer que sera responsavel por isso. somente ele podera desempenhar a tarefa de subir e administrar o git.").
> Itens cobertos: **0 BLOQUEANTE + 0 IMPORTANTE + 0 PARCIAL** (sprint greenfield; tudo e' BLOQUEANTE ate' TDD verde).
> Principio: **TDD** (teste vermelho primeiro), zero regressao nas suites existentes (761 passed / 1 skipped baseline Sprint 17), cobertura >= 80%.
> A sprint NAO mexe em logica de `src/` — e' uma sprint de **infraestrutura de agents** (harness `.opencode/`, plugin TS, slash command, docs).

## Contexto

Estado atual do repo (`https://github.com/wia-ti/dfe-agent.git`):

- **CI**: 3 workflows em `.github/workflows/` (Sprint 14):
  - `test-npm-package.yml` (CI matrix ubuntu x Node 20.x/22.x; pytest-regression `if: false`; E2E smoke `if: false`).
  - `publish-npm.yml` (publish job `if: false` desde Sprint 14 round 24; user prefere publish manual).
  - `publish-base.yml` (publica `storage/dfe.db.gz` no GitHub Releases em tag `v*.*.*`).
- **API publica real**: `https://api.github.com/repos/wia-ti/dfe-agent/actions/runs` (81 runs totais). Apenas 1 dos ultimos 4 runs passou. **CI degradado, sem valor residual**.
- **Agents canonicos** (Sprint 11): `dev` (implementador owner) + `code-reviewer` (read-only).
  - `dev/pre_tool_use.py` BLOQUEIA `git push`, `gh pr create`, `gh release` (linha 56-60).
  - `code-reviewer` tem `permission.edit: deny` (read-only total).
- **Nenhum agent hoje pode fazer push** — publicacao manual via `npm login` + `npm publish` (gate humano) e tags via `git tag` direto no shell.

Decisao do usuario: **remover CI** + **criar agent Deployer** como unico autorizado a:
- `git push` (incluindo tags e branches).
- `git pull --rebase` (resolver a divergencia atual de 1 byte em `storage/dfe.db.gz.sha256`).
- `git tag` (criar/deletar local + push).
- `git remote` (list/set-url).
- `gh release create/delete/upload` (Sprint 14 workflow substituido).
- `npm login` + `npm publish --access public --provenance` + `npm dist-tag add`.
- `npx dfe-agent *` (instalacao local do pacote no consumidor).

## Decisoes arquiteturais (D18.1-D18.10)

- **D18.1** — Agent slug canonico: `deployer` (singular, kebab-case via `mode: primary`). Path: `.opencode/agent/deployer.md` (singular; Sprint 11 D.1 canonizou `.opencode/agent/`).
- **D18.2** — Permissions do `deployer`:
  - `edit: deny` (defesa em profundidade — deployer NAO altera arquivos; usa apenas Bash para operacoes remotas).
  - `bash: allow` (necessario para `git`, `npm`, `gh release`).
  - `task: deny` (deployer NAO sub-delega; e' uma acao atomica).
  - `skill: deny` (deployer NAO carrega skill `dfe-fiscal`; fora de escopo).
  - `todowrite: deny` (deployer NAO cria TODOs; fluxo e' curto).
  - `webfetch: deny` (deployer NAO consulta web).
  - `external_directory: deny` (deployer NAO sai do workspace).
  - `read: allow`, `glob: allow`, `grep: allow`, `list: allow` (necessarios para verificar working tree antes do push).
- **D18.3** — Escopo do `pre_tool_use.py` do deployer (allow list explicita + block list de defesa em profundidade):
  - **ALLOW** (padrao `*`): comandos `git *`, `npm *`, `gh release *`, `npx dfe-agent *`, `npx --prefix .opencode tsx .opencode/rag/embed.ts --file <md>` (escape hatch para RAG depois).
  - **BLOCK**:
    - `Write`, `Edit`, `MultiEdit`, `NotebookEdit` (reforca `permission.edit: deny`).
    - `rm -rf`, `sed -i`, redirecionamento `>` (escrita shell).
    - `curl`, `wget` (downloads HTTP nao fazem parte do escopo).
    - `python -m src.collector --once`, `python -m src.indexer.ingest`, `python -m src.ragctl {migrate,reindex,benchmark}` (gate de pipeline RAG, mesmo do `dev`).
    - `pip install`, `poetry add` (decisao humana via PLAN).
    - `git commit` sem `--allow-empty` (NAO escreve historico; deployer sobe o que o humano ja commitou).
- **D18.4** — Slash command `/deploy` (path: `.opencode/command/deploy.md`, `agent: deployer`):
  - Flags canonicas:
    - `/deploy` (sem flag): apenas `git push` (commits locais -> origin).
    - `/deploy --tag <vX.Y.Z>`: push + `git tag <vX.Y.Z>` + `git push origin <vX.Y.Z>`.
    - `/deploy --npm`: push + tag (`v0.0.1-sprint<N>`) + `npm publish --access public --provenance` no `packages/dfe-agent/`.
    - `/deploy --release <tag> [notas]`: push + tag + `gh release create <tag> --notes <notas>` (substitui workflow `publish-base.yml`).
  - Gate humano explicito antes de cada acao destrutiva (`--npm`, `--release`, `--tag` com `force`).
- **D18.5** — `post_tool_use.py` do deployer: observer lightweight (apenas `log_event` em `storage/agent_hooks.log`; NAO roda pytest).
- **D18.6** — `stop.py` do deployer: exit 0 sem pytest e sem captura RAG (deployer e' acao atomica, nao ha aprendizado de feature).
- **D18.7** — Plugin `.opencode/plugin/agent-hooks.ts`:
  - Adicionar `"deployer"` ao map `AGENTS` (linha 44-56).
  - Adicionar `"deployer"` a `RECOGNIZED_AGENT_SLUGS` (linha 162-165).
- **D18.8** — `_lib/payload.py::_AGENT_HINTS`: adicionar `("deployer", re.compile(r"\bdeployer\b(?!ed|ing|ment)"))` (lookahead negativo evita match em "deployed", "deploying").
- **D18.9** — `_lib/test_runner.py::suites_for_path`: branch para `agent == "deployer"` retornando suite vazia (deployer NAO roda pytest; gate diferente do dev).
- **D18.10** — Remocao completa de CI:
  - `rm .github/workflows/test-npm-package.yml`
  - `rm .github/workflows/publish-npm.yml`
  - `rm .github/workflows/publish-base.yml`
  - Gate anti-regressao em `tests/integration/test_no_legacy_ci.py` impede ressurreicao.

## Diagrama ASCII (dependencias criticas)

```
Fase 0 (briefing + RAG)
    |
    v
Fase 1 (PLAN_SPRINT18)  --[aprovado]-->  Fase 2.1-2.4 (TDD vermelho)
                                                |
                                                v
                                          Fase 2.5 (implementacao)
                                                |
                                                v
                                          Fase 2.6 (verde local)
                                                |
                                                v
Fase 3 (suite verde)  --[0 BLOQUEANTE / 0 IMPORTANTE]-->  Fase 4 (code review)
                                                                 |
                                                                 v
                                                       Fase 5 (loop corretivo)
                                                                 |
                                                                 v
                                                       Fase 6 (RAG depois)
                                                                 |
                                                                 v
                                                       Fase 7 (entrega humana)
```

## Tabela de IDs

- `B<n>` = BLOQUEANTE
- `I<n>` = IMPORTANTE
- `P<n>` = PARCIAL
- `S<n>` = SUGESTAO

Sprint 18 e' greenfield; nao ha `B18.x` pre-existentes — todos os `B18.x` serao declarados pelo code-reviewer (Fase 4) se algo BLOQUEANTE surgir durante TDD.

## Fases

### Fase 0 — Briefing + RAG antes (completo)

- Briefing canonico: AGENTS.md, SPEC.md, PLAN.md, regras `dfe-rules`/`convencoes-gerais`/`src`/`tests`/`seguranca`.
- RAG antes: 3 hits retornados (`2026-08-26-dev-sprint14-npm-package.md`, `2026-08-26-feature-unify-harness.md`, `2026-08-27-dev-bug-dfe-agent-schema-drift.md`).
- Conclusao: nenhum learning previo sobre agent `deployer` ou remocao de CI; sprint abre territorio novo. Convencao "agent canonico em `.opencode/agent/` (singular)" e "teste estrutural por agent" valem (precedentes Sprint 9 + Sprint 11).

### Fase 1 — Planning (este arquivo)

- Criterio: `PLAN_SPRINT18.md` criado, validado contra template de `PLAN_SPRINT17.md` e `PLAN_SPRINT14.md`, gates Fase 0-7 definidos.
- [x] `PLAN_SPRINT18.md` escrito.

### Fase 2 — Implementacao TDD (teste vermelho primeiro)

#### Task 2.1 — Definition do agent Deployer (gate B18.1 + TDD)

- **Agent**: @dev
- **Input**: nenhuma (arquivo a ser criado).
- **Output**: 
  - `tests/unit/test_deployer_agent_definition.py` (NOVO; espelha `test_dev_agent_definition.py`).
  - `.opencode/agent/deployer.md` (NOVO; segue `.opencode/agent/dev.md` como template).
- **Criterios de aceitacao**:
  - [ ] Teste vermelho `test_deployer_agent_file_exists` falha antes da implementacao.
  - [ ] Frontmatter YAML valido com `name: deployer`, `mode: primary`, `model: PROVIDER/MiniMax-M3`.
  - [ ] `permission.edit: deny`, `permission.task: deny`, `permission.skill: deny`, `permission.todowrite: deny`, `permission.webfetch: deny`, `permission.external_directory: deny`.
  - [ ] `permission.read: allow`, `permission.bash: allow`, `permission.glob: allow`, `permission.grep: allow`, `permission.list: allow`.
  - [ ] Corpo declara escopo canonico (git push/pull/tag/branch/remote + npm publish + gh release) e gate humano antes de acoes destrutivas.
  - [ ] Corpo referencia `.opencode/hooks/deployer/{pre_tool_use,post_tool_use,stop}.py`.
  - [ ] Suite verde.

#### Task 2.2 — `pre_tool_use.py` do Deployer (gate B18.2 + TDD)

- **Agent**: @dev
- **Input**: `.opencode/hooks/dev/pre_tool_use.py` como template.
- **Output**:
  - `tests/unit/hooks/test_deployer_pre_tool_use.py` (NOVO; ~25 testes parametrizados cobrindo allow list + block list + edge cases).
  - `.opencode/hooks/deployer/pre_tool_use.py` (NOVO).
- **Criterios de aceitacao**:
  - [ ] Teste vermelho `test_allows_git_push_origin_main` falha antes da implementacao.
  - [ ] ALLOW: `git push`, `git push origin main`, `git tag v0.1.6`, `git push origin v0.1.6`, `git push origin :refs/tags/v0.1.5`, `git push origin :feature/foo`, `git pull --rebase`, `git fetch`, `git remote -v`, `git branch -D feature/foo`, `npm publish --access public --provenance`, `npm login`, `npm view @wiati/dfe-agent`, `npm dist-tag add`, `gh release create v1.2.5 --notes "..."`, `gh release delete v1.2.4`, `gh release upload v1.2.5 file.tar.gz`, `npx dfe-agent install --auto-setup`, `npx --prefix .opencode tsx .opencode/rag/embed.ts --file <md>`.
  - [ ] BLOCK: Write/Edit/MultiEdit/NotebookEdit, `rm -rf`, `sed -i`, `>`, `curl`, `wget`, `pip install`, `python -m src.collector --once`, `python -m src.indexer.ingest`, `python -m src.ragctl {migrate,reindex,benchmark}`.
  - [ ] Suite verde.

#### Task 2.3 — `post_tool_use.py` + `stop.py` do Deployer (gate B18.3 + TDD)

- **Agent**: @dev
- **Input**: `.opencode/hooks/dev/post_tool_use.py` e `.opencode/hooks/dev/stop.py` como templates.
- **Output**:
  - `tests/unit/hooks/test_deployer_post_tool_use.py` (NOVO; testa log_event).
  - `tests/unit/hooks/test_deployer_stop.py` (NOVO; testa exit 0 sem pytest).
  - `.opencode/hooks/deployer/post_tool_use.py` (NOVO).
  - `.opencode/hooks/deployer/stop.py` (NOVO).
- **Criterios de aceitacao**:
  - [ ] Teste vermelho falha antes da implementacao.
  - [ ] `post_tool_use.py` nao roda pytest (apenas log_event em `storage/agent_hooks.log`).
  - [ ] `stop.py` retorna exit 0 sem rodar pytest e sem chamar `learning.spawn_summarize_then_embed`.
  - [ ] Suite verde.

#### Task 2.4 — Plugin dispatch (gate B18.4 + TDD)

- **Agent**: @dev
- **Input**: `.opencode/plugin/agent-hooks.ts` (linhas 44-56 e 162-165).
- **Output**:
  - `tests/integration/test_deployer_plugin_dispatch.py` (NOVO).
  - `.opencode/plugin/agent-hooks.ts` (EDIT: adicionar `"deployer"` ao map `AGENTS` + `RECOGNIZED_AGENT_SLUGS`).
- **Criterios de aceitacao**:
  - [ ] Teste vermelho falha antes da implementacao.
  - [ ] Plugin detecta `deployer` via `DFE_ACTIVE_AGENT=deployer` no env e dispara `pre_tool_use.py` correto.
  - [ ] Plugin dispara `post_tool_use.py` apos Write/Edit (apesar de `edit: deny`, hook continua registrado).
  - [ ] Plugin NAO dispara hook quando agent e' `dev` ou `code-reviewer` (regressao).
  - [ ] `RECOGNIZED_AGENT_SLUGS` contem `deployer`.
  - [ ] Suite verde.

#### Task 2.5 — `_lib/payload.py` + `_lib/test_runner.py` (gate B18.5 + TDD)

- **Agent**: @dev
- **Input**: `.opencode/hooks/_lib/payload.py` e `.opencode/hooks/_lib/test_runner.py`.
- **Output**:
  - `tests/unit/hooks/test_deployer_payload_detection.py` (NOVO; consolida
    testes de `_AGENT_HINTS` E `suites_for_path` em um unico arquivo
    por DRY — 4 testes de payload + 4 testes de test_runner).
  - `.opencode/hooks/_lib/payload.py` (EDIT: adicionar deployer a _AGENT_HINTS).
  - `.opencode/hooks/_lib/test_runner.py` (EDIT: branch deployer retorna suite vazia).
- **Criterios de aceitacao**:
  - [ ] Teste vermelho falha antes da implementacao.
  - [ ] `detect_active_agent(payload)` retorna `deployer` quando env `DFE_ACTIVE_AGENT=deployer`.
  - [ ] `_AGENT_HINTS` pattern reconhece `deployer` sem match em `deployed`/`deploying` (lookahead negativo).
  - [ ] `suites_for_path("packages/dfe-agent/src/foo.ts", agent="deployer")` retorna `[]`.
  - [ ] Suite verde.

#### Task 2.6 — Slash command `/deploy` (gate B18.6 + TDD)

- **Agent**: @dev
- **Input**: `.opencode/command/feature.md` como template.
- **Output**:
  - `tests/unit/test_commands_definitions.py` (EDIT: adicionar testes parametrizados para `/deploy`).
  - `.opencode/command/deploy.md` (NOVO; pipeline canonico com 4 fases e gate humano explicito).
- **Criterios de aceitacao**:
  - [ ] Teste vermelho falha antes da implementacao.
  - [ ] `/deploy` frontmatter declara `agent: deployer` (NAO `dev`, NAO `code-reviewer`, NAO `build`/`plan`).
  - [ ] Fase 0 (briefing) chama `npx tsx .opencode/rag/search.ts -q "$ARGUMENTS" -a deployer --top-k 5` (RAG antes com slug canonico).
  - [ ] Fase 4 (gate humano) para cada acao destrutiva (`--tag`, `--npm`, `--release`).
  - [ ] Fase 6 (RAG depois) chama `npx tsx .opencode/rag/embed.ts --file <md>` sincrono.
  - [ ] Documenta os 4 modos (sem flag, `--tag`, `--npm`, `--release`).
  - [ ] Suite verde.

#### Task 2.7 — Remocao do CI (gate B18.7 + TDD)

- **Agent**: @dev
- **Input**: 3 arquivos em `.github/workflows/`.
- **Output**:
  - `tests/integration/test_no_legacy_ci.py` (NOVO; gate anti-regressao).
  - `.github/workflows/test-npm-package.yml` (DELETE).
  - `.github/workflows/publish-npm.yml` (DELETE).
  - `.github/workflows/publish-base.yml` (DELETE).
- **Criterios de aceitacao**:
  - [ ] Teste vermelho falha antes da remocao (testa que os 3 arquivos existem).
  - [ ] Apos remocao: `Test-Path .github/workflows/*.yml` retorna False para os 3.
  - [ ] Gate anti-regressao: 3 testes garantem que os 3 arquivos NAO voltam.
  - [ ] Suite verde.

#### Task 2.8 — Atualizacao AGENTS.md (gate B18.8)

- **Agent**: @dev
- **Input**: AGENTS.md atual.
- **Output**: AGENTS.md (EDIT).
- **Criterios de aceitacao**:
  - [ ] Bloco "Decisoes resolvidas (Sprint 18)" adicionado (4-6 bullets).
  - [ ] Secao "Pipeline de feature" mantem `/feature` mas adiciona `/deploy` no fluxo.
  - [ ] Secao "Como rodar localmente" remove referencias a CI mas adiciona link para `/deploy`.
  - [ ] Lista de agents canonicos atualizada: `dev`, `code-reviewer`, `deployer`.
  - [ ] Secao "Nunca fazer" ganha: "Nunca rodar `git push`/`npm publish` via `@dev` ou `@code-reviewer` (gate enforced — apenas `@deployer` pode)".
  - [ ] Markdown lint passa (`python -c "import re; ..."` nao detecta broken refs).
  - [ ] Suite verde.

### Fase 3 — Suite verde (gate obrigatorio)

- Criterio: `pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=80` exit 0.
- Esperado: 761 passed / 1 skipped (baseline Sprint 17) + ~15-20 testes novos desta sprint.
- Cobertura global mantida >= 80% (gate de CI removido, mas gate de cobertura continua).

### Fase 4 — Code review (subagent `general`; `code-reviewer` nao inviavel por Sprint 9 follow-up)

- Review de:
  - `.opencode/agent/deployer.md` (1 arquivo).
  - `.opencode/hooks/deployer/{pre_tool_use,post_tool_use,stop}.py` (3 arquivos).
  - `.opencode/plugin/agent-hooks.ts` (EDIT).
  - `.opencode/hooks/_lib/{payload,test_runner}.py` (EDIT).
  - `.opencode/command/deploy.md` (1 arquivo).
  - AGENTS.md (EDIT).
- Categoria: BLOQUEANTE / IMPORTANTE / SUGESTAO (template `code-reviewer.md`).
- Especifico: garantir que `@deployer` e `@dev` tem limites claros (deployer NAO edita arquivos; dev NAO faz push).

### Fase 5 — Loop corretivo (max 3 iteracoes)

- BLOQUEANTE: aplicar, re-rodar testes.
- IMPORTANTE: aplicar, re-rodar testes.
- SUGESTAO: registrar em `.opencode/rag/knowledge/<date>-dev-suggestions.md`.
- Gate: 0 BLOQUEANTE / 0 IMPORTANTE antes de Fase 7.

### Fase 6 — RAG depois

- Knowledge file `.opencode/rag/knowledge/2026-08-27-dev-feature-deployer-agent.md`:
  - Sintoma (CI degradado, sem valor residual) + causa raiz (3 jobs `if: false`, 22-25 runs FAILURE consecutivos).
  - Solucao: agent `deployer` + remocao completa de CI.
  - Decisao: slash command `/deploy` com 4 modos + gate humano.
  - Padroes adotados:
    - "permission.edit: deny + bash: allow" para agents de deployment.
    - Allow list explicita em `pre_tool_use.py` (vs block list generica do `@dev`).
    - Hook `stop.py` exit 0 sem RAG capture para acoes atomicas.
  - Embedding file via `npx tsx .opencode/rag/embed.ts --file <md>`.
- Sanity: `search.ts -q "deployer agent deploy command npm publish git push"` retorna top-1 = nosso knowledge.
- `AGENTS.md > Decisoes resolvidas (Sprint 18)` bloco adicionado (gate B18.8).

### Fase 7 — Entrega humana

- Commit + push (gate humano manual, NAO pelo agent).
- **Publicacao do `@wiati/dfe-agent`**: gate humano via `/deploy --npm` (substitui o `npm publish` manual que vinha sendo feito).
- Relatorio final ao humano com:
  - Arquivos modificados (7 novos + 5 edits + 3 deletes).
  - Suite verde (pytest + npm test no `packages/dfe-agent/`).
  - Code review final (0 BLOQUEANTE / 0 IMPORTANTE).
  - Comando para o user fechar: `/deploy` (sem flag) ou `/deploy --tag vX.Y.Z --npm --release vX.Y.Z`.

## Testes criticos (gate duplo)

- [ ] Gate B18.1 — Definition do `deployer` (12+ testes estruturais).
- [ ] Gate B18.2 — `pre_tool_use.py` do deployer (~25 testes allow/block).
- [ ] Gate B18.3 — `post_tool_use.py` + `stop.py` do deployer (observer + exit 0).
- [ ] Gate B18.4 — Plugin dispatch para `deployer` (4 testes).
- [ ] Gate B18.5 — `_AGENT_HINTS` + `suites_for_path` para `deployer` (4 testes).
- [ ] Gate B18.6 — Slash command `/deploy` (5 testes parametrizados).
- [ ] Gate B18.7 — Gate anti-regressao CI removido (3 testes).
- [ ] Gate B18.8 — AGENTS.md atualizado sem broken refs.
- [ ] Suite Python: `pytest tests/ --cov=src --cov-branch --cov-fail-under=80` verde (gate anti-regressao Py).
- [ ] Suite Node: `npm test` no `packages/dfe-agent/` continua verde (gate anti-regressao Node).
- [ ] Code review: 0 BLOQUEANTE / 0 IMPORTANTE (gate code-reviewer template).

## Apêndice A — Riscos

| Risco | Probabilidade | Impacto | Mitigacao |
|---|---|---|---|
| Deployer agent usado para editar arquivos via bypass de `permission.edit: deny` | Baixa | Alto | Hook `deployer/pre_tool_use.py` BLOQUEIA Write/Edit/MultiEdit/NotebookEdit (defesa em profundidade); code reviewer testa explicitamente |
| Divergencia local/remoto (1 byte em `.sha256`) bloqueia `git push` | Media | Baixo | `git pull --rebase` na Fase 1 do `/deploy` resolve antes do push |
| User esquece de commitar antes de `/deploy` | Media | Medio | Fase 1 do `/deploy` aborta se `git status --short` nao-vazio (gate canonico) |
| `npm publish` requer login manual (npm policy 2024+) | Alta | Baixo | `/deploy --npm` aborta com mensagem clara se `npm whoami` falhar; user roda `npm login` e re-tenta |
| Regressao: `@dev` ainda consegue fazer `git push` | Baixa | Critico | Sprint 10 B.1 ja' bloqueou; teste novo `test_dev_pre_tool_use_blocks_git_push_force` adicionado nesta sprint |
| `code-reviewer` consegue fazer push por bug | Baixa | Alto | `permission.bash: { "*": ask }` (linha 11 do frontmatter) + hook `code-reviewer/pre_tool_use_bash.py` ja' BLOQUEIA `git push` |
| CLI do opencode nao expoe `deployer` no menu | Baixa | Baixo | `mode: primary` no frontmatter; gate via `opencode agent list` |

## Apêndice B — Fora de escopo

- Publicar `@wiati/dfe-agent` automaticamente via CI (ja' desabilitado desde Sprint 14 round 24; continua fora).
- Re-habilitar Windows na CI matrix do npm package (Sprint 14 FOLLOW-UP; continua fora — CI foi REMOVIDO).
- Criar versao bash de `smoke-test.ps1` (Sprint 14 FOLLOW-UP; continua fora).
- Implementar `dfe-agent build` em Node (Sprint 14 FOLLOW-UP; continua fora).
- Migrar `src/collector` para Node (Sprint 14 FOLLOW-UP; continua fora).
- Adicionar `--provenance` no CI publish (ja' re-habilitado via Trusted Publisher; continua fora — CI removido).
- Migrar de npm Trusted Publisher para OIDC token local (decisao ja' tomada em Sprint 14 round 17; continua valida).

## Apêndice C — Comandos shell para reproduzir a sprint manualmente

```bash
# Fase 0
pwd && git status --short && git log --oneline -10
npx tsx .opencode/rag/search.ts -q "deployer git push npm publish" -a dev --top-k 5

# Fase 2 (TDD: teste vermelho primeiro)
# Criar testes (vermelho), depois implementacao (verde), depois refactor.
pytest tests/unit/test_deployer_agent_definition.py -x
pytest tests/unit/hooks/test_deployer_pre_tool_use.py -x
pytest tests/unit/hooks/test_deployer_post_tool_use.py -x
pytest tests/unit/hooks/test_deployer_stop.py -x
pytest tests/integration/test_deployer_plugin_dispatch.py -x
pytest tests/unit/hooks/test_deployer_payload_detection.py -x
pytest tests/unit/hooks/test_deployer_suites_for_path.py -x
pytest tests/integration/test_no_legacy_ci.py -x
pytest tests/unit/test_commands_definitions.py -x -k deploy

# Fase 3 (suite verde)
pytest tests/ --cov=src --cov-branch --cov-fail-under=80 -q

# Fase 7 (entrega humana — NAO comita)
git add -A
git status --short
git commit -m "feat(agent): add Deployer agent + remove CI (Sprint 18)"
/deploy  # ou /deploy --tag v0.1.6 --npm --release v0.1.6
```