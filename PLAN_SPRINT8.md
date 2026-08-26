# PLAN_SPRINT8.md

> Plano para **restaurar a captura de aprendizados** no RAG meta-cognitivo (`.claude/rag.db`).
> Origem: investigacao em 2026-08-26 revelou que `.claude/rag.db` esta' congelado em
> 11 chunks gerados pelo smoke test em 2026-08-25, sem nenhuma entrada nova desde entao.
> Itens cobertos: **1 BLOQUEANTE** (RAG meta-cognitivo nao captura) + ajustes correlatos.
> Principio: **TDD** (teste vermelho primeiro), zero regressao nas suites existentes,
> cobertura >= 80%.

## Criterio global de conclusao

`pytest tests/ --cov=src --cov-fail-under=80` retorna exit code 0 **E** o BLOQUEANTE
e verificado manualmente via:
1. Rodar uma sessao real de backend-engineer que edite `src/collector/foo.py`.
2. Encerrar a sessao.
3. Verificar que `.claude/knowledge/<data>-backend-engineer.md` foi criado.
4. Verificar que `.claude/rag.db` tem 1 chunk novo (consulta `SELECT COUNT(*) FROM knowledge` antes/depois).

```
Fase A ──► Fase B ──► Fase C ──► Fase D ──► Fase E
plugin     stop.py    helper     opencode    docs
load       capture    lib        .json       finalize
BLOQUEANTE BLOQUEANTE BLOQUEANTE IMPORTANTE  PARCIAL
```

**Dependencias criticas entre fases**:
- B depende de A — sem plugin carregado, stop.py nao dispara.
- B depende de C — stop.py precisa do helper `learning.py`.
- D depende de A — `opencode.json` so' referencia plugin depois de A funcionar.
- E depende de A+B+C+D.

## Resumo dos problemas observados

| ID | Sintoma | Causa raiz (resumo) |
|----|---------|---------------------|
| **B8.1** | `.claude/rag.db` nao cresce; `storage/learning_hook.log` tem 0 bytes; `.claude/storage/agent_hooks.log` tem 13 linhas (todas `pre_tool_use_block_*`); `.claude/knowledge/` so' tem 3 arquivos do smoke test de 2026-08-25 | Migracao da arquitetura A (manifest.json + learning_*.py) para B (plugin TS + .claude/hooks/<agent>/stop.py) em Sprints 4–6 substituiu os hooks que disparavam `summarize.ts → embed.ts` por hooks que so' rodam pytest. O pipeline de captura evaporou no refactor. |
| **B8.2** | `.opencode/opencode.json` (gerado pelo CLI) tem `{"plugin": ["list"]}` — path invalido | O usuario executou `opencode plugin add .opencode/plugin/agent-hooks.ts`, mas o CLI interpretou os argumentos de modo a gravar apenas o subcomando como entrada. O plugin nunca foi carregado. |
| **B8.3** | `manifest.json` com `learning_*` continua no repo (letra morta) | Hooks nao sao despachados pelo opencode (so' o plugin TS); `.opencode/hooks/manifest.json` nao tem loader em `opencode.json`. Mantido por compatibilidade historica mas nao executado. |

---

## Fase A — Carregar o plugin TS (BLOQUEANTE B8.2)

**Criterio**: `opencode run "..."` nao emite warning de plugin nao-carregado. `cat opencode.json` contem `"plugin": [".opencode/plugin/agent-hooks.ts"]`.

### Task A.1 — Adicionar `plugin` em `opencode.json` raiz

- Agent: Prompt Engineer
- Input: nenhuma
- Diagnostico:
  - `opencode.json` raiz tem apenas `instructions`. Sem `plugin`, o plugin TS nunca
    e carregado e todos os hooks pre/post/stop ficam inertes.
  - `.opencode/opencode.json` foi criado pelo CLI `opencode plugin add` com path
    invalido (`"list"` em vez do path real).
- Output:
  - `opencode.json`: adicionar `"plugin": [".opencode/plugin/agent-hooks.ts"]`.
  - **Remover** `.opencode/opencode.json` (gerado automaticamente, agora obsoleto).
  - Documentar em `.opencode/README.md` (1 paragrafo) o caminho canonico de instalacao
    via JSON em vez de via CLI `opencode plugin add` (evidencia em PLAN_SPRINT5 C.1).
- Criterios de aceitacao:
  - [ ] `git diff opencode.json` mostra so' a adicao do campo `plugin`.
  - [ ] `cat .opencode/opencode.json 2>/dev/null` nao retorna o arquivo (foi removido).
  - [ ] Documento `.opencode/README.md` explica a abordagem.

---

## Fase B — Capturar aprendizados no stop.py de cada agent (BLOQUEANTE B8.1)

**Criterio**: apos uma sessao com edicoes, `.claude/knowledge/<data>-<agent>.md` tem arquivo
novo E `.claude/rag.db` ganha entradas. Sessao sem edicoes nao gera entrada (escopo = so'
implementacoes).

### Task B.1 — Plugin TS: contar writes por session e injetar no payload do stop

- Agent: Backend Engineer
- Input: A.1 completa
- Diagnostico:
  - `tool.execute.after` em `.opencode/plugin/agent-hooks.ts:232` ja' dispara para
    Write/Edit/MultiEdit/NotebookEdit; precisamos contabilizar por session_id.
  - `event` handler em `agent-hooks.ts:258` envia payload minimo `{session_id, agent}`;
    precisamos enviar tambem `tool_writes_count`.
- Output:
  - `.opencode/plugin/agent-hooks.ts`:
    - Adicionar `Map<string, number>` para `writesPerSession`.
    - Em `tool.execute.after`: incrementar contador da session apos post_tool_use rodar.
    - Em `event`: incluir `tool_writes_count: writesPerSession.get(ev.sessionID ?? "", 0)`
      no payload enviado ao `profile.stop`.
    - Limpar contador da session ao final do `event` (evita crescimento ilimitado em
      sessoes longas).
- Criterios de aceitacao:
  - [ ] TypeScript compila (`npx tsc --noEmit` exit 0).
  - [ ] Teste novo em `tests/integration/test_agent_hooks_plugin.py` (ou extensao de
    existente): mock 2x `tool.execute.after` com mesmo sessionID, assert payload do
    `event` contem `tool_writes_count >= 2`.

### Task B.2 — Helper `_lib/learning.py` com summarize+embed assincrono

- Agent: Backend Engineer
- Input: nenhuma
- Diagnostico:
  - `learning_subagent_stop.py` ja' implementa summarize+embed async com marker de
    idempotencia; mas ele vive em `.opencode/hooks/`, fora do escopo do backend-engineer
    (`pre_tool_use.py` em `backend-engineer/pre_tool_use.py:66-67` ate' BLOQUEIA chamadas
    a `npx tsx .claude/scripts/(embed|search|summarize).ts`).
  - Solucao: extrair logica reutilizavel para `.claude/hooks/_lib/learning.py` (escopo
    neutro, fora do pre_tool_use gate); manter o `subagent_end` legado por compat.
- Output:
  - `.claude/hooks/_lib/learning.py` (NOVO, ~80 linhas):
    - `should_record(agent_slug: str, session_id: str) -> bool` — checa marker.
    - `marker_path(agent_slug: str, session_id: str) -> Path` — path canonico.
    - `spawn_summarize_then_embed(transcript_path: Path, agent_slug: str, session_id: str) -> int` —
      invoca `summarize.ts --stdout`, escreve `.md` em `.claude/knowledge/`, spawn
      `embed.ts --file <md>` em Popen detached (reusar `_spawn_detached` pattern de
      `learning_subagent_stop.py:53-68`).
    - Constantes `PROJECT_ROOT`, `LOG_PATH`, `KNOWLEDGE_DIR`, `TSX_BIN`.
  - Tipagem completa (sem `Any`).
- Criterios de aceitacao:
  - [ ] Cobertura de `.claude/hooks/_lib/learning.py` >= 95%.
  - [ ] Testes em `tests/unit/hooks/test_learning_helper.py` (NOVO, ~6 testes):
    - `test_should_record_returns_false_when_marker_exists`
    - `test_should_record_returns_true_when_marker_absent`
    - `test_marker_path_normalizes_special_chars` (slug com `/`, `\\`, espacos)
    - `test_spawn_summarize_then_embed_invokes_npx_with_correct_args` (spy em Popen)
    - `test_spawn_summarize_then_embed_skips_when_no_transcript` (transcript inexistente)
    - `test_spawn_summarize_then_embed_writes_md_then_spawns_embed` (integra summarize→md→spawn)

### Task B.3 — Editar `stop.py` de backend-engineer para chamar learning helper

- Agent: Backend Engineer
- Input: B.2 pronta (helper existe)
- Diagnostico:
  - `backend-engineer/stop.py:39` chama `run_pytest(...)`; em sucesso (rc=0) nada mais
    acontece — exatamente o gap que precisa fechar.
- Output:
  - `.claude/hooks/backend-engineer/stop.py`:
    - Importar `learning` helper de `.._lib.learning`.
    - Apos `if rc != 0: block(...)` e antes do `return 0`: bloco `if rc == 0 and
      payload.get("tool_writes_count", 0) > 0:` chama `learning.spawn_summarize_then_embed(...)`
      com `session_id = payload.get("session_id") or "<unknown>"`.
    - Logar `[backend-engineer] [learning_async] ...` em `agent_hooks.log`.
    - Se transcript nao disponivel em `.opencode/sessions/<id>.jsonl`, log de skip
      (mas NAO falha — captura pode voltar em sessoes futuras).
  - Pre-requisito: gate pytest existente continua valido (rc != 0 → block).
- Criterios de aceitacao:
  - [ ] Teste em `tests/integration/test_learning_stop_hook.py::test_backend_stop_runs_learning_after_pytest_passes` passa.
  - [ ] Teste em `tests/integration/test_learning_stop_hook.py::test_backend_stop_skips_learning_when_pytest_fails` passa.
  - [ ] Teste em `tests/integration/test_learning_stop_hook.py::test_backend_stop_skips_learning_when_no_edits` passa.

### Task B.4 — Editar `stop.py` de ml-engineer e prompt-engineer (mesmo padrao)

- Agent: Backend Engineer + Prompt Engineer
- Input: B.3 aplicada (padrao estabelecido)
- Output:
  - `.claude/hooks/ml-engineer/stop.py`: mesmo bloco de learning que B.3, com
    `agent_slug="ml-engineer"` e suite pytest inalterada (`tests/unit/indexer`).
  - `.claude/hooks/prompt-engineer/stop.py`: mesmo bloco de learning que B.3, com
    `agent_slug="prompt-engineer"` e suite pytest inalterada (3 testes de definicao).
- Criterios de aceitacao:
  - [ ] Testes `test_ml_stop_runs_learning_after_pytest_passes` e
    `test_prompt_stop_runs_learning_after_pytest_passes` passam.

### Task B.5 — Idempotencia por (agent_slug, session_id)

- Agent: Backend Engineer
- Input: B.3 + B.4
- Output:
  - Marker path agora usa chave composta: `_pending-<agent>-<session>.md.lock` em vez
    de apenas `_pending-<agent>.md.lock` (evita colisao entre sessoes do mesmo agent).
  - `learning.spawn_summarize_then_embed` cria marker apos sucesso do summarize
    (antes do spawn do embed); embed async nao precisa re-checar.
- Criterios de aceitacao:
  - [ ] Teste `test_spawn_is_idempotent_per_session` (2 chamadas com mesmo session_id,
    1 chamada com session_id diferente — apenas 1 marker por session_id).

---

## Fase C — Testes de integracao end-to-end (BLOQUEANTE B8.1)

**Criterio**: `pytest tests/integration/test_learning_stop_hook.py -v` exit 0.

### Task C.1 — Teste de integracao do pipeline stop → learning

- Agent: QA Engineer
- Input: B.3 completa
- Output:
  - `tests/integration/test_learning_stop_hook.py` (NOVO, ~5 testes):
    - `test_stop_runs_summarize_after_pytest_passes`: mock pytest rc=0, mock
      `learning.spawn_summarize_then_embed`, simular payload via stdin JSON, assert
      helper foi chamado1x com `(transcript_path=ANY, agent_slug="backend-engineer", session_id="sess-1")`.
    - `test_stop_skips_learning_when_pytest_fails`: pytest rc != 0 → block(2) →
      helper NAO foi chamado. Garante gate de qualidade.
    - `test_stop_skips_learning_when_no_edits`: payload sem `tool_writes_count` →
      helper NAO foi chamado. Garante escopo "so' implementacoes".
    - `test_stop_idempotent_per_session`: rodar stop.py 2x com mesmo payload → 2a
      chamada ve marker e nao chama helper.
    - `test_stop_spawns_only_after_pytest_passes_and_edits`: combinar pre-requisitos.
- Criterios de aceitacao:
  - [ ] Suite passa isolada: `pytest tests/integration/test_learning_stop_hook.py -v` exit 0.
  - [ ] Suite passa junto: `pytest tests/integration/ -v` exit 0.

---

## Fase D — opencode.json + ajustes finais (IMPORTANTE I8.1)

**Criterio**: plugin carregado + helpers funcionando + docs atualizadas.

### Task D.1 — Limpar `.opencode/opencode.json` (subproduto do CLI quebrado)

- Agent: Prompt Engineer
- Input: A.1 aplicada
- Output:
  - Confirmar ausencia do arquivo (foi removido em A.1).
  - Adicionar `.opencode/opencode.json` em `.gitignore` para evitar regeracao acidental.
- Criterios de aceitacao:
  - [ ] `git status` nao lista `.opencode/opencode.json`.
  - [ ] `.gitignore` contem `.opencode/opencode.json` (1 linha).

### Task D.2 — Adicionar testes para o plugin carregar (sanity check)

- Agent: QA Engineer
- Input: A.1 + B.1 aplicadas
- Output:
  - `tests/integration/test_agent_hooks_plugin_loads.py` (NOVO, 2 testes):
    - `test_plugin_default_export_is_function`: via `tsx`, executa
      `node -e "import('./.opencode/plugin/agent-hooks.ts').then(m => assert(typeof m.default === 'function'))"`
      e espera exit 0.
    - `test_plugin_opencode_json_has_plugin_field`: le `opencode.json` e assert
      `".opencode/plugin/agent-hooks.ts" in config["plugin"]`.
- Criterios de aceitacao:
  - [ ] Suite nova passa.

---

## Fase E — Documentacao e finalizacao (PARCIAL P8.1)

### Task E.1 — Atualizar `.claude/README.md` e `AGENTS.md`

- Agent: Prompt Engineer
- Output:
  - `.claude/README.md` secao "Hooks opencode (wrappers)": reescrever bloco para
    refletir a nova arquitetura. Tabela com hooks por agent, marker de idempotencia
    composto, link para `PLAN_SPRINT8.md`.
  - `AGENTS.md` "Decisoes resolvidas (Sprint 8)" (novo bloco): resumir 4 decisoes:
    1. `.claude/hooks/_lib/learning.py` e' o helper canonico para summarize+embed
       assincrono a partir de stop.py de agent.
    2. Marker de idempotencia agora e composto `(agent_slug, session_id)` em vez de
       apenas `agent_slug` (evita colisao entre sessoes).
    3. `opencode.json` raiz tem `"plugin": [".opencode/plugin/agent-hooks.ts"]`;
       instalacao via JSON em vez de via CLI `opencode plugin add`.
    4. Escopo de captura e apenas sessoes com `tool_writes_count > 0` (gate evita
       poluir RAG com sessoes de leitura pura).

### Task E.2 — Backfill manual dos PLANs 4–7 (opcional, nao-bloqueante)

- Agent: Backend Engineer
- Output:
  - 5 chamadas manuais:
    ```bash
    for plan in PLAN_SPRINT2 PLAN_SPRINT3 PLAN_SPRINT4 PLAN_SPRINT5 PLAN_SPRINT6 PLAN_SPRINT7; do
      npx tsx .claude/scripts/summarize.ts --input $plan.md --agent retro --date 2026-08-26
    done
    for f in .claude/knowledge/2026-08-26-retro.md; do
      npx tsx .claude/scripts/embed.ts --file "$f"
    done
    ```
  - Validar: `npx tsx .claude/scripts/search.ts -q "guard HTTP in-process"` retorna >= 1 chunk relevante.
- Criterios de aceitacao:
  - [ ] `.claude/rag.db` cresceu de 11 para ~40-80 chunks.
  - [ ] Search retorna resultados uteis para termos dos sprints anteriores.

### Task E.3 — Marcar este plano como concluido

- Agent: Backend Engineer
- Output:
  - Bloco "Decisoes resolvidas (Sprint 8)" adicionado ao `AGENTS.md`.

---

## Verificacao manual dos BLOQUEANTE

```powershell
# BLOQUEANTE B8.1: capture pipeline funcional end-to-end
# Pre-requisito: pelo menos 1 sessao de opencode que editou um arquivo .py em src/
$before = (npx.cmd tsx -e "const db = require('better-sqlite3')('.claude/rag.db'); console.log(db.prepare('SELECT COUNT(*) as c FROM knowledge').get().c)")
Write-Host "Antes: $before"

# Rodar uma sessao de teste (substitua pelo comando real do usuario):
opencode run --agent backend-engineer "edite src/collector/foo.py adicionando uma funcao de teste" "<encerre>"

# Apos encerramento, verificar crescimento:
$after = (npx.cmd tsx -e "const db = require('better-sqlite3')('.claude/rag.db'); console.log(db.prepare('SELECT COUNT(*) as c FROM knowledge').get().c)")
Write-Host "Depois: $after"
# esperado: $after > $before

# Verificar arquivos .md novos em .claude/knowledge/
Get-ChildItem .claude/knowledge/ -Filter *.md | Where-Object LastWriteTime -gt (Get-Date).AddHours(-1)
# esperado: pelo menos 1 arquivo com data recente

# Verificar log do learning hook
Get-Content storage/agent_hooks.log | Select-String "learning_async"
# esperado: pelo menos 1 linha

# BLOQUEANTE B8.2: plugin carregado
cat opencode.json | Select-String "plugin"
# esperado: contem ".opencode/plugin/agent-hooks.ts"

# Verificar que .opencode/opencode.json NAO existe (subproduto removido)
Test-Path .opencode/opencode.json
# esperado: False
```

---

## Apêndice A — Riscos conhecidos e mitigacoes

| Risco | Probabilidade | Impacto | Mitigacao |
|-------|---------------|---------|-----------|
| B.1 contador em memoria zera se opencode reinicia mid-session | Media | Baixo | Persistir contador em sidecar `.claude/state/<session_id>.writes.json` (criar em B.1 se necessario). Backlog para Sprint 9 se virar problema. |
| B.2 helper extraido de `learning_subagent_stop.py` introduz regressao | Baixa | Medio | Manter `learning_subagent_stop.py` chamando o mesmo helper; testes de smoke de `.claude/scripts/test_hooks.py` continuam passando. |
| B.5 marker composto quebra idempotencia existente | Baixa | Baixo | Limpar markers `_pending-*.md.lock` antigos antes de subir (`rm .claude/knowledge/_pending-*.md.lock`). |
| D.1 `.gitignore` de `.opencode/opencode.json` nao funciona porque ja' foi removido | Baixa | Baixo | Verificar `git status` antes de adicionar ao `.gitignore` para garantir que nao sera' commitado acidentalmente. |
| E.2 backfill gera muitos chunks irrelevantes (classificador heuristico) | Media | Baixo | Revisar manualmente `.claude/knowledge/2026-08-26-retro.md`; se ruido alto, refinar classificador antes de embedar (Sprint 9). |

## Apêndice B — Itens fora do escopo desta Sprint (follow-up)

1. **Backfill automatico via cronjob** de PLANs antigos (hoje manual em E.2).
2. **Sidecar persistente** para contador de writes (cobrir caso opencode reinicia mid-session).
3. **Refatorar `learning_subagent_stop.py` e `learning_stop.py`** para usar o novo helper
   (DRY completo). Hoje eles tem logica duplicada — funciona, mas nao e' canonico.
4. **Mover classificador heuristico para LLM** (quando parar de custar latencia). Heuristica
   cobre 80%+; o resto pode ser revisado manualmente.
5. **Visualizador web** para `.claude/rag.db` (similar ao `python -m src.ragctl stats`
   mas para meta-RAG). Nao bloqueia.
