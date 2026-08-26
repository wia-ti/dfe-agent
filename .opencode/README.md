# opencode
Configurações do opencode: agente, skills, hooks e rules do projeto DFe-Agent.

## Estrutura

```
.opencode/
├── agent/             # Definicoes canonicas de agents (Sprint 12 consolida)
├── command/           # Slash commands (/feature, /bug, /duvida)
├── hooks/             # Hooks Python por agent (dev/, code-reviewer/) + guardrails (domain_guard.py, allowed_domains.py) + helpers (_lib/)
├── plugin/            # Plugin TS (.opencode/plugin/agent-hooks.ts)
├── rag/               # RAG meta-cognitivo (scripts TS + rag.db + knowledge/)
├── rules/             # Rules carregadas via opencode.json > instructions
├── skills/            # Skills canonicas (dfe-fiscal)
└── node_modules/      # Deps Node (gitignored)
```

## Agentes canonicos

| Slug | Path | Escopo |
|---|---|---|
| `dfe-agent` | `.opencode/agent/dfe-agent.md` | Consultas fiscais (NF-e, NT, etc.). User-invocable. |
| `dev` | `.opencode/agent/dev.md` | Owner de implementacao. Escopo amplo. |
| `code-reviewer` | `.opencode/agent/code-reviewer.md` | Read-only, invocado via task tool. |

> **Sprint 11**: o diretorio `.opencode/agents/` (plural) foi REMOVIDO
> em D.1 (consolidado em `.opencode/agent/` singular). Os 4 agents legacy
> (`backend-engineer`, `ml-engineer`, `prompt-engineer`, `qa-engineer`)
> tambem foram REMOVIDOS em C.1 — o plugin TS `agent-hooks.ts` reduziu
> o map `AGENTS` de 6 para 2. `@dev` absorveu todos os escopos.

## Slash commands

| Comando | Descricao |
|---|---|
| `/feature <descricao>` | Pipeline completo de feature (planning + TDD + review + RAG). |
| `/bug <sintoma>` | Investigacao read-only + correcao com gate de aprovacao humana. |
| `/duvida <pergunta>` | Q&A read-only lendo o projeto, cita `file_path:line_number`. |

Todos invocam `agent: dev` e seguem o padrao **RAG antes/depois**
(`search.ts` na Fase 0; `summarize.ts + embed.ts` na Fase final).