---
description: Pipeline completo de feature — planning (sprint), implementacao TDD, testes, code review e persistencia no RAG meta-cognitivo. Re-executa o ciclo se o code review reportar BLOQUEANTE ou IMPORTANTE.
agent: dev
model: PROVIDER/MiniMax-M3
---

# /feature — Pipeline completo de feature do DFe-Agent

Voce disparou o pipeline canonico de entrega do DFe-Agent. Sua tarefa NAO e'
responder a pergunta do usuario: e' **planejar + implementar + testar + revisar
+ documentar** a feature descrita em `$ARGUMENTS` (texto livre; pode ser slug
ou descricao longa) ate que esteja pronta para entrega humana.

> O usuario (humano) e' o arbitro final. Voce NAO commita, NAO pusha, NAO abre
> PR. Sua entrega e' um conjunto de artefatos no working tree + um resumo
> estruturado.

---

## Fase 0 — Briefing obrigatorio (ler tudo ANTES de planejar)

| # | Acao | Comando / tool |
|---|---|---|
| 0.1 | Confirmar cwd do projeto (precisa ter `AGENTS.md`, `SPEC.md`, `PLAN.md`, `requirements.txt`, `pyproject.toml`, `storage/`, `.opencode/`) | `bash: pwd && ls AGENTS.md SPEC.md PLAN.md .opencode/ 2>/dev/null` |
| 0.2 | Estado do git | `bash: git rev-parse --is-inside-work-tree 2>/dev/null && git status --short && git log --oneline -10` |
| 0.3 | Ler contratos canonicos do projeto | `read: AGENTS.md, SPEC.md, PLAN.md, .opencode/rules/dfe-rules.md, .opencode/rules/*.md` |
| 0.4 | Localizar todas as sprints existentes (PLAN_SPRINT*.md) para nao colidir numeracao | `glob: PLAN_SPRINT*.md` |
| 0.5 | Recuperar aprendizados anteriores do RAG meta-cognitivo (top-5 do agent `dev`) | `bash: npx tsx .opencode/rag/search.ts -q "$ARGUMENTS" -a dev --top-k 5` |
| 0.6 | Sintetizar em 5 bullets: (a) onde estamos, (b) o que ja' existe, (c) gaps relativos a `$ARGUMENTS`, (d) decisoes resolvidas que vinculam, (e) restricoes inegociaveis (rules + "Nunca fazer" do AGENTS.md) | interno |

> **Gate 0**: se algum dos arquivos de 0.3 estiver ausente, ABORTE com
> "Este diretorio nao parece ser o root do DFe-Agent (faltam AGENTS.md / SPEC.md
> / .opencode/). Execute dentro do projeto." NAO invente estrutura.

---

## Fase 1 — Planning (sprint)

Objetivo: produzir `PLAN_SPRINT{n}.md` (sendo `n = max(existing) + 1` ou `1`
se nao existir PLAN_SPRINT*.md) seguindo **exatamente** o template do projeto.

### 1.1 — Numeracao

```bash
ls PLAN_SPRINT*.md 2>/dev/null | grep -oE '[0-9]+' | sort -n | tail -1
# ex.: "7" -> proxima sprint = 8
```

Se houver `PLAN_FEATURE_*.md` previo para a mesma feature, sobrescrever e
pular numeracao (mais barato do que fragmentar).

### 1.2 — Template obrigatorio do plano

O arquivo DEVE conter (nesta ordem):

1. **Cabecalho** com:
   - `# PLAN_SPRINT{n}.md` (ou `# PLAN_FEATURE_<slug>.md`)
   - Descricao de origem (`> Origem: pedido do usuario via /feature com argumento "$ARGUMENTS".`)
   - Principio: TDD, zero regressao, `cobertura >= 80%`.
   - Itens cobertos: contagem BLOQUEANTE/IMPORTANTE/PARCIAL quando aplicavel.

2. **Criterio global de conclusao**: 1-3 frases verificaveis via comando shell
   (ex.: `pytest tests/ --cov=src --cov-fail-under=80 exit 0`).

3. **Diagrama ASCII** de fases com setas `A -> B -> C` mostrando dependencias
   criticas entre fases.

4. **Tabela de IDs** (mesmo do PLAN_SPRINT7.md):
   - `B<n>` = BLOQUEANTE
   - `I<n>` = IMPORTANTE
   - `P<n>` = PARCIAL
   - `S<n>` = SUGESTAO

5. **Fases** — cada uma com:
   - Titulo `## Fase X — <nome> (<prefixos> : Bn, Im, ...)` 
   - "Criterio": comando shell + condicao de saida
   - Tasks `### Task X.n — <titulo>`:
     - `- Agent: <Backend Engineer | ML Engineer | Prompt Engineer | QA Engineer>`
     - `- Input:` dependencias
     - `- Output:` lista explicita de arquivos a criar/editar, com paths completos
     - `- Criterios de aceitacao:` checkboxes `[ ]` que viram `[x]` ao fim

6. **Apêndice A** — Riscos (tabela Risco / Probabilidade / Impacto / Mitigacao).
7. **Apêndice B** — Fora de escopo (bullets).
8. **Apêndice C** — Comandos shell para reproduzir a sprint manualmente.

### 1.3 — Granularidade

- Sprint com ate ~6 fases e ate ~20 tasks. Mais que isso = quebrar em 2 sprints.
- Cada task deve tocar 1-5 arquivos (caminho explícito no Output).
- Marcar paralelismo intra-fase explicitamente (ex.: "Task 2.1 e 2.2 em paralelo").

### 1.4 — Idempotencia do plano

Antes de escrever, verifique se ja' existe `PLAN_SPRINT{n}.md`:
- Se existe E foi criado por este pipeline: sobrescrever e seguir.
- Se existe E tem conteudo de humano: perguntar antes de sobrescrever.

### 1.5 — Gate 1 (passa para Fase 2)

- Arquivo `PLAN_SPRINT{n}.md` criado e validado contra a checklist do item 1.2.
- Marque um TODO list com Fase + Task para acompanhamento interno
  (`todowrite`). Cada task vira um item; serao marcados `completed` apenas
  APOS o teste critico correspondente passar.

---

## Fase 2 — Implementacao TDD (task por task)

Para CADA task listada no plano (na ordem do plano, respeitando paralelismo
quando aplicavel):

### 2.1 — Ciclo TDD

1. **Teste vermelho primeiro** — escrever o teste critico declarado no plano
   como `[ ]` em `tests/<suite>/<path>` espelhado a `src/`.
2. Rodar `pytest <caminho-do-teste> -x` — CONFIRMAR que falha (vermelho).
3. **Implementacao minima** — escrever codigo de producao em `src/<path>`.
4. Rodar `pytest <caminho-do-teste> -x` ate' verde.
5. Rodar `pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=80`
   para garantir zero regressao e cobertura minima.
6. Marcar a checkbox `[x]` no `PLAN_SPRINT{n}.md`.

> **NAO pular o teste vermelho**. E' a unica forma de provar que o teste de
> fato verifica algo. "Vai passar" nao conta.

### 2.2 — Guardrails durante implementacao

- Type hints em 100% das funcoes publicas de `src/`.
- `snake_case` em arquivos/modulos Python; `PascalCase` em classes;
  `UPPER_SNAKE_CASE` em constantes.
- Toda alteracao em `documents`/`vec_chunks` passa por
  `RagIndexer.ingest_pending` ou `apply_pending` (migration) — NUNCA INSERT
  raw.
- Toda chamada HTTP via `Throttler` (sem `requests.get` solto).
- Todo path passa pelo guardrail de `domain_guard.py` se tocar URL de rede.
- Comentarios apenas em trechos nao-obvios.

### 2.3 — Quando NAO e' TDD puro

- Mudanca de configuracao (`.opencode/`, `.opencode/rules/`, `opencode.json`):
  nao ha teste vermelho. Validar com `python -c "import yaml; yaml.safe_load(...)"`
  e `opencode command list` / `opencode agent list` se aplicavel.
- Mudanca de documentacao (markdown): validar com `python -c "import re; ..."`

### 2.4 — Gate 2 (passa para Fase 3)

- TODOS os testes criticos do plano marcados `[x]`.
- `pytest tests/ --cov=src --cov-fail-under=80` exit 0.
- `git status` mostra apenas os arquivos esperados pelo plano (mais docs auxiliares).

---

## Fase 3 — Garantir testes (gate obrigatorio)

Mesmo se Fase 2 terminou verde, rodar a suite **inteira** uma vez com cobertura
para servir de baseline:

```bash
pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=80
```

Capturar contadores:
- `test_count`, `coverage_pct`, `covered_lines`, `missing_lines`.

Se algum submodulo critico (`src/parser/` esperado em 100%, `src/indexer/`
esperado em >=95%) estiver abaixo do minimo: voltar para Fase 2 e escrever
testes faltantes ate' bater o alvo.

### Gate 3

- Suite completa verde.
- Cobertura dentro dos minimos do `AGENTS.md > Padroes de codigo` (80%
  global, 100% parser, >=95% indexer).

---

## Fase 4 — Code review (read-only, subagent)

Disparar o subagent `code-reviewer` sobre TODOS os arquivos modificados
(comparado contra `git status --short` ou `git diff --name-only`).

### 4.1 — Invocacao

Use a `task` tool (Task) com:

```yaml
subagent_type: code-reviewer
description: "Review feature $ARGUMENTS"
prompt: |
  Faca review read-only dos arquivos modificados nesta branch:

  ```
  <cole aqui a saida de git diff --name-only main..HEAD ou git status --short>
  ```

  Contexto: o pipeline /feature do DFe-Agent esta' fechando a entrega da
  feature descrita como "$ARGUMENTS". O plano da sprint atual esta' em
  PLAN_SPRINT{n}.md (em fase {Fase atual do pipeline}).

  Sua saida deve seguir EXATAMENTE o template definido em
  .opencode/agent/code-reviewer.md (BLOQUEANTE / IMPORTANTE / SUGESTAO).
  Reporte contagem por categoria no Resumo executivo.

  Cruzes Obrigatorios:
  - SPEC.md (proposito, criterios de aceitacao)
  - PLAN.md (padroes de tasks) + PLAN_SPRINT{n}.md (itens cobertos)
  - AGENTS.md (nomenclatura, TDD, "Nunca fazer", decisoes resolvidas)
  - .opencode/rules/dfe-rules.md (guardrails inviolaveis)
  - .opencode/rules/*.md (convencoes por caminho)

  NAO edite nada. Apenas reporte.
```

### 4.2 — Captura do relatorio

Capturar a saida do subagent como o relatorio canonico da Fase 4. O formato
obrigatorio (ja' garantido pelo subagent) tem: Resumo executivo, BLOQUEANTE,
IMPORTANTE, SUGESTAO, Itens verificados, Comandos.

### 4.3 — Gate 4

Relatorio emitido com contagens em cada categoria. Continua para Fase 5.

---

## Fase 5 — Loop corretivo (BLOQUEANTE / IMPORTANTE)

### 5.1 — Algoritmo

```
iteration = 0
max_iterations = 3
loop:
  iteration += 1
  if relatorio_vazio(BLOQUEANTE) and relatorio_vazio(IMPORTANTE):
    break  # passou limpo
  if iteration > max_iterations:
    reportar ao humano e pedir arbitragem
    break
  para cada item BLOQUEANTE em ordem:
    mapear para a task/arquivo que viola
    voltar para Fase 2 naquela task
    re-rodar testes ate' verde
  para cada item IMPORTANTE em ordem:
    idem BLOQUEANTE
  re-invocar code-reviewer (Fase 4)
```

### 5.2 — SUGESTAO nao bloqueia

Itens `SUGESTAO` sao registrados em `.opencode/rag/knowledge/<date>-dev-decisions.md`
para o humano arbitrar depois; NAO disparam correcao automatica.

### 5.3 — Itens nao corrigiveis pelo pipeline

Se o reviewer reportar violacao que depende de decisao humana (ex.:
"alterar `ALLOWED_DOMAINS` precisa de decisao humana documentada em
AGENTS.md"), registrar como BLOQUEANTE **bloqueado-por-humano** no relatorio
final, NAO continuar o loop.

### 5.4 — Gate 5

Relatorio final com **0 BLOQUEANTE** e **0 IMPORTANTE**. `iteration` registrado.

---

## Fase 6 — Documentar no RAG meta-cognitivo

Os hooks `.opencode/hooks/learning_*.py` ja' capturam transcript + summarize +
embed em background (fire-and-forget). Aqui voce faz a **persistencia
explicita e imediata** para garantir que o aprendizado da sprint sobreviva
mesmo que o hook assincrono seja perdido.

### 6.1 — Arquivo de decisao da feature

Criar `.opencode/rag/knowledge/<YYYY-MM-DD>-feature-<slug>.md` com:

```markdown
# Aprendizados -- feature <slug> -- <YYYY-MM-DD>

> Origem: /feature $ARGUMENTS
> Plano: PLAN_SPRINT{n}.md
> Relatorio final do code-reviewer: {N} BLOQUEANTE / {M} IMPORTANTE / {K} SUGESTAO
> Iteracoes do loop corretivo: {iteration}

## Bugs resolvidos com causa raiz
- {para cada BLOQUEANTE resolvido: sintoma, causa raiz, fix, arquivo:test}

## Decisoes de arquitetura e o porque
- {para cada decisao de design da sprint: opcao, alternativa descartada, justificativa, arquivo:test de cobertura}

## Padroes adotados pelo time
- {padroes novos que surgiram na sprint que deveriam virar regra em .opencode/rules/*.md}

## O que nao funcionou e por que
- {TDD inversoes, falsos vermelhos, fixtures que precisaram refazer, etc.}

## Arquivos modificados
- <lista completa com paths e 1-linha sobre cada>
```

### 6.2 — Embedding (IMEDIATO, sincrono)

```bash
npx tsx .opencode/rag/embed.ts --file .opencode/rag/knowledge/<arquivo>.md
```

Isto precisa ser sincrono (nao fire-and-forget) para garantir que a feature
ja' aparece no `search.ts` antes da proxima fase.

### 6.3 — Atualizar AGENTS.md (resumo da sprint)

Adicionar bloco em `AGENTS.md > Decisoes resolvidas (Sprint N)` com 4-6
bullets sumarizando as 4 decisoes mais importantes + caminhos das evidencias
(`PLAN_SPRINT{n}.md`, suites de teste, `.opencode/rag/knowledge/<...>.md`).

### 6.4 — Gate 6

- Arquivo `.opencode/rag/knowledge/<...>.md` criado.
- `embed.ts --file` retornou 0.
- `AGENTS.md` atualizado.
- `npx tsx .opencode/rag/search.ts -q "feature <slug>" -a dev --top-k 3`
  retorna >=1 hit (sanity check).

---

## Fase 7 — Finalizacao e entrega ao humano

### 7.1 — Checklist de saida

- [ ] `PLAN_SPRINT{n}.md` com TODOS os checkboxes de criterios de aceitacao `[x]`.
- [ ] `pytest tests/ --cov=src --cov-fail-under=80` verde (print do resumo final).
- [ ] Relatorio do code-reviewer com 0 BLOQUEANTE / 0 IMPORTANTE / {K} SUGESTAO.
- [ ] `.opencode/rag/knowledge/<...>-feature-<slug>.md` criado e embedado.
- [ ] `AGENTS.md` atualizado com bloco "Decisoes resolvidas (Sprint N)".

### 7.2 — Relatorio final (impresso ao humano)

```markdown
## Entrega — feature <slug> (Sprint {n})

**Plano**: `PLAN_SPRINT{n}.md`
**Argumento original**: `$ARGUMENTS`

### Tasks concluidas
{N}/{total} tasks do plano (lista enumerada com 1 linha cada)

### Suite
- pytest: {pass}/total ({fail} fail, {skip} skip)
- cobertura global: {pct}% (alvo 80%)
- src/parser/: {pct}% (alvo 100%)
- src/indexer/: {pct}% (alvo >=95%)

### Code review
- iteracoes do loop corretivo: {N}
- BLOQUEANTE final: 0
- IMPORTANTE final: 0
- SUGESTAO: {K} (registradas em .opencode/rag/knowledge/)

### Documentacao RAG
- .opencode/rag/knowledge/{arquivo}.md criado e embedado
- search sanity: {N} hits para "feature {slug}"

### O que NAO foi feito (decisao humana pendente)
- {bullets, se houver}

### Proxima acao humana
- `git add -A && git diff --cached` para revisar o que sera comitado
- revisar `.opencode/rag/knowledge/<...>.md`
- revisar SUGESTOES do code-reviewer
- commit + push (voce NAO commita)
```

### 7.3 — Gate 7 (entrega ao humano)

Imprimir o relatorio 7.2 e parar. NAO commitar, NAO chamar `git push`,
NAO abrir PR. O humano decide.

---

## Guardrails inegociaveis (valem em qualquer fase)

- **Regra de veracidade** (`AGENTS.md > Nunca fazer`): NAO inventar
  informacao fiscal na resposta ao usuario. Este comando e' de entrega, nao
  de Q&A sobre o dominio — mas qualquer mensagem ao humano sobre o estado
  parcial da entrega deve ser precisa (nao "terminei tudo" quando nao
  terminou; nao "100% verde" quando ha skip marcados).
- **Sem secrets em commit**: nunca gravar `.env`, dumps de `storage/*.db`,
  transcriptions completas. Antes de sugerir `git add`, verificar `git status`
  e comparar contra `.gitignore`.
- **Sem captura nao-autorizada**: dominio fora de `ALLOWED_DOMAINS` e'
  bloqueado por `domain_guard` (hook `pre_request`). Este comando NAO faz
  scraping direto; apenas consulta a base local.
- **Sem reprocessamento**: documento com `status="ingerido"` NAO e'
  reingerido. Idempotencia por hash e' obrigatoria.
- **Sem COMMIT**: o humano fecha o commit.

## Quando abortar (e reportar ao humano)

| Sintoma | Acao |
|---|---|
| `git rev-parse` falha ou `AGENTS.md` ausente | Abortar — nao e' o repo do DFe-Agent |
| Bloqueante "depende de decisao humana" surge no code review | Nao iterar; registrar e parar |
| `iteration > 3` no loop corretivo | Registrar, pedir arbitragem humana |
| Cobertura nao sobe para alvo mesmo com novos testes | Parar e pedir diagnostico humano |
| Hooks `.opencode/hooks/learning_*` retornam diferente de 0 | Nao bloqueia (abort_on_nonzero=false), mas avisar |
| Codigo viola "Nunca fazer" do AGENTS.md | Reverter mudanca, registrar incidente como BLOQUEANTE em `.opencode/rag/knowledge/incident-<slug>.md`, pedir arbitragem |

## Para debugar este command

- `opencode command list` deve listar `/feature`.
- `opencode command show /feature` (se existir no CLI) mostra o body.
- Mensagem de log do agent principal fica em `storage/agent_hooks.log` (hooks
  `pre_tool_use` etc.).
