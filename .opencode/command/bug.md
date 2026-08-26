---
description: Pipeline completo de correcao de bug — investigar a causa raiz em modo read-only, relatar pedindo aprovacao humana ANTES de corrigir, corrigir com TDD, code review, persistencia no RAG meta-cognitivo. Re-executa o ciclo se o code review reportar BLOQUEANTE ou IMPORTANTE.
agent: dev
model: PROVIDER/MiniMax-M3
---

# /bug — Pipeline completo de correcao de bug do DFe-Agent

Voce disparou o pipeline canonico de correcao de bug do DFe-Agent.
Sua tarefa NAO e' responder a pergunta do usuario: e' **investigar a
causa raiz em modo read-only, relatar pedindo aprovacao explicita e
so' entao corrigir com TDD + code review + RAG**.

Argumento recebido: `$ARGUMENTS` (descricao do bug, sintoma, mensagem
de erro, ou caminho do teste que falha).

> **Gate humano obrigatorio**: este comando tem 1 aprovacao explicita
> entre a investigacao (read-only) e a correcao (write). NAO escreva
> em arquivos ate' receber "sim, prossiga" ou equivalente.

---

## Fase 0 — Briefing obrigatorio + RAG antes (ler tudo ANTES de investigar)

| # | Acao | Comando / tool |
|---|---|---|
| 0.1 | Confirmar cwd do projeto | `bash: pwd && ls AGENTS.md SPEC.md PLAN.md .opencode/ 2>/dev/null` |
| 0.2 | Estado do git | `bash: git rev-parse --is-inside-work-tree 2>/dev/null && git status --short && git log --oneline -10` |
| 0.3 | Ler contratos canonicos | `read: AGENTS.md, SPEC.md, PLAN.md, .opencode/rules/dfe-rules.md, .opencode/rules/*.md` |
| 0.4 | Localizar sprints existentes | `glob: PLAN_SPRINT*.md` |
| 0.5 | **RAG antes** — buscar aprendizados de bugs anteriores | `bash: npx tsx .opencode/rag/search.ts -q "$ARGUMENTS" -a dev --top-k 5` |
| 0.6 | Sintetizar em 5 bullets: (a) onde estamos, (b) o que ja' existe, (c) bugs similares em sprints anteriores, (d) decisoes vinculadas, (e) restricoes inegociaveis | interno |

> **Gate 0**: se algum arquivo de 0.3 faltar, ABORTE com "Este diretorio nao
> parece ser o root do DFe-Agent (faltam AGENTS.md / SPEC.md / .opencode/).
> Execute dentro do projeto."

> **Por que RAG antes**: o `.opencode/rag/rag.db` guarda aprendizados de bugs
> passados. Aproveitar evita reinventar a roda (mesma causa raiz,
> mesmo fix, mesmo teste).

---

## Fase 1 — Investigacao READ-ONLY (zero Write/Edit ate' aprovacao)

Objetivo: caracterizar o sintoma, identificar a causa raiz, listar
arquivos candidatos, levantar hipoteses alternativas. **NAO modifique
nenhum arquivo nesta fase.** Apenas Read, Grep, Glob, Bash (read-only).

### 1.1 — Sintoma

Reproduza o sintoma. Se houver teste que falha:
`bash: pytest <caminho-do-teste> -x 2>&1 | head -50`

Se nao houver teste, crie um caso de reproducao mental:
- Input: $ARGUMENTS (texto livre do usuario)
- Comando que dispara: (sintetizado)
- Saida observada: (erro, stack trace, log)
- Saida esperada: (comportamento correto)

### 1.2 — Causa raiz

Use a tecnica dos "5 porques" + leitura de codigo:
- Por que acontece? (sintoma mais proximo da causa)
- Por que isso? (1 nivel acima)
- ...ate' chegar na causa raiz (decisao de design, schema, ausencia
  de teste, regressao).

Ferramentas:
- `grep "<termo>"` em `src/`, `tests/`, `.opencode/`.
- `git log -p -- <arquivo>` para regressoes recentes.
- `git blame <arquivo>:<linha>` para identificar a linha exata.

### 1.3 — Arquivos candidatos

Liste os arquivos que provavelmente precisam de mudanca:
- Arquivo X (linhas Y-Z): porque precisa mudar.
- Arquivo W (linha V): porque precisa de teste novo.

### 1.4 — Hipoteses alternativas

Liste 1-3 hipoteses alternativas:
- Hipotese A: causa raiz X1 (probabilidade ~X%).
- Hipotese B: causa raiz X2 (probabilidade ~X%).
- Hipotese C: regressao de fix anterior (probabilidade ~X%).

### 1.5 — Gate 1

Relatorio de investigacao COMPLETO escrito. ZERO Write/Edit realizado.
Prosseguir para Fase 2.

---

## Fase 2 — Relatorio + APROVACAO HUMANA (gate inegociavel)

### 2.1 — Formato do relatorio

```markdown
## Relatorio de investigacao — bug <slug>

**Sintoma**: <frase objetiva com comando/erro exato>
**Causa raiz**: <frase objetiva apontando o codigo/linha>
**Arquivos a editar**: <lista com paths e justificativa>
**Teste novo**: <descricao do teste vermelho que cobre o bug>
**Hipoteses alternativas**: <lista>
**Esforco estimado**: <X horas / Y testes / Z arquivos>

**Decisao solicitada**: posso prosseguir com a correcao? (responda "sim, prossiga" para gate de Fase 3)
```

### 2.2 — PARAR e pedir aprovacao

Imprima o relatorio 2.1 e **PARE**. NAO faca Write/Edit. NAO faca
pytest (ate' ser aprovacao NAO precisa do teste vermelho).

> **Por que este gate**: a correcao pode tocar 5+ arquivos e custar
> 1-2 horas. Sem aprovacao humana, o agente pode interpretar mal o bug
> e implementar o fix errado. A aprovacao explicita garante alinhamento.

### 2.3 — Se o usuario pedir mais investigacao

Volte para Fase 1 com foco na duvida. NAO avance para Fase 3.

### 2.4 — Se o usuario reprovar

Encerre com resumo do que foi investigado. NAO corrija. A decisao e'
do humano.

### 2.5 — Gate 2 (passa para Fase 3)

Resposta explicita do humano autorizando (qualquer frase equivalente a
"sim, prossiga"). Sem isso, ABORTAR.

---

## Fase 3 — Correcao TDD (gate duplo: pytest + code review)

> **Gate duplo**: correcao so' comeca apos Fase 2.5. Em paralelo com
> a correcao, registre TODO list (`todowrite`) com cada task para
> acompanhamento.

### 3.1 — Teste vermelho primeiro

1. Escrever o teste critico declarado no relatorio como `[ ]` em
   `tests/<suite>/<path>` espelhado a `src/`.
2. Rodar `pytest <caminho-do-teste> -x` — CONFIRMAR vermelho.
3. **NAO pular o teste vermelho.** E' a unica forma de provar que o
   teste de fato cobre o bug.

### 3.2 — Implementacao minima

1. Escrever codigo de producao em `src/<path>` com type hints.
2. Rodar `pytest <caminho-do-teste> -x` ate' verde.
3. Rodar `pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=80`
   para garantir zero regressao.

### 3.3 — Guardrails durante implementacao

- Type hints em 100% das funcoes publicas.
- `snake_case` em arquivos/modulos Python; `PascalCase` em classes;
  `UPPER_SNAKE_CASE` em constantes.
- Toda alteracao em `documents`/`vec_chunks` via `RagIndexer.ingest_pending`
  ou `apply_pending` — NUNCA INSERT raw.
- Toda chamada HTTP via `Throttler` — sem `requests.get` solto.
- Cobertura: 80% global em `src/`, 100% em `src/parser/`, >=95% em
  `src/indexer/`.

### 3.4 — Gate 3

- Teste vermelho -> verde documentado no relatorio.
- Suite geral verde.
- `pytest tests/ --cov=src --cov-fail-under=80` exit 0.

---

## Fase 4 — Code review (read-only, subagent)

Disparar o subagent `code-reviewer` sobre TODOS os arquivos modificados.

### 4.1 — Invocacao

Use a `task` tool (Task) com:

```yaml
subagent_type: code-reviewer
description: Review bugfix <slug>
prompt: |
  Faca review read-only dos arquivos modificados nesta branch:
  <cole aqui `git diff --name-only main..HEAD` ou `git status --short`>

  Contexto: o pipeline /bug do DFe-Agent esta' fechando a entrega do
  bugfix descrito como "$ARGUMENTS". O relatorio de investigacao foi
  aprovado pelo humano na Fase 2.

  Sua saida deve seguir EXATAMENTE o template definido em
  .opencode/agent/code-reviewer.md (BLOQUEANTE / IMPORTANTE / SUGESTAO).

  Cruzes Obrigatorios:
  - SPEC.md, PLAN.md, AGENTS.md
  - .opencode/rules/dfe-rules.md
  - .opencode/rules/*.md
  - Cobre o bug do relatorio? O teste vermelho -> verde documentado?

  NAO edite nada. Apenas reporte.
```

### 4.2 — Captura do relatorio

Capturar a saida do subagent. Formato obrigatorio: Resumo executivo,
BLOQUEANTE, IMPORTANTE, SUGESTAO, Itens verificados, Comandos.

### 4.3 — Gate 4

Relatorio emitido com contagens. Prosseguir para Fase 5.

---

## Fase 5 — Loop corretivo (BLOQUEANTE / IMPORTANTE)

### 5.1 — Algoritmo

```
iteration = 0
max_iterations = 3
loop:
  iteration += 1
  if relatorio_vazio(BLOQUEANTE) and relatorio_vazio(IMPORTANTE):
    break
  if iteration > max_iterations:
    reportar ao humano e pedir arbitragem
    break
  para cada item BLOQUEANTE em ordem:
    mapear para o arquivo que viola
    voltar para Fase 3 naquele arquivo
    re-rodar testes ate' verde
  para cada item IMPORTANTE em ordem:
    idem BLOQUEANTE
  re-invocar code-reviewer (Fase 4)
```

### 5.2 — SUGESTAO nao bloqueia

Itens `SUGESTAO` sao registrados em
`.opencode/rag/knowledge/<date>-dev-suggestions.md` para o humano arbitrar
depois; NAO disparam correcao automatica.

### 5.3 — Gate 5

Relatorio final com **0 BLOQUEANTE** e **0 IMPORTANTE**. `iteration`
registrado.

---

## Fase 6 — Documentar no RAG meta-cognitivo

> **RAG depois**: este command SEMPRE grava o aprendizado do bugfix no
> RAG meta-cognitivo, independente do que os hooks `learning_*` fizerem
> em background. Garante sobrevivencia do conhecimento.

### 6.1 — Arquivo de decisao do bug

Criar `.opencode/rag/knowledge/<YYYY-MM-DD>-dev-bug-<slug>.md` com:

```markdown
# Bugfix <slug> -- <YYYY-MM-DD>

> Origem: /bug $ARGUMENTS
> Relatorio do code-reviewer: {N} BLOQUEANTE / {M} IMPORTANTE / {K} SUGESTAO
> Iteracoes do loop corretivo: {iteration}

## Sintoma
- Comando/erro exato que o usuario reportou.

## Causa raiz
- Arquivo:linha + por que a regra/decisao foi violada.

## Teste vermelho -> verde
- Arquivo de teste + 1 frase sobre o que ele cobre.

## Fix
- Arquivo:linha + 1 frase sobre o que mudou.

## Hipoteses alternativas descartadas
- H1: ... (probabilidade X%, refutada por ...).
- H2: ...

## Arquivos modificados
- <lista completa com paths e 1-linha sobre cada>
```

### 6.2 — Embedding (IMEDIATO, sincrono)

```bash
npx tsx .opencode/rag/embed.ts --file .opencode/rag/knowledge/<arquivo>.md
```

Isto precisa ser sincrono (nao fire-and-forget) para garantir que o
bugfix ja' aparece no `search.ts` antes da proxima fase.

### 6.3 — Atualizar AGENTS.md (se for bugfix de decisao)

Se o bugfix revelar uma regra/decisao nova, adicionar em
`AGENTS.md > Decisoes resolvidas (Sprint N)`. Caso contrario, skip.

### 6.4 — Gate 6

- Arquivo `.opencode/rag/knowledge/<...>.md` criado.
- `embed.ts --file` retornou 0.
- `npx tsx .opencode/rag/search.ts -q "bug <slug>" -a dev --top-k 3`
  retorna >=1 hit (sanity check).

---

## Fase 7 — Finalizacao e entrega ao humano

### 7.1 — Checklist de saida

- [ ] Relatorio de investigacao (Fase 2) entregue e aprovado.
- [ ] Teste vermelho -> verde documentado.
- [ ] `pytest tests/ --cov=src --cov-fail-under=80` verde.
- [ ] Relatorio do code-reviewer com 0 BLOQUEANTE / 0 IMPORTANTE.
- [ ] `.opencode/rag/knowledge/<...>-bug-<slug>.md` criado e embedado.
- [ ] `AGENTS.md` atualizado (se aplicavel).

### 7.2 — Relatorio final (impresso ao humano)

```markdown
## Entrega — bugfix <slug>

**Argumento original**: `$ARGUMENTS`
**Sintoma + causa raiz**: <1 frase cada>

### Aprovacao humana
- Relatorio enviado em Fase 2: <resumo>
- Aprovacao recebida em <timestamp>: <sim/prossiga/etc>

### Correcao
- Arquivos modificados: {N}
- Testes novos: {N}
- pytest: {pass}/{total} ({fail} fail, {skip} skip)
- cobertura global: {pct}%
- src/parser/: {pct}%
- src/indexer/: {pct}%

### Code review
- iteracoes do loop corretivo: {N}
- BLOQUEANTE final: 0
- IMPORTANTE final: 0
- SUGESTAO: {K} (em .opencode/rag/knowledge/)

### RAG meta-cognitivo
- .opencode/rag/knowledge/{arquivo}.md criado e embedado
- search sanity: {N} hits para "bug {slug}"

### Proxima acao humana
- `git add -A && git diff --cached` para revisar
- revisar `.opencode/rag/knowledge/<...>.md`
- revisar SUGESTOES do code-reviewer
- commit + push (voce NAO comita)
```

### 7.3 — Gate 7 (entrega ao humano)

Imprimir o relatorio 7.2 e parar. NAO comitar.

---

## Guardrails inegociaveis (valem em qualquer fase)

- **Gate humano obrigatorio (Fase 2.5)**: NAO escreva em arquivos ate'
  receber aprovacao explicita. Investigacao e' read-only.
- **Regra de veracidade**: NAO inventar causa raiz. Se a investigacao
  nao conseguir apontar causa raiz, PARE e peça ao humano.
- **Sem secrets em commit**: antes de sugerir `git add`, verificar
  `.gitignore` nao inclui `.env`, `storage/*.db`, etc.
- **Sem captura nao-autorizada**: dominio fora de `ALLOWED_DOMAINS` e'
  bloqueado por `domain_guard`. Este comando NAO faz scraping.
- **Sem COMMIT**: o humano fecha.

## Quando abortar (e reportar ao humano)

| Sintoma | Acao |
|---|---|
| `git rev-parse` falha ou `AGENTS.md` ausente | Abortar — nao e' o repo do DFe-Agent |
| Usuario nao aprova em Fase 2 | Registrar investigacao, NAO corrigir |
| `iteration > 3` no loop corretivo | Registrar, pedir arbitragem humana |
| Cobertura nao sobe para alvo | Parar e pedir diagnostico humano |
| Hook `learning_*` retorna !=0 | Nao bloqueia (abort_on_nonzero=false), avisar |
| Codigo viola "Nunca fazer" do AGENTS.md | Reverter, registrar como BLOQUEANTE |

## Para debugar este command

- `opencode command list` deve listar `/bug`.
- O agent ativo sera `dev` (via `DFE_ACTIVE_AGENT=dev` setado pelo opencode).
- Logs em `storage/agent_hooks.log`.
