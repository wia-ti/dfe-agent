---
description: Responde duvidas sobre o DFe-Agent SEMPRE lendo o projeto antes. Read-only por contrato — nunca faz Write/Edit/Bash destrutivo. Captura Q&A canonico no RAG meta-cognitivo para consultas futuras.
agent: dev
model: PROVIDER/MiniMax-M3
---

# /duvida — Resposta fundamentada lendo o projeto

Voce disparou o comando canonico de Q&A do DFe-Agent. Sua tarefa NAO e'
inventar resposta: e' **LER o projeto** (Read, Grep, Glob), formular
resposta com citacao literal de paths (`file_path:line_number`), gravar
o Q&A no RAG meta-cognitivo e entregar.

Argumento recebido: `$ARGUMENTS` (a pergunta do usuario em linguagem
natural).

> **Read-only por contrato**: este comando NAO faz Write/Edit. NAO faz
> `git commit`, `pip install`, scraper, ingestao, ou qualquer acao que
> altere estado. Apenas leitura + RAG append.

---

## Fase 0 — Briefing + RAG antes (ler tudo ANTES de responder)

| # | Acao | Comando / tool |
|---|---|---|
| 0.1 | Confirmar cwd do projeto | `bash: pwd && ls AGENTS.md SPEC.md PLAN.md .opencode/ 2>/dev/null` |
| 0.2 | Estado do git (read-only) | `bash: git rev-parse --is-inside-work-tree 2>/dev/null && git log --oneline -10` |
| 0.3 | Ler contratos canonicos do projeto | `read: AGENTS.md, SPEC.md, PLAN.md, .opencode/rules/dfe-rules.md, .opencode/rules/*.md` |
| 0.4 | **RAG antes** — buscar Q&A canonicos anteriores | `bash: npx tsx .opencode/rag/search.ts -q "$ARGUMENTS" -a dev --top-k 5` |
| 0.5 | Sintetizar em 3 bullets: (a) onde a resposta provavelmente vive (arquivo), (b) regras aplicaveis, (c) Q&A anteriores relevantes | interno |

> **Gate 0**: se algum arquivo de 0.3 faltar, ABORTE com "Este diretorio nao
> parece ser o root do DFe-Agent."

> **Por que RAG antes**: perguntas recorrentes ja' tem Q&A canonico no
> `.opencode/rag/rag.db` (categoria `team_pattern` ou `architecture_decision`).
> Aproveitar evita formular resposta inconsistente com decisoes anteriores.

---

## Fase 1 — Leitura ativa do projeto (read-only)

Objetivo: identificar os arquivos exatos que respondem `$ARGUMENTS`.

### 1.1 — Escopo da duvida

Classifique `$ARGUMENTS` em 1 categoria:

| Categoria | Onde procurar |
|---|---|
| `architecture` / `design` | `AGENTS.md`, `SPEC.md`, `PLAN.md`, `.opencode/rules/*.md` |
| `como funciona X` | `src/<modulo>/<arquivo>.py` + `tests/unit/<modulo>/` espelhado |
| `onde esta Y` | `grep -r "Y" --include='*.py' src/ tests/` |
| `decisao passada` | `AGENTS.md > Decisoes resolvidas (Sprint N)`, `.opencode/rag/knowledge/` |
| `guardrail / proibicao` | `AGENTS.md > Nunca fazer`, `.opencode/rules/dfe-rules.md`, `.opencode/hooks/` |
| `config / setup` | `requirements.txt`, `pyproject.toml`, `opencode.json`, `.opencode/`, `.opencode/` |
| `CLI / comando` | `python -m src.<x> --help`, `src/<x>/__main__.py` |

### 1.2 — Listar arquivos candidatos ANTES de abrir

Use Glob + Grep para enumerar candidatos sem ler todos:
- `glob: src/**/<termo>*.py`
- `grep: "<termo>" --include='*.py' --include='*.md' src/ tests/ .opencode/ .opencode/ AGENTS.md`
- `grep: "^### \|^## " --include='*.md' AGENTS.md SPEC.md PLAN.md`

### 1.3 — Ler arquivos relevantes

Para cada candidato:
- `read: <caminho>` com `limit`/`offset` se for arquivo grande.
- Identifique o trecho exato (linha ou bloco) que responde.
- Se necessario, leia testes espelhados (`tests/unit/<modulo>/`) para
  entender o comportamento esperado.

### 1.4 — Cruzar com regras/decisoes

Se a duvida toca em decisao/regra, leia:
- `AGENTS.md > Padroes de codigo`
- `AGENTS.md > "Nunca fazer"`
- `AGENTS.md > Decisoes resolvidas (Sprint N)` (todos os blocos)
- `.opencode/rules/*.md`

### 1.5 — Gate 1

Conjunto de arquivos + trechos relevantes identificados. Prosseguir
para Fase 2.

---

## Fase 2 — Resposta fundamentada (com citacao literal)

### 2.1 — Estrutura da resposta

```markdown
## Resposta — <slug da duvida>

<Resposta em portugues, 2-5 paragrafos. Tom direto e objetivo.>

### Evidencias no projeto

- `<arquivo:linha>` — <frase citando o que esta' la>.
- `<arquivo:linha>` — <frase citando o que esta' la>.

### Fontes adicionais

- `AGENTS.md > Secao X` — <citacao da regra aplicada>.
- `SPEC.md > Secao Y` — <citacao do criterio>.
- `PLAN_SPRINT{n}.md > Task Z.W` — <citacao da implementacao>.

### Limitacoes

- <Se a duvida nao tem resposta canonica no projeto: declare
  explicitamente.>
- <Se a duvida extrapolaria o escopo do projeto: aponte.>
```

### 2.2 — Regras de formatacao

- Toda evidencia inclui `file_path:line_number` no formato
  `<caminho/relativo>:<N>` (sem extensao se possivel, igual a
  `.opencode/agent/dfe-agent.md`).
- Toda citacao de codigo usa bloco de codigo com a linguagem
  (````python`, ```bash`, ```yaml`).
- Quando nao houver base para responder: escreva literalmente
  `Nao encontrei base no projeto para responder` (analogia ao
  `NO_EVIDENCE_MESSAGE` do dfe-agent).
- Tom de voz: objetivo, sem rodeios. Sem auto-promo ("claro!",
  "com prazer!", "otima pergunta!").

### 2.3 — Gate 2

Resposta formatada com `file_path:line_number` para cada evidencia.
Prosseguir para Fase 3.

---

## Fase 3 — Capturar no RAG meta-cognitivo

> **RAG depois**: este command SEMPRE grava o Q&A canonico no
> `.opencode/rag/knowledge/` e roda `embed.ts`. O proximo `/duvida <topico>`
> similar podera aproveitar este chunk via `search.ts`.

### 3.1 — Arquivo de Q&A canonico

Criar `.opencode/rag/knowledge/<YYYY-MM-DD>-dev-qa-<slug>.md` com:

```markdown
# Q&A — <slug da duvida> -- <YYYY-MM-DD>

> Origem: /duvida $ARGUMENTS
> Categoria: <architecture|team_pattern|what_didnt_work|bug_root_cause>

## Pergunta original

> $ARGUMENTS (texto exato do usuario)

## Resposta canonica

<Resposta da Fase 2, reformatada em paragrafos curtos e citacoes
inline `file_path:line_number`.>

## Fontes citadas

- `<arquivo:linha>` — <descricao>.
- `AGENTS.md > Secao X` — <descricao>.

## Quem pode precisar desta resposta

- <Cenario de uso futuro>
```

### 3.2 — Embedding (IMEDIATO, sincrono)

```bash
npx tsx .opencode/rag/embed.ts --file .opencode/rag/knowledge/<arquivo>.md
```

Sincrono (nao fire-and-forget) para garantir que o Q&A ja' aparece
no `search.ts` antes da proxima fase.

### 3.3 — Gate 3

- Arquivo `.opencode/rag/knowledge/<...>-qa-<slug>.md` criado.
- `embed.ts --file` retornou 0.
- `npx tsx .opencode/rag/search.ts -q "<topico>" -a dev --top-k 3`
  retorna >=1 hit (sanity check do RAG append).

---

## Fase 4 — Entrega ao humano

### 4.1 — Relatorio final (impresso ao humano)

A resposta da Fase 2 + bloco de Fontes + relatorio de captura RAG:

```markdown
## Q&A capturado no RAG

- /duvida "<pergunta original>"
- Categoria: <X>
- Arquivo: `.opencode/rag/knowledge/<YYYY-MM-DD>-dev-qa-<slug>.md`
- Embedding: aplicado (sanity hit em search.ts)
```

### 4.2 — Gate 4 (entrega)

Imprimir a resposta e o relatorio 4.1 e parar. **NAO** altere nenhum
arquivo do projeto (read-only por contrato).

---

## Guardrails inegociaveis

- **Read-only por contrato**: NUNCA Write/Edit/Bash destrutivo.
- **NUNCA inventar resposta**: se nao houver base no projeto,
  declarar literalmente `Nao encontrei base no projeto para responder`.
- **Citacao obrigatoria**: toda evidencia vem de `file_path:line_number`
  confirmado via `Read` ou `Grep` (NAO de memoria do LLM).
- **Sem secrets em log**: NUNCA imprimir `.env`, `storage/*.db`,
  transcripts em texto cru.

## Quando abortar

| Sintoma | Acao |
|---|---|
| `git rev-parse` falha ou `AGENTS.md` ausente | Abortar — nao e' o repo do DFe-Agent |
| Pergunta e' sobre dominio fiscal (NF-e, NT, etc.) | Delegar: "Use o agent `dfe-agent` (subagent principal) que tem a skill `dfe-fiscal`." |
| Pergunta exige implementar codigo | Sugerir `/feature <descricao>` em vez de responder |
| Hook `learning_*` retorna !=0 | Nao bloqueia (abort_on_nonzero=false), avisar |

## Para debugar este command

- `opencode command list` deve listar `/duvida`.
- O agent ativo sera `dev` (via `DFE_ACTIVE_AGENT=dev`).
- Q&A canonicos ficam em `.opencode/rag/knowledge/*-dev-qa-*.md`.
