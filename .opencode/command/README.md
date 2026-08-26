# command
Slash commands do opencode registrados em `.opencode/command/<name>.md`
(ou `.opencode/commands/<name>.md`). Acionaveis via `/<name> <argumentos>`
na CLI ou TUI.

| Comando | Descricao |
|---|---|
| `/feature` | Pipeline completo de feature: planning (sprint), implementacao TDD, testes, code review e persistencia no RAG meta-cognitivo. Re-executa o ciclo se o code-reviewer reportar BLOQUEANTE ou IMPORTANTE. |
| `/bug` | Pipeline completo de correcao de bug: investigar a causa raiz em modo read-only, relatar pedindo aprovacao humana ANTES de corrigir, corrigir com TDD, code review, persistencia no RAG. |
| `/duvida` | Responde duvidas sobre o DFe-Agent SEMPRE lendo o projeto antes. Read-only por contrato. Captura Q&A canonico no RAG meta-cognitivo para consultas futuras. |

Todos os 3 commands invocam o agente `dev` (definido em
`.opencode/agent/dev.md`) e seguem o padrao **RAG antes/depois**:

- **RAG antes** (Fase 0 de cada command): `npx tsx .opencode/rag/search.ts -q "$ARGUMENTS" -a dev --top-k 5` injeta aprendizados anteriores relevantes no contexto.
- **RAG depois** (Fase final): grava `.opencode/rag/knowledge/<date>-dev-<contexto>.md` e roda `npx tsx .opencode/rag/embed.ts --file <md>` sincrono. Hook `.opencode/hooks/dev/stop.py` continua como safety net em background (fire-and-forget).

> **Sprint 11**: os hooks `.opencode/hooks/learning_*.py` foram REMOVIDOS em B11.2 (BLOQUEANTE — eram "letra morta" desde Sprint 5 C.1). O safety net agora e' apenas `.opencode/hooks/dev/stop.py` via `.opencode/hooks/_lib/learning.py::spawn_summarize_then_embed`.

## Convecoes

- kebab-case para o nome do arquivo (ex.: `feature.md` invocado como `/feature`).
- Frontmatter YAML obrigatorio: `description` (1 frase efetiva) e `agent` (built-in
  ou definido em `.opencode/agent/`).
- Body e' o prompt completo; variaveis: `$ARGUMENTS` (tudo digitado depois
  do comando) e `$1`, `$2`, ... (argumentos posicionais).
- `model: PROVIDER/MiniMax-M3` no frontmatter (placeholder ate definicao
  formal do provider MiniMax-M3).

> **Sprint 11**: o diretorio `.opencode/agents/` (plural) foi REMOVIDO em D.1. Path canonico de agent e' singular (`.opencode/agent/`).

## Validacao apos criar/editar

```bash
opencode command list
python -c "import yaml, re, pathlib; p = pathlib.Path('.opencode/command/<file>.md'); raw = p.read_text(encoding='utf-8'); fm = yaml.safe_load(re.match(r'^---\s*\n(.*?\n)---\s*\n', raw, re.DOTALL).group(1)); print(sorted(fm.keys()))"
```

Reiniciar o opencode apos alteracao de command file (config nao e'
hot-reloaded).

## Agentes referenciados

| Slug | Path canonico | Escopo |
|---|---|---|
| `dev` | `.opencode/agent/dev.md` | Implementador owner de todas as alteracoes. Escopo amplo: `src/`, `tests/`, `.opencode/`, `AGENTS.md`, `PLAN*.md`, `SPEC.md`. |
| `code-reviewer` | `.opencode/agent/code-reviewer.md` | Revisor read-only invocado via task tool (`subagent_type: code-reviewer`). Pode ser sub-delegado por `/feature` e `/bug` na Fase 4. |
| `dfe-agent` | `.opencode/agent/dfe-agent.md` | Agente principal user-invocable para consultas fiscais (NF-e, NT, etc.). NAO e' invocado por slash commands de implementacao. |

Agentes legados (`backend-engineer`, `ml-engineer`, `prompt-engineer`,
`qa-engineer`) foram REMOVIDOS em Sprint 11 I11.2. Todos os slash commands apontam para
`dev` (canonico desde Sprint 10).

## Fluxo RAG antes/depois

Cada slash command segue o mesmo padrao (ver body de cada command para
detalhes):

```
Fase 0: search.ts -q "$ARGUMENTS" -a dev   <-- RAG antes
... (fases de trabalho) ...
Fase N: summarize.ts + embed.ts            <-- RAG depois (sincrono)
```

O `search.ts` injeta contexto relevante no prompt do agent antes de
qualquer trabalho. O `embed.ts` sincrono garante que o aprendizado da
sessao ja' aparece no `search.ts` antes do termino do command.