# DFe-Agent

> Agente local que coleta documentacao fiscal eletronica oficial (NF-e, NFC-e, CT-e, MDF-e, SPED) e legislacao fiscal eletronica oficial, indexa em base RAG local e responde perguntas em linguagem natural fundamentadas em notas tecnicas.

Este arquivo e' o contexto do projeto para o **Claude Code**. O historico completo de decisoes (Sprints 2 a 18) continua em `AGENTS.md` > "Decisoes resolvidas (Sprint N)": leia a secao da sprint relevante quando precisar do porque de uma escolha. As regras detalhadas ficam em `.claude/rules/` (carregadas automaticamente; `src.md` e `tests.md` so' valem para seus paths).

## Harness Claude Code

| Peca | Onde | Papel |
|---|---|---|
| Agente padrao (`@dev`) | sessao principal | Owner de todas as alteracoes; ver "Agente padrao" abaixo |
| `code-reviewer` | `.claude/agents/code-reviewer.md` | Revisao read-only (BLOQUEANTE/IMPORTANTE/SUGESTAO) |
| `deployer` | `.claude/agents/deployer.md` | Unico que faz `git push`/`git tag`/`npm publish`/`gh release` |
| `dfe-agent` | `.claude/agents/dfe-agent.md` | Responde duvidas fiscais pela base RAG, sempre com `Fontes:` |
| `/feature`, `/bug`, `/duvida` | `.claude/commands/` | Pipelines do `@dev` (TDD + review + RAG meta) |
| `/deploy` | `.claude/skills/deploy/` | Roda no subagent `deployer` (`context: fork`) |
| Skill `dfe-fiscal` | `.claude/skills/dfe-fiscal/` | Fluxo de coleta, ingestao e consulta RAG |
| Hooks | `.claude/settings.json` -> `.claude/hooks/dispatch.py` -> `.claude/hooks/<agent>/*.py` | Guardrails por agent (porta do plugin OpenCode) |
| RAG meta-cognitivo | `.claude/rag/` (`rag.db` + `knowledge/`) | Aprendizados de sessoes anteriores |

O dispatcher escolhe o perfil de hooks pelo `agent_type` do payload: sem `agent_type` (sessao principal) aplica `dev`; `code-reviewer` e `deployer` tem perfis proprios; `dfe-agent` nao tem hooks.

## Agente padrao (`@dev`)

A sessao principal faz o papel do antigo agent `@dev`:

- Owner de `src/`, `tests/`, `.claude/`, `AGENTS.md`, `CLAUDE.md`, `PLAN*.md`, `SPEC.md`, `requirements.txt`, `pyproject.toml`, `scripts/`. `storage/` e' so' leitura; escrita na base passa por `apply_pending`, `RagIndexer.ingest_pending` e `python -m src.ragctl reindex`.
- Nao emite documentos fiscais nem responde duvida de dominio fiscal: delegue ao subagent `dfe-agent`.
- Revisao read-only: delegue ao subagent `code-reviewer` (Agent tool).
- Publicacao: use `/deploy` (subagent `deployer`). O `@dev` **nao commita, nao faz push, nao abre PR**; o humano fecha o commit.
- Workflow: briefing (`AGENTS.md`, `SPEC.md`, `PLAN.md`, `.claude/rules/`) -> RAG antes (`npx tsx .claude/rag/search.ts -q "<tema>" -a dev --top-k 5`) -> plano com TodoWrite -> TDD (vermelho primeiro) -> `pytest tests/ --cov=src --cov-fail-under=80` -> code review -> loop corretivo ate' 0 BLOQUEANTE / 0 IMPORTANTE (max 3 iteracoes) -> RAG depois (`.claude/rag/knowledge/<data>-dev-<contexto>.md` + `npx tsx .claude/rag/embed.ts --file <md>`) -> atualizar `AGENTS.md` com as decisoes da sprint.
- Hooks do perfil `dev`: PreToolUse bloqueia `git push`, `gh pr create`, `gh release`, `pip install`/`poetry add`, `curl`/`wget`, `rm -rf`, `sed -i`, redirecionamento `>`/`<`/`tee`, SQL direto em `*.db`, `npx tsx .claude/rag/(embed|search|summarize).ts` e o pipeline RAG (`src.collector --once`, `src.indexer.ingest`, `src.ragctl migrate|reindex|benchmark`). Escapes: `python -m src.ragctl stats` e `python -m src.collector --diagnose-net`. PostToolUse roda a suite pytest do arquivo editado. Stop roda `pytest tests/` quando o turno editou arquivos e bloqueia o encerramento se falhar (uma vez por ciclo).

## Stack

| Camada | Tecnologia |
|---|---|
| Base RAG (documentos fiscais) | SQLite + `sqlite-vec` (vec0), versao operacional **6** |
| Linguagem | Python 3.11+ (`src/`), TypeScript (`packages/dfe-agent/`, `.claude/rag/`) |
| Parsing | `pypdf`, `BeautifulSoup` + `lxml` |
| Embeddings | `sentence-transformers` `paraphrase-multilingual-MiniLM-L12-v2` (trocavel via `DFE_EMBEDDING_MODEL`; `DFE_EMBEDDING_DTYPE=float16` reduz RAM) |
| Busca textual | FTS5 (BM25) |
| RAG meta-cognitivo | SQLite + `sqlite-vec` dim 384, `all-MiniLM-L6-v2` via `@xenova/transformers`, rodado com `tsx` |
| Pacote npm | `@wiati/dfe-agent` em `packages/dfe-agent/` (tag `packages-v*.*.*`) |
| Execucao | 100% local |

## Como rodar

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python -m src.ragctl migrate          # cria DB e aplica migrations
python -m src.collector --once        # varredura dos portais
python -m src.indexer.ingest          # ingestao dos pendentes
python -m src.query "<pergunta>"      # --hybrid | --hierarchical | --rerank | --no-cache
python -m src.ragctl stats            # contadores da base
pytest tests/                         # suite completa
pytest tests/unit/ --cov=src --cov-fail-under=80
cd packages/dfe-agent && npm test && npm run drift-check
npx tsx .claude/rag/search.ts -q "<pergunta>" -a dev   # RAG meta
```

Modos de busca: semantica (default, cosseno + dedup + boost temporal), `--hybrid` (RRF k=60 com BM25, para numeros de NT e codigos), `--hierarchical` (summaries -> chunks, bases >1000 docs), `--rerank` (cross-encoder opt-in). Cache de embedding de query em `storage/query_cache.db`.

## Padroes de codigo

- `snake_case` em arquivos, funcoes e variaveis Python; `PascalCase` em classes; `UPPER_SNAKE_CASE` em constantes; `kebab-case` em agents, rules e skills.
- Sem API HTTP: interacao via CLI (`python -m src.<modulo>`) e chamadas entre modulos.
- Cada modulo de `src/` e' independente; `__init__.py` expoe so' a interface publica; I/O separado de dominio.
- Type hints obrigatorios, sem `Any` implicito; modelos de dominio em `dataclass` ou `pydantic`.
- Dependencias com pin exato em `requirements.txt` e `pyproject.toml`.

## TDD

- `pytest` + `pytest-mock` + `pytest-cov`; testes espelhados em `tests/unit/` e `tests/integration/`.
- Cobertura minima 80% em `src/`, **100% em `src/parser/`**, **>=95% em `src/indexer/`**.
- Cada `_apply_vN(conn)` das migrations e' idempotente (`PRAGMA user_version`, `apply_pending`).
- Testes criticos (todos cobertos): coletor marca documento novo como `nao ingerido`; parser preserva acentuacao; indexador idempotente por hash; recusa sem chunk relevante; guard bloqueia dominio fora da lista; throttling entre requisicoes; toda resposta cita fonte; upgrade de migration v1->v6 sem perda; RRF e hierarquica consistentes; cache de query HIT na 2a chamada; guard HTTP nao recursivo.

## Nunca fazer

- Inventar informacao: toda afirmacao do agente tem fonte na base RAG; sem base, responder `NO_EVIDENCE_MESSAGE` ("Nao encontrei base para responder", definido em `src/query/context_builder.py`).
- Acessar dominios fora de `ALLOWED_DOMAINS` (guard `src/utils/http_guard.py` + `.opencode/hooks/domain_guard.py`).
- Metralhar portais: respeitar `Throttler`; sem proxy rotativo, CAPTCHA solving ou contorno de anti-bot.
- Emitir documento fiscal, substituir contador ou dar opiniao legal/contabil.
- Reprocessar documento `ingerido` (idempotencia por `content_hash`).
- Dropar `vec_chunks` sem backfill (use `python -m src.ragctl reindex`).
- Recriar CI em `.github/workflows/` (removido na Sprint 18; publicacao via `/deploy`).

## Distribuicao npm

`packages/dfe-agent/` distribui o agente para consumidores **OpenCode** (`npx dfe-agent install` copia agent + skill para `.opencode/` do consumidor). As fontes do sync ainda sao `.opencode/agent/dfe-agent.md` e `.opencode/skills/dfe-fiscal/` (`packages/dfe-agent/scripts/sync-assets.ts`); mudar isso altera o produto publicado.
