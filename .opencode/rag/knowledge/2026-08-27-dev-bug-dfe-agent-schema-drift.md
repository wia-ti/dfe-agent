# Bugfix dfe-agent-schema-drift — 2026-08-27

> Origem: /bug "Bug C: npx dfe-agent query retorna 'no such column: chunk_id'"
> (Sprint 16; apareceu durante validacao manual de v0.1.3 pelo usuario).
> Relatorio do code-reviewer: 0 BLOQUEANTE / 0 IMPORTANTE / 3 SUGESTAO (round 1).
> Iteracoes do loop corretivo: 1 (3 SUGESTOES aplicadas em round 2 -> 0/0/0).

## Sintoma

Apos instalar `@wiati/dfe-agent@0.1.3` (que tinha os fixes Bug A+B da Sprint 15):

```
PS> npx dfe-agent query "O que e a NF-e?"
[dfe-agent] erro fatal: no such column: chunk_id
```

Reproduzido em 2026-08-27 pelo usuario (`C:\Users\Andrews\Workspace\Projetos\# Pessoal\teste2`).

## Causa raiz

**Drift entre schema Py (produtor do `dfe.db.gz`) e codigo Node (consumidor).**

O Py (`src/db/vector_store.py:89-92`, `src/db/fts_store.py:102-103`) produz schema com
**chave composta `(document_id, chunk_index)`** desde Sprint 12 (quando adicionou sidecar
`chunk_metadata`):

```sql
CREATE VIRTUAL TABLE vec_chunks USING vec0(
  embedding float[384],
  document_id INTEGER,         -- Py
  chunk_index INTEGER,         -- Py
  text TEXT, source_url TEXT, doc_title TEXT
);

CREATE VIRTUAL TABLE fts_chunks USING fts5(
  text, section_path,
  document_id UNINDEXED,       -- Py
  chunk_index UNINDEXED,       -- Py
  ...
);
```

Mas o codigo Node publicado em v0.1.0-0.1.3 usava nomes de coluna antigos de um schema pre-Sprint-12
(antes do sidecar `chunk_metadata`), alem de assumir uma tabela `chunks` que **nao existe mais**:

| Arquivo Node | Linha (pre-fix) | Query errada |
|---|---|---|
| `src/query/vectorSearch.ts` | 49 | `SELECT chunk_id, doc_id, distance FROM vec_chunks ...` |
| `src/query/ftsSearch.ts` | 51 | `SELECT chunk_id, doc_id, bm25(fts_chunks) ... FROM fts_chunks ...` |
| `src/query/index.ts` | 111 | `FROM chunks c JOIN documents d ON c.doc_id = d.id WHERE c.id IN (?)` |

A tabela `chunks` (PK simples `id`) foi substituida por `vec_chunks` + `chunk_metadata` (PK
composta `(document_id, chunk_index)`) na Sprint 12. O PLAN_SPRINT14.md original documentava
`chunk_id` no design (linha 690), mas a implementacao Py divergiu e **ninguem re-sincronizou o Node**.

### Por que CI nao pegou (pior que Bug A/B)

- `tests/e2e/smoke-test.ps1` (Sprint 14) so' roda `install --auto-setup && status` — **nao
  chama `query`** end-to-end. Foi documentado como follow-up Sprint 14 #6.
- Testes comportamentais (`cache.test.ts`, `ftsSearch.test.ts`) skippados em CI por gate nativo
  Node 22/24 (pre-existente, gate `_SKIP_NATIVE` no Sprint 15).
- `tests/cli/skeleton.test.ts` 100% estrutural (regex em `readFileSync`) — confirma so' que o
  metodo **existe**, nao que a query esta correta.
- O test BEHAVIORAL pre-existente em `ftsSearch.test.ts:48-63` (pre-fix) usava schema ANTIGO
  (`chunk_id, doc_id, text`) casando com o codigo errado — **nao cobria o schema Py real**.
- O usuario eh o **primeiro** a rodar `update && query` end-to-end em Windows real com o pacote
  npm publicado. As sessoes de code review Sprint 14 (validadas em Linux + Node 20/22) e os tests
  comportamentais (skipados) nao exercitaram o caminho.

## Teste vermelho -> verde

TDD obrigatorio (`bug.md:3.1`); vermelho confirmado ANTES da implementacao.

### `tests/query/vectorSearch.test.ts` (NOVO, 92 linhas, 4 testes)

| # | Teste | Status pre-fix | Status pos-fix |
|---|---|---|---|
| 1 | `vectorSearch.ts existe e expoe vectorSearch()` | verd. (regex) | verd. |
| 2 | `vectorSearch usa schema Py real (aliases chunk_index AS chunk_id, document_id AS doc_id)` | verm. | verd. |
| 3 | `vectorSearch.ts NAO referencia colunas antigas chunk_id/doc_id sem alias` | verm. | verd. |
| 4 | `vectorSearch BEHAVIORAL: hits com schema Py real (document_id, chunk_index)` | verm. (`no such column`) | verd. (skipado Win+Node>=22) |

### `tests/query/ftsSearch.test.ts` (1 BEHAVIORAL migrado + 1 estrutural novo)

| # | Teste | Status pre-fix | Status pos-fix |
|---|---|---|---|
| 5 | `sanitizeQuery BEHAVIORAL: remove chars especiais` | verd. (schema antigo!) | verm. pre-fix / verd. pos-fix (skipado Win+Node>=22) |
| 6 | `ftsSearch.ts usa schema Py real (aliases)` + `assert.doesNotMatch SELECT chunk_id, doc_id` | verm. | verd. |

### `tests/query/index.test.ts` (NOVO, 73 linhas, 2 testes)

| # | Teste | Status pre-fix | Status pos-fix |
|---|---|---|---|
| 7 | `index.ts expoe hydrateChunks para teste` (gate anti-regressao de export interno) | verm. (privado) | verd. |
| 8 | `hydrateChunks BEHAVIORAL: usa vec_chunks (nao chunks) + JOIN documents — schema Py real` | verm. (`no such table: chunks`) | verd. (skipado Win+Node>=22) |

### Resultado final da suite

- `npm test` (packages/dfe-agent): **64 passed / 0 fail / 5 skipped (gate nativo) / 69 total**
  (era 60/2/62 antes; +9 testes: 3 BEHAVIORAL skipados + 6 estruturais novos).
- `tsc --noEmit`: sem erros.
- `pytest tests/ --cov=src --cov-branch --cov-fail-under=80` (DFe-Agent root): **761 passed /
  1 skipped (CONFAZ pre-existente) / cobertura 85.07%** (baseline mantido).
- Drift-check: OK (`source==dist`).

## Fix

### `src/query/vectorSearch.ts` (+2/-2)

```sql
-- antes (pre-fix):
SELECT chunk_id, doc_id, distance
  FROM vec_chunks
 WHERE embedding MATCH ?
 ORDER BY distance
 LIMIT ?

-- depois (aliases SQL casam schema Py):
SELECT chunk_index AS chunk_id, document_id AS doc_id, distance
  FROM vec_chunks
 WHERE embedding MATCH ?
 ORDER BY distance
 LIMIT ?
```

A interface Node `VectorHit { chunk_id, doc_id, distance }` fica preservada. Aliases SQL sao
no-op em custo e nao mudam tipo exportado.

### `src/query/ftsSearch.ts` (+2/-2)

Mesma mudanca:
```sql
-- antes:
SELECT chunk_id, doc_id, bm25(fts_chunks) AS score FROM fts_chunks ...

-- depois:
SELECT chunk_index AS chunk_id, document_id AS doc_id, bm25(fts_chunks) AS score FROM fts_chunks ...
```

### `src/query/index.ts` `hydrateChunks` (+58/-10)

Refator SQL completo:
```sql
-- antes (tabela chunks nao existe desde Sprint 12):
SELECT c.id AS chunk_id, c.doc_id, c.text, d.url, d.title, d.published_at
  FROM chunks c
  JOIN documents d ON c.doc_id = d.id
 WHERE c.id IN (?)

-- depois (tuplas WHERE IN casam chave composta):
SELECT vc.document_id, vc.chunk_index, vc.text, d.url, d.title, d.published_at
  FROM vec_chunks vc
  JOIN documents d ON d.id = vc.document_id
 WHERE (vc.document_id, vc.chunk_index) IN ((?,?),(?,?), ...)
```

Mudancas adicionais:
- Funcao agora `export function hydrateChunks(...)` (helper interno para teste).
- Parametro `handle: BetterSqlite3Database` (consistente com `ftsSearch.ts`/`vectorSearch.ts`).
- Tipo explicito `(h): HydratedChunk | null` no `.map(...)` resolve TS2322/TS2677.
- `byKey` indexa por `"${document_id}:${chunk_index}"` (chave composta).
- Removido bloco duplicado de comentario "Re-export canônico de `resolveBaseDir`".
- Removido `interface ChunkRow` orphan.

### `package.json:22`

`tests/query/vectorSearch.test.ts` e `tests/query/index.test.ts` adicionados a lista do `npm test`.

## Hipoteses alternativas descartadas

- **H1** — Schema do `dfe.db.gz` publicado esta corrompido (~0%). Refutada: `user_version=6` bate
  com `update.ts:157` validation; 23 tabelas; 134 MB de dados intactos.
- **H2** — v0.1.3 no registry eh a versao errada (~0%). Refutada: tarball 0.1.3 contem os fixes
  Sprint 15; o problema eh em `vectorSearch.ts`/`ftsSearch.ts`/`index.ts` que nao foram tocados.
- **H3** — Regressao de fix recente (~5%). Refutada: `git log` mostra que os 3 arquivos nao
  foram modificados desde o commit inicial da Sprint 14; o bug estava la desde v0.1.0.

## Code review (subagent `general`, code-reviewer nao inviavel)

### Round 1

- 0 BLOQUEANTE / 0 IMPORTANTE / 3 SUGESTAO.
- SUGESTOES aplicadas em round 2:
  1. **Aliases redundantes `AS document_id, AS chunk_index` removidos** (SUGESTAO 1).
  2. **Bloco duplicado de comentario removido** (SUGESTAO 2).
  3. **Tipo `Database.Database` padronizado para `BetterSqlite3Database`** (SUGESTAO 3).

### Round 2

- 0 BLOQUEANTE / 0 IMPORTANTE / 0 SUGESTAO.

## Padroes adotados

1. **Aliases SQL como ponte schema-vs-interface** — preserva tipos Node sem mudar schema Py.
   Mesma pattern de `src/db/migrations.py:75-98` (colunas Py) + `src/query/vectorSearch.ts`
   (alias Node).
2. **Tupla WHERE IN para chave composta** — gate anti-regrassao para queries com PK composta
   (gate paridade Py `src/db/vector_store.py:267-280`).
3. **Export de helpers internos para teste** (sem re-export publico) — gate anti-regrassao
   consistente com Sprint 11 B11.5 (`code-reviewer.md` consolidado em `.opencode/agent/`).
4. **Gate `_SKIP_NATIVE` padronizado** em todos os testes BEHAVIORAL novos (CI +
   `DFE_AGENT_SKIP_NATIVE_TESTS` + `IS_WIN_NODE_NATIVE_BUG` win32+Node>=22).
5. **Gates estruturais `assert.match` + `assert.doesNotMatch`** bloqueiam regressao ao
   schema pre-fix.

## Decisao arquitetural registrada

**Toda query Node contra schema Py** DEVE usar as colunas Py reais (`document_id`,
`chunk_index`) ou aliases explicitos que casem. Tabela `chunks` legacy foi **removida** em
Sprint 12; gates `assert.doesNotMatch` em `ftsSearch.test.ts`/`vectorSearch.test.ts`
impedem regressao.

## FOLLOW-UPS Sprint 16+

1. **Re-habilitar `tests/query/cache.test.ts`** em Windows + Node >= 22 via upgrade
   `better-sqlite3` (issue #336 WillBrennan). Decisao humana via PLAN.
2. **`tests/integration/test_query_e2e_readonly.test.ts`** — gate E2E completo `update && query`
   cross-platform com `dfe.db` em `tmp_path`. Setup pesado (criar DB com vec0 + fts5 +
   documents + chunk_metadata); adiado deste `/bug` por dependencia da upgrade do
   `better-sqlite3`.
3. **Estender `tests/e2e/smoke-test.ps1`** para incluir `query` alem de
   `install --auto-setup && status`. Garante gate end-to-end em Windows runner.
4. **Versao bash de `smoke-test.ps1`** para CI Linux (Sprint 14 FOLLOW-UP #6, parcialmente
   atendido por este bug via gate `_SKIP_NATIVE`).
5. **`python -m src.ragctl benchmark`** rodando contra a base Node (paridade query, nao so
   embeddings). Gate D.7 cobriu embeddings; falta paridade de queries.
6. **Aplicar SUGESTAO residual round 1** (se houver no round 2 final).

## Publicacao

- Versao: **v0.1.4 (PATCH bump)** — bugfix em runtime, interface publica inalterada (aliases SQL).
- Workflow `publish-npm.yml` ainda com `if: false` (Sprint 14 round 24); publicacao manual via
  `npm publish` ou re-habilitacao do CI.

## Arquivos modificados

| Path | Mudanca | LoC |
|---|---|---|
| `packages/dfe-agent/package.json` | +2 testes na lista do `npm test` | +1/-1 |
| `packages/dfe-agent/src/query/ftsSearch.ts` | Aliases SQL gate Bug C | +2/-2 |
| `packages/dfe-agent/src/query/vectorSearch.ts` | Aliases SQL gate Bug C | +2/-2 |
| `packages/dfe-agent/src/query/index.ts` | hydrateChunks refator + export + tipo explicito + remove dead code | +50/-15 |
| `packages/dfe-agent/tests/query/ftsSearch.test.ts` | BEHAVIORAL migrado schema Py + teste gate aliases | +30/-9 |
| `packages/dfe-agent/tests/query/vectorSearch.test.ts` (NOVO) | 4 testes gate Bug C | +92 |
| `packages/dfe-agent/tests/query/index.test.ts` (NOVO) | 2 testes gate Bug C hydrateChunks | +73 |

## Links uteis

- Sprint 14 plan: `PLAN_SPRINT14.md` (drift documentado mas nao pego)
- Sprint 15 knowledge: `.opencode/rag/knowledge/2026-08-27-dev-bug-dfe-agent-runtime-path-and-cache.md`
- Sprint 15 decisions: `AGENTS.md > Decisoes resolvidas (Sprint 15)`
- Sprint 16 plan: `PLAN_SPRINT16.md` (a criar)
- Pipeline `/bug`: `.opencode/command/bug.md`
- Code-reviewer template: `.opencode/agent/code-reviewer.md`
