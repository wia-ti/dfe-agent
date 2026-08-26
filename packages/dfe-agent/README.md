# @dfe-agent/dfe-agent

> **Status: MVP em desenvolvimento (Sprint 14)** — publicacao inicial prevista apos Fase F.

Agente opencode + base RAG com documentacao fiscal eletronica oficial brasileira (NF-e, NFC-e, CT-e, MDF-e, SPED). Para outros projetos opencode que querem responder perguntas sobre DFes sem clonar o DFe-Agent inteiro.

## What is this?

`@dfe-agent/dfe-agent` e' o agente `dfe-agent` empacotado como pacote npm. Ele expoe:

- **Agent definition** (`dist/agent.md`) — system prompt que orienta o LLM a:
  - usar a skill `dfe-fiscal`
  - consultar a base RAG local via `dfe-agent query`
  - citar fontes em todas as respostas
  - recusar responder quando nao ha' chunks relevantes (`Nao encontrei base para responder`)

- **Skill definition** (`dist/skill/dfe-fiscal/SKILL.md`) — workflow canonico de:
  - invocar `dfe-agent update` para manter base atualizada
  - usar modos `semantic` / `fts` / `hybrid`
  - aplicar guarda de `NO_EVIDENCE_MESSAGE`

- **CLI Node** (`dist/bin/dfe-agent.js`) — 4 subcommands:
  - `install` — copia agent + skill para `.opencode/` do projeto consumidor
  - `update` — baixa base RAG do GitHub Releases do DFe-Agent
  - `query "<pergunta>"` — busca semantica/FTS5/hibrida, retorna JSON
  - `status` — info da base instalada (path, mtime, doc count, schema)

- **Base RAG pre-buildada** — gerada no CI do DFe-Agent (Python pipeline) e distribuida via GitHub Releases como `dfe.db.gz` + `dfe.db.gz.sha256`. Tamanho: ~30MB gzipped.

## Install

```bash
npm install @dfe-agent/dfe-agent
npx dfe-agent install   # copia agent + skill para .opencode/ (opt-in, nao automatico)
npx dfe-agent update    # baixa base RAG (~30MB)
```

> **Por que `install` e' opt-in?** Decisao D8: evita sobrescrever `.opencode/agent/dfe-agent.md` custom do usuario sem aviso. Para auto-setup, use `npx dfe-agent install --auto-setup`.

## Quick start

### Via opencode TUI (integrado)

```bash
# apos install + update:
opencode run
# no TUI: Tab -> selecione @dfe-agent -> faca pergunta em linguagem natural
```

O agent invocara' a skill `dfe-fiscal`, que rodara' `dfe-agent query "<pergunta>"`, formatara' a resposta em linguagem natural e adicionara' o bloco `Fontes:` no final.

### Via CLI direto (sem TUI)

```bash
npx dfe-agent query "O que e a NF-e?"
# {
#   "answer": "A Nota Fiscal eletronica (NF-e) e' um documento...",
#   "sources": [
#     { "url": "https://www.nfe.fazenda.gov.br/...", "title": "NT 2019.001", "score": 0.87 }
#   ]
# }
```

Modos opt-in:

| Flag | Algoritmo | Quando usar |
|---|---|---|
| (nenhuma) | Vector search (sqlite-vec) | Default; perguntas genericas |
| `--mode=fts` | FTS5 BM25 | Termos literais (numero NT, codigo) |
| `--mode=hybrid` | RRF k=60 (vector + FTS5) | Maioria dos casos (gate Sprint 2) |

## Updating the base

```bash
npx dfe-agent update
```

Fluxo:

1. `GET https://api.github.com/repos/dfe-agent/DFe-Agent/releases/latest`
2. Localiza assets `dfe.db.gz` + `dfe.db.gz.sha256`
3. Download + verifica SHA-256 (gate B.3)
4. Extrai atomicamente para `~/.dfe-agent/dfe.db`
5. Valida `PRAGMA user_version >= 6` (gate schema)
6. Fallback: sem seed bundled (decisao Sprint 14 final); retorna exit 3 com mensagem clara se GitHub inacessivel. Follow-up Sprint 15+ pode adicionar seed mini.

## Custom base path

```bash
DFE_AGENT_BASE_DIR=/custom/path npx dfe-agent update
DFE_AGENT_BASE_DIR=/custom/path npx dfe-agent query "..."
```

Util para:

- CI em sandbox (sem $HOME gravavel)
- Per-project base (multiplas bases em maquinas compartilhadas)
- Testes isolados

## Troubleshooting

| Erro | Causa | Solucao |
|---|---|---|
| `no dfe.db.gz asset` | Release do DFe-Agent ainda nao publicado | Aguarde primeiro release `v*.*.*` |
| `SHA mismatch` | Base corrompida no download | Rode `npx dfe-agent update` novamente |
| `PRAGMA user_version < 6` | Base antiga de versao pre-Sprint 5 | `rm ~/.dfe-agent/dfe.db && npx dfe-agent update` |
| `@xenova/transformers` falha ao carregar | Node v22.21.1 com sharp natives quebrados (Sprint 13) | Use Node 22.9 LTS ou 20.x |
| `better-sqlite3` falha ao compilar | Toolchain MSVC ausente | `npm rebuild better-sqlite3` com Visual Studio Build Tools |
| Query retorna `Nao encontrei base para responder` para pergunta valida | Base sem docs sobre o tema ou score baixo | `npx dfe-agent status` -> verifique `baseDocCount`; se baixo, `npx dfe-agent update` |

## Development

A fonte canonica deste agent vive no **DFe-Agent repo**:

- `.opencode/agent/dfe-agent.md`
- `.opencode/skills/dfe-fiscal/SKILL.md`

Para distribuir atualizacoes:

1. Edite a fonte canonica no DFe-Agent root.
2. Rode `npm run sync` em `packages/dfe-agent/` para copiar para `dist/`.
3. CI roda `npm run drift-check` para garantir consistencia (gate B.1).

Drift detectado em CI = PR bloqueado.

## Como o pacote funciona (arquitetura)

```
DFe-Agent root (CI em cada release v*.*.*)
  │
  ├── python -m src.collector --once       # varre portais oficiais
  ├── python -m src.indexer.ingest          # gera embeddings
  ├── gzip storage/dfe.db > dfe.db.gz       # ~30MB
  └── upload asset em GitHub Release
            │
            ▼
  npx dfe-agent update (consumer)
    ├── download dfe.db.gz + sha256
    ├── verify SHA-256
    ├── extract to ~/.dfe-agent/dfe.db (atomic)
    └── PRAGMA user_version >= 6 (gate schema)
            │
            ▼
  npx dfe-agent query "<pergunta>" (consumer)
    ├── encode(query) via @xenova/transformers (ONNX)
    ├── sqlite-vec MATCH em vec_chunks
    ├── opcional: FTS5 BM25 MATCH em fts_chunks
    ├── opcional: RRF k=60 fusion
    └── retorna {answer, sources[]}
```

## Layout

```
packages/dfe-agent/
├── package.json
├── tsconfig.json
├── .gitignore
├── README.md
├── CHANGELOG.md
├── src/                      # TypeScript source
│   ├── index.ts              # entry point (VERSION, reexports)
│   ├── cli.ts                # CLI parser (parseArgs + 4 subcommands)
│   ├── commands/
│   │   ├── install.ts        # copia agent + skill para .opencode/
│   │   ├── update.ts         # download + SHA verify + atomic extract
│   │   ├── query.ts          # delega para queryEngine.search()
│   │   └── status.ts         # info da base
│   ├── query/                # query engine Node (port Py)
│   │   ├── index.ts          # orchestrator + NO_EVIDENCE_MESSAGE
│   │   ├── embedder.ts       # @xenova/transformers + LRU 128
│   │   ├── vectorSearch.ts   # sqlite-vec MATCH
│   │   ├── ftsSearch.ts      # FTS5 BM25
│   │   ├── hybrid.ts         # RRF k=60
│   │   ├── cache.ts          # SQLite query cache
│   │   └── contextBuilder.ts # {answer, sources}
│   └── bin/
│       └── dfe-agent.ts      # bin shim (shebang)
├── scripts/                  # sync + drift-check
│   ├── sync-assets.ts
│   └── drift-check.ts
├── dist/                     # build output (gitignored)
├── tests/                    # node --test suites
│   ├── scaffold.test.ts
│   ├── sync-assets.test.ts
│   ├── drift-check.test.ts
│   ├── cli/skeleton.test.ts
│   ├── query/{embedder,ftsSearch,hybrid,cache,orchestrator}.test.ts
│   └── e2e/
# NOTA: src/seed/ removido em Sprint 14 final (61MB gzip > target 30MB);
# `update` retorna exit 3 com mensagem clara em rede off sem seed.
```

## License

MIT