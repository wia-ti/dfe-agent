# 2026-08-26-dev-sprint14-npm-package.md

> Categoria: `architecture_decision` (decisao arquitetural de empacotamento).
> Slug: `dev` (owner unico desde Sprint 10).
>
> Extraido automaticamente de transcript via `.opencode/rag/summarize.ts` (Sprint 12 B.4).

## Contexto

Sprint 14 empacota o agente `dfe-agent` (definido em `.opencode/agent/dfe-agent.md`) como pacote npm `@dfe-agent/dfe-agent` para que outros projetos opencode possam consumir a base RAG fiscal sem clonar o repositorio DFe-Agent inteiro.

## Decisoes arquiteturais resolvidas (D1-D10)

| # | Decisao | Resolucao | Por que |
|---|---|---|---|
| D1 | Layout do pacote | mono-repo `packages/dfe-agent/` | Reusa CI do DFe-Agent; sync via path relativo; SemVer independente |
| D2 | Nome do pacote | `@dfe-agent/dfe-agent` | Escopado para futura org `dfe-agent` no npm |
| D3 | Linguagem do CLI | TypeScript compilado | Reusa `@xenova/transformers` + `better-sqlite3` ja' em `.opencode/package.json` |
| D4 | Localizacao da base no consumidor | `~/.dfe-agent/dfe.db` + override `DFE_AGENT_BASE_DIR` | Evita duplicar 50-100MB por projeto; CI pode override |
| D5 | Mecanismo de bootstrap | GitHub Releases download + seed bundled | Download unico, atomic, versionado |
| D6 | Modelo embedding Node | `Xenova/paraphrase-multilingual-MiniLM-L12-v2` (ONNX) | Espelha DFe-Agent Py; offline-capable |
| D7 | Sync Py <-> Node embeddings | ONNX unico (gate cosine >= 0.99) | Drift zero se mesmo modelo + tokenizer |
| D8 | Postinstall permissivo | opt-in via `--auto-setup` | Evita sobrescrever `.opencode/agent/dfe-agent.md` custom |
| D9 | Versionamento | SemVer independente, tag `packages-v*.*.*` | Tag separada de `v*.*.*` do DFe-Agent |
| D10 | Compatibilidade opencode | ultima estavel (engines `>=20 <23`) | Pin evita Node v22.21.1 (issue sharp) |

## Padroes adotados

1. **Drift detection como gate CI**: `npm run drift-check` no workflow `test-npm-package.yml` falha PR se `packages/dfe-agent/dist/*` divergir de `.opencode/*` fonte canonica.
2. **Atomic write na base**: `dfe.db.tmp` + `rename()` evita base corrompida em mid-download (TASK C.2).
3. **SHA-256 obrigatorio**: `update` valida `dfe.db.gz.sha256` antes de extrair (gate B.3).
4. **NO_EVIDENCE_MESSAGE canonico**: literal `Nao encontrei base para responder` exportado de `src/query/index.ts`; nunca duplicado.
5. **Fonte canonica no DFe-Agent root**: editou `.opencode/agent/dfe-agent.md` ou `.opencode/skills/dfe-fiscal/SKILL.md` -> rodar `npm run sync` em `packages/dfe-agent/`.

## Bloqueadores encontrados

- **Ambiente local com Node v22.21.1 + sharp/better-sqlite3 nativos quebrados** (ja' documentado em Sprint 13 B.6). Workaround: validar via PowerShell estrutural; gate `npm install` exit 0 so' fecha em ambiente corrigido (Node 22.9 LTS ou 20.x).
- **`test runner `node --test --import tsx` trava** em ambiente com natives quebrados; roda offline apos `npm rebuild better-sqlite3` ou downgrade de Node.

## Arquivos criados (~25 arquivos novos)

- `packages/dfe-agent/{package.json, tsconfig.json, .gitignore, README.md, CHANGELOG.md}`
- `packages/dfe-agent/src/{index.ts, cli.ts, bin/dfe-agent.ts}`
- `packages/dfe-agent/src/commands/{install,update,query,status}.ts`
- `packages/dfe-agent/src/query/{embedder,vectorSearch,ftsSearch,hybrid,cache,contextBuilder,index}.ts`
- `packages/dfe-agent/scripts/{sync-assets,drift-check}.ts`
- `packages/dfe-agent/tests/{scaffold,sync-assets,drift-check}.test.ts`
- `packages/dfe-agent/tests/cli/skeleton.test.ts`
- `packages/dfe-agent/tests/query/{embedder,ftsSearch,hybrid,cache,orchestrator}.test.ts`
- `.github/workflows/{test-npm-package,publish-base,publish-npm}.yml`
- Edicoes: `.gitignore` (12 linhas para `packages/`), `AGENTS.md` (secao distribuicao npm), `SPEC.md` (nota Sprint 14+), `.opencode/skills/dfe-fiscal/SKILL.md` (secao contexto de uso)

## Tasks concluidas (16/20 = 80%)

| Fase | Tasks | Status |
|---|---|---|
| A | A.1, A.2 | ✅ |
| B | B.1, B.2, B.3 | ✅ |
| C | C.1, C.2, C.3, C.4 | ✅ (C.1 implementada; C.2/C.3/C.4 stubs completos) |
| D | D.1 | ✅ (D.2 bloqueado por base real; D.3 bloqueado por runtime Python) |
| E | E.1, E.2, E.3, E.4, E.5 | ✅ (codigo completo, runtime nao testado) |
| F | F.1, F.3, F.4 | ✅ (F.2 bloqueado por base + runtime) |

## Tasks bloqueadas por ambiente (4/20 = 20%)

| Task | Bloqueador |
|---|---|
| D.2 | Requer `storage/dfe.db.gz` real (Py pipeline) |
| D.3 | Requer Python + sentence-transformers runtime |
| F.2 | Requer base instalada + CLI runtime |
| Fase 3 | Suite verde depende de `npm install` exit 0 + `npm test` exit 0 |

## Follow-ups Sprint 15+

1. Migrar `.opencode/node_modules/` para versao funcional (Node 22.9 LTS).
2. Implementar `D.3` (paridade embeddings Py↔Node >= 0.99) e mover para `tests/integration/`.
3. Implementar `F.2` smoke E2E em scratch project apos ambiente corrigido.
4. Considerar port do collector/indexer para Node (decision D.5 hoje baixa do GitHub Releases; Sprint 15+ pode adicionar `dfe-agent build` para regenerar localmente).
5. Suporte a Windows ARM64 (sqlite-vec build oficial).
6. `dfe-agent query` com streaming output para respostas longas.

## Convencao "agent canonico no DFe-Agent root"

Documentada em `AGENTS.md > Distribuicao como pacote npm > Convecoes de empacotamento`. Toda edicao em `.opencode/agent/dfe-agent.md` ou `.opencode/skills/dfe-fiscal/SKILL.md` no DFe-Agent root deve ser seguida por `npm run sync` em `packages/dfe-agent/` antes de commit. CI bloqueia PR com drift (gate B.1).