/**
 * paths.test.ts — gate anti-regressao Sprint 15 BUG-A.
 *
 * Hipotese coberta: `dfe-agent update && dfe-agent query` end-to-end
 * exige que TODOS os entrypoints (update, status, query/index)
 * resolvam $HOME/dfe-agent/.dfe-agent/dfe.db, NAO $HOME/dfe.db.
 *
 * @see PLAN_SPRINT14.md D4 (decisao: ~/.dfe-agent/dfe.db)
 * @see AGENTS.md Sprint 14 FOLLOW-UP #3
 *
 * Antes do fix:
 *   - src/commands/update.ts:47-52  -> esquece ".dfe-agent"
 *   - src/commands/status.ts:20-24  -> esquece ".dfe-agent"
 *   - src/query/index.ts:64-68      -> ja correto (canônico)
 *
 * Apos o fix: todos importam de src/paths.ts OU tem o regex canonical.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const PKG_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

const ENTRYPOINTS: Array<{ name: string; path: string }> = [
  { name: "update (commands)", path: "src/commands/update.ts" },
  { name: "status (commands)", path: "src/commands/status.ts" },
  { name: "query/index", path: "src/query/index.ts" },
];

for (const { name, path } of ENTRYPOINTS) {
  test(`entrypoint ${name}: usa paths.ts centralizado OU regex canonical ".dfe-agent"`, () => {
    const abs = resolve(PKG_ROOT, path);
    assert.ok(existsSync(abs), `${abs} deve existir`);
    const src = readFileSync(abs, "utf8");

    // 2 sinais canonicos (pre-fix aceita query/index.ts legado):
    //  (a) importa de paths.ts (`import ... from "../paths.js"`) — canonico pos-fix.
    //      Tambem aceita import inline de simbolos resolveBase*/resolveDb*/resolveCacheDb*
    //      desde que venham de paths.js.
    //  (c) tem o pattern `resolve( ... ".dfe-agent"` (legado pre-fix em query/index.ts).
    //      Tolerante a `)` dentro porque
    //      `resolve(process.env.HOME ?? homedir(), ".dfe-agent")` tem um
    //      `)` antes da aspas.
    const usesCentralized =
      /from\s+["'][^"']*paths\.js?["']/.test(src)
      || /import\s+\{[^}]*(resolveBaseDir|resolveDbPath|resolveCacheDbPath)[^}]*\}\s*from/.test(src);
    const hasCanonicalPattern = /resolve\(\s*[^"]*"\.dfe-agent"/.test(src);

    assert.ok(
      usesCentralized || hasCanonicalPattern,
      `${path} precisa importar de paths.ts OU ter 'resolve(... ".dfe-agent")' (legado).\n` +
        `Gate: src/paths.ts com resolveBaseDir/resolveDbPath/resolveCacheDbPath.`,
    );
  });
}

test("src/paths.ts existe e expoe resolveBaseDir + resolveDbPath + resolveCacheDbPath", () => {
  const p = resolve(PKG_ROOT, "src/paths.ts");
  assert.ok(existsSync(p), "src/paths.ts deve existir (gate anti-regressao Sprint 15 BUG-A)");
  const src = readFileSync(p, "utf8");
  assert.match(src, /export (async )?function resolveBaseDir/);
  assert.match(src, /export (async )?function resolveDbPath/);
  assert.match(src, /export (async )?function resolveCacheDbPath/);
});

test("src/paths.ts respeita override de teste (baseDirOverride) e env DFE_AGENT_BASE_DIR", () => {
  const p = resolve(PKG_ROOT, "src/paths.ts");
  const src = readFileSync(p, "utf8");
  assert.match(src, /DFE_AGENT_BASE_DIR/);
  assert.match(src, /baseDirOverride/);
});

// === Gate Bug B (Sprint 15 — desacoplamento cache do dfe.db readonly) ===
// Esses testes estruturais cobrem Bug B em TODO ambiente (mesmo onde os
// comportamentais sao skipados por Windows + Node >= 22 natives bug —
// cache.test.ts:11-16). Sem eles, o cache poderia regredir silenciosamente
// em maquinas onde o teste comportamental nao roda.

test("cache.ts importa resolveCacheDbPath de paths.ts (gate Bug B)", () => {
  const cachePath = resolve(PKG_ROOT, "src/query/cache.ts");
  const src = readFileSync(cachePath, "utf8");
  assert.match(
    src,
    /from\s+["'][^"']*paths\.js?["']/,
    "cache.ts precisa importar de paths.ts (canonico)",
  );
  assert.match(
    src,
    /resolveCacheDbPath/,
    "cache.ts precisa usar resolveCacheDbPath para resolver <baseDir>/cache.db",
  );
  assert.match(
    src,
    /new\s+Database\s*\(/,
    "cache.ts precisa abrir SUA PROPRIA conexao (nao receber handle externo). " +
      "Conexao compartilhada com dfe.db readonly = SQLITE_READONLY (Bug B original)",
  );
  // NUNCA pode receber handle externo como parametro do construtor.
  // Antes do fix: `constructor(handle: BetterSqlite3Database, ...)` — quebrava.
  // Apos o fix: `constructor(baseDir: string, ...)` — usa paths.ts.
  assert.doesNotMatch(
    src,
    /constructor\s*\(\s*handle\s*:\s*BetterSqlite3Database/,
    "cache.ts nao pode mais receber handle externo (acoplamento legacy Bug B)",
  );
});

test("query/index.ts passa baseDir ao construtor do QueryCache (gate Bug B)", () => {
  const indexPath = resolve(PKG_ROOT, "src/query/index.ts");
  const src = readFileSync(indexPath, "utf8");
  // Antes do fix: `new QueryCache(handle)`.
  // Apos o fix:  `new QueryCache(resolveBaseDir(...))`.
  assert.match(
    src,
    /new\s+QueryCache\s*\(\s*resolveBaseDir\s*\(/,
    "query/index.ts precisa passar baseDir (resolveBaseDir) ao QueryCache, NAO o handle do dfe.db",
  );
  // Sanity: nao pode estar passando handle (variavel `handle`).
  assert.doesNotMatch(
    src,
    /new\s+QueryCache\s*\(\s*handle\s*\)/,
    "QueryCache(handle) eh o acoplamento legacy Bug B — proibido pos-fix",
  );
});
