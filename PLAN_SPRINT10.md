# PLAN_SPRINT10.md

> Plano para consolidar a interface de comandos do DFe-Agent em torno de um
> unico agente implementador `@dev`, com slash commands canonicos `/feature`,
> `/bug` e `/duvida`, e captura garantida de aprendizados no RAG meta-cognitivo.
> Origem: pedido do usuario em 2026-08-26 ("criar os slash commands /bug e
> /duvida, agente @dev responsavel pelos comandos, agentes build e plan nao
> devem mais ser disponibilizados"). Itens cobertos: **4 BLOQUEANTE** +
> ajustes correlatos. Principio: **TDD** (teste vermelho primeiro), zero
> regressao nas suites existentes (508+ passed), cobertura >= 80%.

## Criterio global de conclusao

`pytest tests/ --cov=src --cov-fail-under=80` retorna exit code 0 **E** os
3 commands sao listados por `opencode command list` (sanity text) **E** o
agente `@dev` e' o unico agent de implementacao (`opencode agent list`
lista `dev` como primário de escrita + `code-reviewer` como read-only de
auditoria; nao lista `build` nem `plan`).

```
Fase A ──► Fase B ──► Fase C ──► Fase D ──► Fase E
agente    hooks      RAG         commands    docs
@dev      dev/       meta-cog    /feature    AGENTS.md
definicao pre/post   dev slug    /bug        README
BLOQ.     BLOQ.      BLOQ.       BLOQ.       IMP.
```

**Dependencias criticas entre fases**:
- B (hooks) depende de A (definicao do agent) — sem agent, o plugin nao roteia.
- C (RAG meta-cognitivo) depende de A — slug `dev` precisa estar definido.
- D (commands) depende de A — frontmatter `agent: dev` referencia o slug.
- E (docs) depende de A+B+C+D.

## Resumo dos problemas observados

| ID | Sintoma | Causa raiz (resumo) |
|----|---------|---------------------|
| **B10.1** | Nao existe agente `@dev`; comando `/feature` referencia `agent: build` (slug nao definido em lugar nenhum); AGENTS.md fala em "build" como agente RAG-meta | Antes da Sprint 10, o projeto nunca definiu formalmente um agente implementador. Os comandos eram atribuidos a slugs ficticios, e os hooks do plugin TS roteavam para agentes `.claude/agents/<slug>/` que existem (backend-engineer, ml-engineer, prompt-engineer, qa-engineer) mas nenhum deles e' dono da interface do projeto. |
| **B10.2** | Nao existem hooks para o slug `dev`; o plugin TS `agent-hooks.ts:41-69` tem 5 slugs (code-reviewer, backend-engineer, ml-engineer, prompt-engineer, qa-engineer) e nenhum e' "owner" do projeto inteiro (backend-engineer bloqueia `.opencode/agent/`, etc.) | Sem hooks, o agente `@dev` nao consegue editar `.opencode/`, `.claude/agents/`, `AGENTS.md`, etc. sem disparar bloqueios de escopo. |
| **B10.3** | RAG meta-cognitivo (`.claude/rag.db`) nao reconhece slug `dev`; `learning_prompt_submit.py:41-46` tem regex `AGENT_HINTS` com 4 slugs; `_lib/payload.py:46-51` tem 5 slugs em `_AGENT_HINTS`. Sem reconhecimento, comandos executados via `@dev` cairiam em `agent="session"` (modo permissivo com warning). | O classificador heuristico foi montado quando havia 5 agents distintos. A consolidacao em `@dev` exige registro do novo slug. |
| **B10.4** | Nao existem slash commands `/bug` e `/duvida`; `/feature` e' o unico command. O usuario precisa de (a) fluxo estruturado de correcao com gate de aprovacao humana antes da implementacao e (b) comando que LE o projeto antes de responder duvidas (sem implementar nada) | O fluxo de Q&A hoje so' existe via dfe-agent principal (sem comando canonico). O fluxo de bug fix hoje so' existe via `/feature` (que vai direto para implementacao, sem investigacao previa). |

---

## Fase A — Definicao do agente `@dev` (BLOQUEANTE B10.1)

**Criterio**: arquivo `.opencode/agent/dev.md` existe, frontmatter YAML valido
com `name: dev`, `mode: subagent`, `permission.*: allow` para escrita, e o
corpo documenta escopo/responsabilidades. Equivalente em `.claude/agents/dev.md`
para o plugin TS.

### Task A.1 — Criar `.opencode/agent/dev.md` (formato opencode CLI)

- Agent: Prompt Engineer (escopo `.opencode/agent/`)
- Input: `.opencode/agent/dfe-agent.md` (modelo de frontmatter), `.opencode/agents/code-reviewer.md` (modelo de permission block)
- Diagnostico:
  - O opencode CLI aceita agents em `.opencode/agent/<name>.md` (formato
    canonico) OU `.opencode/agents/<name>.md` (formato Claude-Code-like).
    Ambos funcionam; o AGENTS.md e os testes existentes misturam os dois.
  - O dfe-agent usa `.opencode/agent/`; o code-reviewer usa `.opencode/agents/`.
    Para evitar inconsistencia com testes (`test_dfe_agent_definition.py`
    aponta para `.opencode/agent/`), o `@dev` ficara' em `.opencode/agent/dev.md`.
  - Frontmatter obrigatorio (per `AGENTS.md > Convencoes > Frontmatter obrigatorio`):
    `name`, `model`, `mode`, `permission`.
- Output:
  - `.opencode/agent/dev.md` com:
    - Frontmatter:
      ```yaml
      ---
      name: dev
      description: Implementador owner de todas as alteracoes do DFe-Agent. Use para qualquer alteracao em src/, tests/, .opencode/, .claude/, AGENTS.md, PLAN.md, SPEC.md. Sub-delega revisao read-only para o agent code-reviewer via task tool.
      mode: subagent
      model: PROVIDER/MiniMax-M3
      hidden: false
      permission:
        read: allow
        edit: allow
        bash: allow
        glob: allow
        grep: allow
        list: allow
        task: allow
        webfetch: allow
        websearch: allow
        skill: allow
        todowrite: allow
        external_directory: deny
      ---
      ```
    - Corpo Markdown documentando:
      1. Identidade: "Voce e o agente implementador owner do DFe-Agent. Voce
         e' o UNICO agent com permissao de escrita ampla no projeto."
      2. Slash commands owners: `/feature`, `/bug`, `/duvida` — todos te
         invocam via `agent: dev` no frontmatter.
      3. Sub-delegacao: para revisao read-only, use `task` tool com
         `subagent_type: code-reviewer` (vide `.claude/agents/code-reviewer.md`).
      4. Guardrails inviolaveis (link para `.opencode/rules/dfe-rules.md`):
         nunca inventar informacao fiscal, nunca burlar guardrail de dominio,
         nunca reprocessar documento ja ingerido, nunca dropar `vec_chunks`
         sem backfill.
      5. RAG meta-cognitivo: SEMPRE invoque `npx tsx .claude/scripts/search.ts -q "<topico>" -a dev`
         na Fase 0 de qualquer slash command (aproveitar aprendizados
         anteriores); ao final, grave o aprendizado via `.claude/hooks/_lib/learning.py`
         (delegado automaticamente pelos hooks `stop.py`).
      6. Workflow TDD canonico: teste vermelho -> implementacao minima -> verde
         -> marcar `[x]` no plano correspondente.
      7. Limites de bash: nao fazer `git push`, nao fazer `pip install` (decisao
         humana), nao burlar o guardrail de dominio (esses limites sao
         duplicados em `.claude/hooks/dev/pre_tool_use.py` para defesa em
         profundidade).
- Criterios de aceitacao:
  - [ ] Arquivo criado em `.opencode/agent/dev.md`.
  - [ ] Frontmatter contem `name: dev`, `mode: subagent`, todos os
        `permission.*: allow` (exceto `external_directory: deny`).
  - [ ] `python -c "import yaml; yaml.safe_load(open('.opencode/agent/dev.md').read().split('---')[1])"`
        retorna 0 (YAML valido).

### Task A.2 — Criar `.claude/agents/dev.md` (formato Claude-Code-like, para plugin TS)

- Agent: Prompt Engineer
- Input: `.claude/agents/backend-engineer.md` (modelo), A.1 criada
- Diagnostico:
  - O plugin `.opencode/plugin/agent-hooks.ts` detecta o agent ativo via
    `DFE_ACTIVE_AGENT` env var OU `argv` OU `sessionID`. Para que os hooks
    PreToolUse/PostToolUse/Stop sejam despachados para o slug `dev`, o
    `.claude/agents/dev.md` precisa existir com frontmatter `hooks:`.
  - O `.opencode/agent/dev.md` (Task A.1) e' a definicao canonica para o
    opencode CLI; este `.claude/agents/dev.md` e' a definicao canonica para
    o sistema de hooks do plugin TS. Sao complementares (mesmo slug, dois
    formatos).
- Output:
  - `.claude/agents/dev.md` com:
    - Frontmatter com `name: dev`, `description` espelhando A.1,
      `tools: Read, Write, Edit, Bash, Grep, Glob, WebFetch, WebSearch`,
      `hooks: { PreToolUse, PostToolUse, Stop }` apontando para
      `.claude/hooks/dev/{pre_tool_use,post_tool_use,stop}.py`.
    - Corpo Markdown com:
      1. Identidade (mesmo do A.1).
      2. Escape hatch: "Se o PreToolUse hook reclamar de um arquivo que
         deveria ser editavel (bug do hook), reporte como incidente no
         relatorio de code-review."
      3. Hooks ativos:
         - PreToolUse: bloqueia `git push`, `pip install` direto,
           `rm -rf`, `sed -i`, `curl`/`wget` (download HTTP direto),
           SQL direto em `.db`, `python -m src.collector --once` (varredura
           — NAO deve partir do agent de implementacao). NAO bloqueia
           paths (escopo amplo).
         - PostToolUse: roda pytest da suite apropriada (definida em
           `.claude/hooks/_lib/test_runner.py::suites_for_path`).
         - Stop: roda pytest geral (`tests/`) + captura aprendizado
           (gate `tool_writes_count > 0`).
- Criterios de aceitacao:
  - [ ] Arquivo criado.
  - [ ] Frontmatter com `hooks` apontando para os 3 scripts.

---

## Fase B — Hooks do agente `@dev` (BLOQUEANTE B10.2)

**Criterio**: 3 scripts Python em `.claude/hooks/dev/`, todos com testes
unit passando, cobrindo gate de qualidade (pytest) e gate de aprendizado
(learning.spawn_summarize_then_embed).

### Task B.1 — `.claude/hooks/dev/pre_tool_use.py` (escopo amplo, gate minimo)

- Agent: Backend Engineer
- Input: A.2 criada
- Diagnostico:
  - Diferente de `backend-engineer/pre_tool_use.py:70-77` (que BLOQUEIA
    paths), o `dev/pre_tool_use.py` permite escrita em qualquer path.
  - Apenas bloqueia acoes globais perigosas (defesa em profundidade):
    `git push`, `pip install`, `rm -rf`, `sed -i`, `curl`/`wget`,
    SQL direto em `.db`, comandos de varredura RAG (`python -m src.collector --once`,
    `python -m src.indexer.ingest`, `python -m src.ragctl {migrate,reindex,benchmark}`)
    — esses rodam via CLI do usuario, NAO pelo agent de implementacao.
- Output:
  - `.claude/hooks/dev/pre_tool_use.py` (~80 linhas):
    - Mesma estrutura do `backend-engineer/pre_tool_use.py` (import de
      `_lib.payload`, `_BLOCKED_BASH`).
    - `_BLOCKED_BASH` com ~8 patterns.
    - `_BLOCKED_FILE` VAZIO (escopo amplo).
    - Exit 0 em caso de permissao, 2 em caso de bloqueio.
- Criterios de aceitacao:
  - [ ] Cobertura >= 90% em `tests/unit/hooks/test_dev_pre_tool_use.py`.

### Task B.2 — `.claude/hooks/dev/post_tool_use.py` (pytest da suite apropriada)

- Agent: Backend Engineer
- Input: B.1 pronta
- Diagnostico:
  - Mesma logica do `backend-engineer/post_tool_use.py` (importar
    `suites_for_path(edited_path, agent="dev")` e rodar pytest).
  - O `_lib/test_runner.py` precisa conhecer o slug `dev` (Task B.4).
- Output:
  - `.claude/hooks/dev/post_tool_use.py` (~40 linhas).
- Criterios de aceitacao:
  - [ ] Suite apropriadada roda apos edicao.

### Task B.3 — `.claude/hooks/dev/stop.py` (pytest geral + captura aprendizado)

- Agent: Backend Engineer
- Input: B.2 pronta
- Diagnostico:
  - Stop do `backend-engineer` (linha 47-53) roda pytest de 5 suites
    especificas. Para `@dev`, o pytest roda `tests/` inteiro
    (suite completa) — owner de todo o projeto.
- Output:
  - `.claude/hooks/dev/stop.py` (~60 linhas):
    - `suites = ["tests/"]` (suite completa).
    - `run_pytest(suites, timeout=900)` (timeout maior).
    - Em sucesso: chama `learning.spawn_summarize_then_embed` se
      `payload_has_edits(payload)`.
- Criterios de aceitacao:
  - [ ] Cobertura >= 90% em `tests/unit/hooks/test_dev_stop.py`.

### Task B.4 — Atualizar `.claude/hooks/_lib/test_runner.py` para `dev`

- Agent: Backend Engineer
- Input: nenhuma
- Diagnostico:
  - Hoje `suites_for_path(rel_path, agent)` (linha 48) so' conhece 2 agents.
    Para `dev`, retorna TODAS as suites (pois `@dev` pode ter editado qualquer
    arquivo).
- Output:
  - Adicionar branch `if agent == "dev"` que retorna lista uniao das
    suites backend + ml + vetoriais.
- Criterios de aceitacao:
  - [ ] Teste em `tests/unit/hooks/test_test_runner.py` (novo) cobre 3 branches.

### Task B.5 — Testes unit dos hooks `dev`

- Agent: QA Engineer
- Input: B.1-B.4 prontas
- Output:
  - `tests/unit/hooks/test_dev_pre_tool_use.py` (NOVO, ~10 testes):
    - 8 BLOCK patterns (parametrize).
    - 4 ALLOW read-only (Read, Glob, Grep, WebFetch).
    - 5 ALLOW write/edit (Write, Edit, MultiEdit, NotebookEdit) em paths
      arbitrarios do projeto (sem bloqueio de path).
    - 1 teste de log escrito em `storage/agent_hooks.log`.
  - `tests/unit/hooks/test_dev_stop.py` (NOVO, ~4 testes):
    - `test_stop_runs_pytest_full_suite_when_payload_ok`.
    - `test_stop_blocks_when_pytest_fails` (exit 2).
    - `test_stop_skips_learning_when_no_edits`.
    - `test_stop_invokes_learning_when_edits_and_pytest_passes`.

---

## Fase C — RAG meta-cognitivo reconhece slug `dev` (BLOQUEANTE B10.3)

**Criterio**: 4 arquivos de meta-cognitivo atualizados para reconhecer slug
`dev`. Sem isso, comandos `/bug`, `/duvida`, `/feature` rodariam com
`agent="session"` (degradacao controlada).

### Task C.1 — `.claude/hooks/_lib/payload.py:46-51`

- Agent: Backend Engineer
- Output:
  - Adicionar `("dev", re.compile(r"\bdev\b", re.IGNORECASE))` na lista
    `_AGENT_HINTS` (com regex cuidadoso para nao casar com "developer"
    ou "device" — usar `\bdev\b` ja' evita "developer" porque `\bdev\b`
    exige borda apos `dev`, e "developer" tem "developer" depois, entao
    casa. SOLUCAO: regex mais especifica `re.compile(r"\bdev\b(?!elop|ice|el)", re.IGNORECASE)`
    — borda negativa lookhead.
  - ATENCAO: essa heuristica so' eh usada em fallback (3o nivel); o
    caminho primario continua sendo `DFE_ACTIVE_AGENT` env + `payload.agent`.
- Criterios de aceitacao:
  - [ ] Teste em `tests/unit/hooks/test_payload.py` (NOVO ou extensao)
        cobre que `payload={"session_id":"sess-dev-001"}` retorna slug `dev`.

### Task C.2 — `.opencode/hooks/learning_prompt_submit.py:41-46`

- Agent: Prompt Engineer
- Output:
  - Adicionar `("dev", r"\b(implementar|criar|adicionar|desenvolver|fix|bug|refatorar|codigo|src/|test/)\b")`
    no `AGENT_HINTS`. (Cobre o caso do `@dev` ser invocado em contexto
    generico — o regex casa prompt de implementacao).
- Criterios de aceitacao:
  - [ ] Teste em `tests/unit/test_learning_prompt_submit.py` (NOVO ou
        extensao) cobre slug `dev`.

### Task C.3 — `.opencode/plugin/agent-hooks.ts:41-69`

- Agent: Prompt Engineer
- Output:
  - Adicionar entrada `"dev"` no `AGENTS`:
    ```ts
    "dev": {
      slug: "dev",
      preToolUse: ".claude/hooks/dev/pre_tool_use.py",
      postToolUse: ".claude/hooks/dev/post_tool_use.py",
      stop: ".claude/hooks/dev/stop.py",
    },
    ```
  - Tambem adicionar `"dev"` em `_AGENT_HINTS` no Python side (ja' feito
    em C.1) e ao inves disso so' editar TS.
- Criterios de aceitacao:
  - [ ] Teste em `tests/integration/test_dev_plugin_dispatch.py` (NOVO):
    - confirma entrada `"dev"` no map.
    - confirma `preToolUse + postToolUse + stop` configurados.
    - confirma que `detectAgentFromSession` retorna `dev` quando
      `DFE_ACTIVE_AGENT=dev`.

### Task C.4 — `.claude/scripts/lib/classifier.ts` (se aplicavel)

- Agent: Prompt Engineer
- Diagnostico:
  - Se existir, adicionar `agentToCategory` map para `dev` ->
    `architecture_decision` (categoria prioritaria para o owner do projeto).
- Criterios de aceitacao:
  - [ ] Se nao existir, skip.
  - [ ] Se existir, teste cobre.

---

## Fase D — Slash commands `/feature`, `/bug`, `/duvida` (BLOQUEANTE B10.4)

**Criterio**: 3 arquivos `.opencode/command/{feature,bug,duvida}.md`
criados/atualizados, todos com `agent: dev`, todos com invocacao
explicita de `search.ts` na Fase 0 (RAG antes) e `embed.ts` na Fase
final (RAG depois).

### Task D.1 — `.opencode/command/feature.md` (atualizar para `dev`)

- Agent: Prompt Engineer
- Input: nenhuma
- Diagnostico:
  - Substituir `agent: build` (linha 3 do frontmatter) por `agent: dev`.
  - Trocar `-a build` (linhas 28, 252, 323) por `-a dev` em todas as
    chamadas `npx tsx .claude/scripts/search.ts`.
  - Trocar `knowledge/<date>-build-decisions.md` (linha 252) por
    `knowledge/<date>-dev-decisions.md`.
  - Trocar `_pending-backend-engineer.md.lock` (linha 86 do learning_subagent_stop.py)
    NAO mexe — esse hook e' legado, e' substituido pelo novo dev/.
- Output:
  - Diff minimo, apenas substituicoes literais.
- Criterios de aceitacao:
  - [ ] `pytest tests/unit/test_commands_definitions.py::test_feature_command_uses_dev_agent` passa.

### Task D.2 — `.opencode/command/bug.md` (NOVO)

- Agent: Prompt Engineer
- Input: D.1 (padrao de formatacao definido)
- Diagnostico:
  - Pipeline de correcao de bug deve ter gate de aprovacao humana ANTES
    de qualquer edicao (principio de "investigar -> relatar -> pedir
    aprovacao -> corrigir").
  - Estrutura (7 fases):
    - Fase 0 — Briefing (RAG antes): `search.ts -q "$ARGUMENTS" -a dev`.
    - Fase 1 — Investigacao (read-only): reproduzir o sintoma, ler
      codigo, consultar git history, identificar causa raiz. ZERO
      alteracao em arquivos. Entrega: relatorio estruturado com
      sintoma, causa raiz, arquivos candidatos, hipoteses alternativas.
    - Fase 2 — Relatorio + APROVACAO: imprimir relatorio e PARAR. Pedir
      "posso prosseguir com a correcao?" antes de qualquer Write/Edit.
    - Fase 3 — Correcao (TDD, gate duplo): so' apos aprovacao explicita.
      Teste vermelho primeiro (cobrir o bug), implementacao, verde.
    - Fase 4 — Code review (read-only): sub-delega para `code-reviewer`.
    - Fase 5 — Loop corretivo: BLOQUEANTE/IMPORTANTE ate' 0/0.
    - Fase 6 — Documentar no RAG (sempre): `.claude/knowledge/<date>-dev-bug-<slug>.md`
      + `embed.ts --file`.
    - Fase 7 — Entrega: relatorio final.
- Output:
  - `.opencode/command/bug.md` (~250 linhas), frontmatter com
    `agent: dev`, `description` claro.
- Criterios de aceitacao:
  - [ ] Arquivo criado.
  - [ ] Frontmatter YAML valido.
  - [ ] Corpo tem 7 fases distintas com gates explicitos.
  - [ ] `pytest tests/unit/test_commands_definitions.py::test_bug_command_defined`
        passa.

### Task D.3 — `.opencode/command/duvida.md` (NOVO)

- Agent: Prompt Engineer
- Input: D.2 (padrao)
- Diagnostico:
  - Comando de Q&A estruturado: LE o projeto (Read, Grep, Glob), formula
    resposta com citacao literal de paths (`file_path:line_number`), NAO
    faz alteracao (read-only), captura a duvida no RAG.
  - Estrutura (4 fases):
    - Fase 0 — Briefing (RAG antes): `search.ts -q "$ARGUMENTS" -a dev`.
    - Fase 1 — Leitura ativa: identificar o escopo da duvida via Grep/Glob.
      Listar todos os arquivos candidatos ANTES de abrir. Ler os
      relevantes com Read. Cruzar com `AGENTS.md`, `SPEC.md`, `PLAN*.md`,
      `.claude/rules/*.md` para encontrar a regra/decisao que responde.
    - Fase 2 — Resposta fundamentada: redigir em portugues, citar
      literalmente `file_path:line_number` para cada fato, terminar com
      bloco `Fontes:` (path local + URL externa se houver).
    - Fase 3 — Capturar no RAG: gravar `.claude/knowledge/<date>-dev-qa-<slug>.md`
      com pergunta + resposta canonica + paths; `embed.ts --file`.
- Output:
  - `.opencode/command/duvida.md` (~150 linhas).
- Criterios de aceitacao:
  - [ ] Frontmatter YAML valido.
  - [ ] `pytest tests/unit/test_commands_definitions.py::test_duvida_command_defined`
        passa.

### Task D.4 — `.opencode/command/README.md` (atualizar tabela)

- Agent: Prompt Engineer
- Input: D.1-D.3 aplicadas
- Output:
  - Tabela com 3 commands: `/feature` (dev), `/bug` (dev), `/duvida` (dev).
  - Coluna "Agente" removida (todos sao `dev`).
- Criterios de aceitacao:
  - [ ] Tabela menciona os 3 commands.

### Task D.5 — Hook pre-execution compartilhado (`learning_command_pre.py`)

- Agent: Backend Engineer
- Input: nenhuma
- Diagnostico:
  - Cada slash command NAO deveria precisar chamar `search.ts` na Fase 0
    manualmente (risco de esquecer). Solucao: hook `.opencode/hooks/learning_command_pre.py`
    do tipo `pre_request` que dispara automaticamente em todo comando,
    invoca `search.ts` com o `$ARGUMENTS` do payload, e injeta contexto.
  - Porem: opencode hooks `pre_request` rodam por chamada de tool, NAO
    por slash command. NAO existe hook canonico "UserPromptSubmit" em
    opencode. O hook `learning_prompt_submit.py` ja' tenta simular isso
    mas so' roda em tool calls.
  - Solucao pragmatica: cada command inclui explicitamente na Fase 0 uma
    chamada a `search.ts` (igual `/feature` ja' faz). Isso e' robusto e
    auditavel.
- Output:
  - NENHUM hook novo criado. Cada command chama `search.ts` na Fase 0
    explicitamente. Documentado na secao "RAG antes" de cada command.
- Criterios de aceitacao:
  - [ ] Cada command tem Fase 0 com `npx tsx .claude/scripts/search.ts`.

---

## Fase E — Documentacao e finalizacao (IMPORTANTE I10.x)

### Task E.1 — `AGENTS.md` bloco "Decisoes resolvidas (Sprint 10)"

- Agent: Prompt Engineer
- Output:
  - Bloco novo listando 5 decisoes:
    1. **Agente `@dev` e' o UNICO agent implementador** do DFe-Agent. Substitui os agents fragmentados (backend-engineer, ml-engineer, prompt-engineer, qa-engineer) que ficam em `.claude/agents/` como referencia historica. Para revisao read-only, use `code-reviewer`.
    2. **3 slash commands canonicos**: `/feature`, `/bug`, `/duvida`. Todos invocam `agent: dev`. Comandos `build` e `plan` foram removidos da interface.
    3. **`/bug` tem gate de aprovacao humana** entre investigacao (read-only) e correcao (write). Investigacao sempre termina com relatorio que pede "posso prosseguir?".
    4. **`/duvida` e' read-only por contrato**: nunca faz Write/Edit/Bash destrutivo. Captura Q&A canonico no RAG para consultas futuras.
    5. **RAG antes/depois em todos os commands**: Fase 0 invoca `search.ts` explicitamente; Fase final invoca `summarize.ts + embed.ts` explicitamente. Hooks `learning_*` continuam como safety net.

### Task E.2 — `.opencode/agent/README.md` (atualizar lista)

- Agent: Prompt Engineer
- Output:
  - Lista: `dfe-agent.md` (consulta fiscal), `dev.md` (implementacao owner), `code-reviewer.md` em `.opencode/agents/` (revisao read-only).

### Task E.3 — `.claude/README.md` (atualizar secao "Hooks opencode")

- Agent: Prompt Engineer
- Output:
  - Atualizar tabela de agent -> hooks para incluir `dev`.

### Task E.4 — Limpar referencias a `build` / `plan` no projeto

- Agent: dev (proprio agente da sprint)
- Diagnostico:
  - Buscar com `grep -r "build\|plan" --include='*.md' .` para localizar
    referencias orfas. As principais:
    - `.opencode/command/feature.md` (ja' corrigido em D.1)
    - `AGENTS.md` (a corrigir em E.1)
  - Garantir que nenhum command reference `agent: build` ou `agent: plan`.
- Output:
  - Diff: apenas substituicoes literais `build` -> `dev` em comandos,
    `plan` -> mantido apenas em `PLAN_SPRINT*.md` (documentos canonicos).
- Criterios de aceitacao:
  - [ ] `grep -r "agent: build" .opencode/` retorna 0 hits.
  - [ ] `grep -r "agent: plan" .opencode/` retorna 0 hits.

---

## Apêndice A — Riscos

| Risco | Probabilidade | Impacto | Mitigacao |
|-------|---------------|---------|-----------|
| `@dev` com `permission.edit: allow` em todo path permite bypass de guardrails de outros agents (ex.: edicao de `.claude/agents/code-reviewer.md` para desativar read-only) | Baixa | Alto | Guardrails de seguranca estao em 2 camadas: (1) `permission.*` no frontmatter do opencode; (2) hooks `.claude/hooks/dev/pre_tool_use.py` que bloqueiam comandos destrutivos globais (`git push`, `pip install`, `rm -rf`). NAO ha hook que bloqueia path especifico (escopo amplo). Code-review identifica violacoes post-hoc. |
| RAG meta-cognitivo cresce rapido com `dev` (cada command gera um .md) | Media | Baixo | Marker composto `(dev, session_id)` ja' existe no `_lib/learning.py`. Classificador heuristico categoriza por palavras-chave. `.claude/rag.db` suporta milhoes de chunks (sqlite-vec). |
| `/bug` gate de aprovacao humana quebra em CLI nao-interativa | Baixa | Medio | Documentado em `/bug.md`: se nao houver TTY (ex.: CI), o comando aborta com mensagem clara. |
| Opencode CLI `permission.*` nao suporta todos os campos tentados (`external_directory: deny` pode nao existir) | Media | Baixo | Verificar schema via `opencode agent list` (sanity). Se nao suportado, remover e ajustar. |
| `dev/` diretorio de hooks duplica logica de `backend-engineer/` (DRY violation) | Alta | Baixo | Decisao consciente: manutencao de paths separados vs. DRY. Por enquanto duplicar para evitar regressao no backend-engineer (que ainda funciona). Refatorar para helper compartilhado em Sprint futura. |
| Cobertura de testes dos hooks `dev/` adiciona muito ruido | Baixa | Baixo | Foco em 90% por hook (cobre gate de bloqueio + log + pytest dispatch). 100% nao e' meta. |

## Apêndice B — Fora do escopo

- **Refatorar `backend-engineer/`, `ml-engineer/`, etc.** para reusar `dev/`. Eles ficam como referencia historica. Migracao para `@dev` deve ser feita em sprint futura (BACKLOG).
- **Criar agente `dfe-fiscal`** (sub-delegacao da skill `dfe-fiscal`). Hoje o `dfe-agent.md` ja' cobre; nao duplicar.
- **Testes E2E reais** invocando `opencode run "/bug foo"` (depende de CLI no PATH do CI).
- **Auto-recuperacao do gate pytest** (se pytest falhar, rodar de novo em 30s). Fora do escopo desta sprint.
- **Visualizador web do RAG meta-cognitivo** (ja' fora de escopo de PLAN_SPRINT8 B.5).

## Apêndice C — Comandos shell para reproduzir a sprint manualmente

```bash
# Fase A
python -c "import yaml; yaml.safe_load(open('.opencode/agent/dev.md').read().split('---')[1])"
pytest tests/unit/test_dev_agent_definition.py -v

# Fase B
pytest tests/unit/hooks/test_dev_pre_tool_use.py -v
pytest tests/unit/hooks/test_dev_stop.py -v

# Fase C
pytest tests/unit/hooks/test_payload.py -v
pytest tests/integration/test_dev_plugin_dispatch.py -v

# Fase D
pytest tests/unit/test_commands_definitions.py -v

# Gate final
pytest tests/ --cov=src --cov-fail-under=80 -q
```

## Verificacao manual dos BLOQUEANTE

```powershell
# B10.1: agente @dev existe
Test-Path .opencode/agent/dev.md  # esperado: True
Test-Path .claude/agents/dev.md  # esperado: True

# B10.2: hooks do @dev existem
Test-Path .claude/hooks/dev/pre_tool_use.py  # True
Test-Path .claude/hooks/dev/post_tool_use.py  # True
Test-Path .claude/hooks/dev/stop.py  # True

# B10.3: RAG meta-cognitivo reconhece dev
Select-String -Path .claude/hooks/_lib/payload.py -Pattern '"dev"'
Select-String -Path .opencode/hooks/learning_prompt_submit.py -Pattern '"dev"'
Select-String -Path .opencode/plugin/agent-hooks.ts -Pattern '"dev"'

# B10.4: 3 slash commands existem
Test-Path .opencode/command/feature.md  # True
Test-Path .opencode/command/bug.md  # True
Test-Path .opencode/command/duvida.md  # True

# Sanity: nenhum command referencia build ou plan
Select-String -Path .opencode/command/*.md -Pattern 'agent: (build|plan)'  # esperado: zero hits
```
