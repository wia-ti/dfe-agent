# Bugfix dfe-agent-runtime-path-and-cache — 2026-08-27

> Origem: /bug "corrija os dois bugs seguindo o pipeline /bug"
> (Bug A: paths divergentes; Bug B: cache em handle readonly).
> Relatorio do code-reviewer: 1 BLOQUEANTE / 0 IMPORTANTE / 6 SUGESTAO
> (round 1) -> 0 BLOQUEANTE / 0 IMPORTANTE / 1 SUGESTAO (round 2 pos-fix).
> Iteracoes do loop corretivo: 1.

## Sintoma

`npx dfe-agent query "O que e a NF-e?"` no Windows retorna:

```
[dfe-agent] erro fatal: Cannot open database because the directory does not exist
```

Apos mover `dfe.db` para o local esperado, retorna:

```
[dfe-agent] erro fatal: attempt to write a readonly database
```

Reproduzido em 2026-08-27 pelo usuario (`PS C:\Users\Andrews\Workspace\Projetos\# Pessoal\teste`).

## Causa raiz

Dois defeitos correlatos no pacote `@wiati/dfe-agent` v0.1.2 (publicado em 2026-08-27):

### Bug A — paths divergentes

A decisao D4 de Sprint 14 ("`~/.dfe-agent/dfe.db` + override `DFE_AGENT_BASE_DIR`") foi implementada **duplicada em 3 funcoes locais**:

| Local | Comportamento |
|---|---|
| `src/query/index.ts:64-68` (pre-fix) | `resolve(process.env.HOME ?? homedir() ?? tmpdir(), ".dfe-agent")` — **correto** |
| `src/commands/update.ts:47-52` (pre-fix) | esquecia o `resolve(..., ".dfe-agent")` → gravava em `$HOME/dfe.db` |
| `src/commands/status.ts:20-24` (pre-fix) | mesmo — verificava em `$HOME/dfe.db`, nao `~/.dfe-agent/dfe.db` |

Sintoma: `update` salvava em `C:\Users\Andrews\dfe.db`, `query` procurava em `C:\Users\Andrews\.dfe-agent\dfe.db`. **End-to-end nunca bate**.

### Bug B — cache acoplado a handle readonly

`src/query/index.ts:153` abre `dfe.db` com `readonly: true`. `src/query/cache.ts:44-50` aceitava `handle: BetterSqlite3Database` no construtor e fazia `handle.exec(QUERY_CACHE_SCHEMA)` — CREATE TABLE em DB readonly → **SQLITE_READONLY (8)** → `attempt to write a readonly database`. Docstring de `cache.ts:6` **prometia** `<baseDir>/cache.db` separado, codigo **misturava** tudo no mesmo DB.

### Por que CI nao pegou

- Sprint 14 fechou com 5 testes comportamentais `skipped` em CI por bug Node 22 `RemoveEnvironmentCleanupHook` (knowledge 2026-08-26-dev-sprint14-npm-package.md:104).
- Mesmo sintoma reproduz em Windows + Node 24 (gate estendido no fix).
- `tests/cli/skeleton.test.ts` 100% estrutural (regex em `readFileSync`).
- `tests/e2e/smoke-test.ps1` so' roda `install --auto-setup && status` — nao chama `query`.
- Nenhum teste E2E `update && query` cross-platform.
- Decisao D4 documentada mas nao extraida para modulo unico → drift entre 3 implementacoes independentes (pattern ja' visto em Sprint 14 "Drift com Py" — `MIN_RELEVANCE_SCORE 0.3 vs 0.5`).

## Teste vermelho -> verde

TDD obrigatorio (`bug.md:3.1`); vermelho confirmado ANTES da implementacao.

### Bug A — `tests/query/paths.test.ts` (NOVO, 7 testes)

| # | Teste | Status pre-fix | Status pos-fix |
|---|---|---|---|
| 1 | entrypoint `update`: usa paths.ts OU canonical `.dfe-agent` | verm. | verd. |
| 2 | entrypoint `status`: usa paths.ts OU canonical `.dfe-agent` | verm. | verd. |
| 3 | entrypoint `query/index`: usa paths.ts OU canonical `.dfe-agent` | verd. (canonical legado) | verd. (import paths.ts) |
| 4 | `src/paths.ts` expoe `resolveBaseDir + resolveDbPath + resolveCacheDbPath` | verm. (arquivo nao existe) | verd. |
| 5 | `src/paths.ts` respeita override e env `DFE_AGENT_BASE_DIR` | verm. | verd. |

### Bug B — `tests/query/cache.test.ts` + `tests/query/paths.test.ts`

| # | Teste | Status pre-fix | Status pos-fix |
|---|---|---|---|
| 6 | `QueryCache` nao escreve em handle externo (migracao API pre-fix) | verm. (cache(handle) rodava handle.exec) | verd. (cache(baseDir) usa proprio DB) |
| 7 | `cache.ts` importa `resolveCacheDbPath` de `paths.ts` (gate estrutural) | verm. | verd. |
| 8 | `query/index.ts` passa `resolveBaseDir(...)` ao `QueryCache` | verm. (passava `handle`) | verd. |
| 9 | `cache.ts` NAO tem `constructor(handle: BetterSqlite3Database)` | verm. (legacy acoplamento) | verd. |
| 10 | `query/index.ts` NAO tem `new QueryCache(handle)` | verm. | verd. |

## Fix

### Novo: `packages/dfe-agent/src/paths.ts` (78 linhas)

Centraliza os 3 resolves:

- `resolveBaseDir(baseDirOverride?)` → `<override>` OU `$DFE_AGENT_BASE_DIR` OU `$HOME`/`$USERPROFILE`/`os.homedir()` + `.dfe-agent`.
- `resolveDbPath(baseDirOverride?)` → `<baseDir>/dfe.db`.
- `resolveCacheDbPath(baseDirOverride?)` → `<baseDir>/cache.db` (Bug B — separado por design).

### `src/commands/update.ts`

- Removido helper local `resolveBaseDir()` (47-52) — esquecia `.dfe-agent`.
- Import de `../paths.js` (`resolveBaseDir`, `resolveDbPath`).
- `dbPath = resolveDbPath(opts.baseDirOverride)` — fonte canonica.
- `baseDir = opts.baseDirOverride ?? resolveBaseDir()` permanece para `mkdirSync`.

### `src/commands/status.ts`

- Removido helper local (20-24).
- Import de `../paths.js` apenas `resolveDbPath` (SUGESTAO do code-review aplicada — `baseDir` era dead var).
- `dbPath = resolveDbPath()`.

### `src/query/index.ts`

- Removido helper local `resolveBaseDir` (61-68).
- Import + re-export de `../paths.js` para manter API publica (`export { resolveBaseDir } from "../paths.js"`).
- `dbPath = resolveDbPath(opts.baseDirOverride)`.
- `cache = new QueryCache(resolveBaseDir(opts.baseDirOverride))` — **NUNCA MAIS `new QueryCache(handle)`**.

### `src/query/cache.ts` (refator central Bug B)

- Construtor agora recebe `baseDir: string` (nao `handle: BetterSqlite3Database`).
- `this.dbPath = resolveCacheDbPath(baseDir)`.
- `mkdirSync(dirname(this.dbPath), { recursive: true })` (DB precisa de dir existente).
- `this.handle = new Database(this.dbPath)` — **propria conexao RW**, isolada do `dfe.db` (readonly).
- `handle.exec(QUERY_CACHE_SCHEMA)` — agora permitido (RW).
- Adicionado `close()` method idempotente (`if (this.handle.open)`) — evita crash do destructor better-sqlite3 no cleanup hook (gate FOLLOW-UP Sprint 14 #6).

### `tests/query/cache.test.ts`

- Guard CI estendido: auto-detecta `process.platform === "win32" && NODE_MAJOR >= 22` alem de `CI=true`/`DFE_AGENT_SKIP_NATIVE_TESTS=1`. Documenta que o bug `RemoveEnvironmentCleanupHook` reproduz em Windows + Node 24 (nao so' Linux + Node 22 como Sprint 14 documentou).
- Teste pre-existente "hit na 2a chamada identica" **migrado para nova API** (BLOQUEANTE do round 1 do code-review): usa `mkdtempSync` + `new QueryCache(tmp, ...)` + `cache.close()` no `finally`. Sem `Database(":memory:")` nem `handle as any`.
- Adicionado teste comportamental "abre conexao propria em <baseDir>/cache.db" (gate Bug B). Skip em CI/Windows (gate nativo).

### `tests/query/paths.test.ts` (NOVO, 7 testes)

Cobrem Bug A e Bug B estruturalmente — gate cross-platform mesmo quando comportamentais estao skipados.

### `package.json`

`tests/query/paths.test.ts` adicionado a lista do `npm test` (linha 22).

## Hipoteses alternativas descartadas

- **H1** — Sintoma 2 (readonly) eh ACL/permission do Windows (~5%). Refutada: `Get-Acl` mostra `FullControl`; alem disso `--mode fts` (que nao toca cache) passaria sem mudanca de ACL. Nao eh permission.
- **H2** — Suprimir `CREATE TABLE IF NOT EXISTS` ja' que cache existe (~10%). Refutada: problema eh arquitetural, nao de inicializacao; suprimir DDL nao resolve a dependencia readonly/RW.
- **H3** — Remover `readonly: true` em `query/index.ts` (~5%). Refutada: o `readonly` eh defesa contra corrupcao; remover amplifica superficie de bug (`vectorSearch.ts:34` documenta o invariante). `QueryCache` precisa de propria conexao RW.
- **H4** — Regressao de fix anterior (~0%). `git blame` coloca origem no commit inicial da Sprint 14. Nao eh regressao, eh defeito de origem.

## Code review

### Round 1

- Subagent invocacao: `general` (code-reviewer nao inviavel — Sprint 9 follow-up).
- Reportou: 1 BLOQUEANTE / 0 IMPORTANTE / 6 SUGESTAO.
- BLOQUEANTE: `tests/query/cache.test.ts:64,80` — teste pre-existente nao migrado para `QueryCache(baseDir, opts)`. Em Linux Node <22 (sem CI=true), `path.resolve(handle, "cache.db")` coage objeto para `"[object Object]"`, mkdirSync cria `[object Object]/`, SQLITE_CANTOPEN.
- SUGESTOES aplicadas (5): dead `baseDir` em status.ts, `?? tmpdir()` dead-code em paths.ts, docstring `paths.ts` x `homedir()`, `DFE_ROOT` dead em cache.test.ts, ref `FOLLOW-UP #3` em paths.ts.
- SUGESTAO NAO aplicada (1): redundancia `resolveBaseDir(opts.baseDirOverride)` vs `resolveDbPath(opts.baseDirOverride)` em update.ts — diff minimo, TOCTOU teorico nao justifica.

### Round 2

- BLOQUEANTE resolvido (teste migrado).
- 0 BLOQUEANTE / 0 IMPORTANTE / 1 SUGESTAO (residual do update.ts).

## Arquivos modificados

| Path | Mudanca | LoC |
|---|---|---|
| `packages/dfe-agent/src/paths.ts` (NOVO) | Centraliza `resolveBaseDir/resolveDbPath/resolveCacheDbPath` | +78 |
| `packages/dfe-agent/src/commands/update.ts` | Helper local removido; importa de paths.ts | -13/+8 |
| `packages/dfe-agent/src/commands/status.ts` | Helper local removido; importa de paths.ts; dead var | -10/+4 |
| `packages/dfe-agent/src/query/cache.ts` | Construtor recebe `baseDir`; abre propria conexao; `close()` | +34/-12 |
| `packages/dfe-agent/src/query/index.ts` | Helper local removido; re-export; passa `baseDir` ao cache | +8/-16 |
| `packages/dfe-agent/tests/query/cache.test.ts` | Migracao API; guard CI estendido; novo teste Bug B | +62/-12 |
| `packages/dfe-agent/tests/query/paths.test.ts` (NOVO) | 7 testes estruturais Bug A+B | +91 |
| `packages/dfe-agent/package.json` | `tests/query/paths.test.ts` no `npm test` | +1/-1 |

## Resultado de testes

- `npm test` (packages/dfe-agent): **60 passed / 0 fail / 2 skipped / 62 total**.
  - 2 skipped: `QueryCache BEHAVIORAL: hit na 2a chamada identica` + `QueryCache BEHAVIORAL: abre conexao propria em <baseDir>/cache.db` — gate nativo `win32 && Node >= 22` (e CI).
- `pytest tests/ --cov=src --cov-branch --cov-fail-under=80` (DFe-Agent root): **761 passed / 1 skipped (CONFAZ pre-existente) / cobertura 85.07%**. Baseline Sprint 14: 85.11% (-0.04pp margin).
- `tsc --noEmit` (packages/dfe-agent): sem erros.

## Padroes adotados

1. **Centralizacao via `paths.ts`** — fonte UNICA de verdade para paths. Mesmo pattern de Sprint 14 `src/utils/syspath_bootstrap.ensure_sys_path()` (gate anti-regressao cross-cutting).
2. **Construtor explicito sobre acoplamento implicito** — `QueryCache(baseDir, opts)` eh mais robusto que `QueryCache(handle, opts)` porque explicita a dependencia em vez de herdar o estado (readonly/RW) de outro modulo.
3. **Gate estrutural + comportamental** — `paths.test.ts` (estrutural, cross-platform) cobre Bug B mesmo em Windows + Node 24 onde os comportamentais skipam. Comportamental so' eh bonus.
4. **Re-export para compat de API** — `export { resolveBaseDir } from "../paths.js"` em `query/index.ts:43` preserva callers externos.
5. **`close()` idempotente em classes que abrem conexoes nativas** — gate contra destructor cleanup-hook crash em Node 22/24.

## Decisao arquitetural registrada

`paths.ts` eh a fonte canonica de paths no pacote. **Qualquer comando futuro** (install, uninstall, doctor, etc.) deve importar de `paths.ts`. **NAO** criar helpers locais de path.

## Follow-ups Sprint 15+

1. **Re-habilitar testes comportamentais em Windows + Node >= 22** — atualizar `better-sqlite3` (issue #336 do WillBrennan). Pino atual `11.5.0` quebra cleanup em Node 22+. Decisao humana via PLAN.
2. **`tests/integration/test_query_e2e_readonly.test.ts`** — gate E2E completo (criar `dfe.db` em `tmp_path`, rodar `search()`, validar que `cache.db` aparece separado). Setup pesado; adiado deste `/bug`.
3. **Estender `tests/e2e/smoke-test.ps1`** — incluir `query` (alem de `install --auto-setup && status`). Garante gate end-to-end em Windows runner.
4. **Versao bash de `smoke-test.ps1`** — gate CI Linux (Sprint 14 FOLLOW-UP #6, parcialmente atendido por este bug).
5. **`update.ts` SUGESTAO 2 (redundancia)** — opcional; implementar `dirname(resolveDbPath(opts.baseDirOverride))` se a redundancia for reportada novamente.

## Links uteis

- Sprint 14 plan: `PLAN_SPRINT14.md`
- Sprint 14 knowledge: `.opencode/rag/knowledge/2026-08-26-dev-sprint14-npm-package.md`
- Decisao D4: `2026-08-26-dev-sprint14-npm-package.md:21`
- Repositorio: https://github.com/wia-ti/dfe-agent
- Code-reviewer template: `.opencode/agent/code-reviewer.md`
- Pipeline `/bug`: `.opencode/command/bug.md`
