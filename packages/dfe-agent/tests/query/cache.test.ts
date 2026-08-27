import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const PKG_ROOT = process.cwd();

// CI runners (Linux + Node 22) E maquinas Windows + Node >=22 tem bug em
// RemoveEnvironmentCleanupHook ao carregar better-sqlite3 natives
// (Database::scalar deleting destructor -> v8 hook cleanup panic).
// Sprint 14: skip behaviorals em CI. Sprint 15: estende para Windows
// Node >= 22 onde o sintoma tambem reproduz (gate FOLLOW-UP Sprint 14 #6).
// Tests comportamentais rodam apenas em Linux + Node < 22.
const NODE_MAJOR = parseInt(process.versions.node.split(".")[0], 10);
const IS_WIN_NODE_NATIVE_BUG = process.platform === "win32" && NODE_MAJOR >= 22;
const CI = process.env.CI === "true"
  || process.env.DFE_AGENT_SKIP_NATIVE_TESTS === "1"
  || IS_WIN_NODE_NATIVE_BUG;

test("QueryCache existe e expoe classe", () => {
  const p = resolve(PKG_ROOT, "src/query/cache.ts");
  assert.ok(existsSync(p), "src/query/cache.ts deve existir (Task E.4)");
  const src = readFileSync(p, "utf8");
  assert.match(src, /export class QueryCache/);
});

test("QueryCache usa sha256(model|mode|q_norm) como chave", () => {
  const src = readFileSync(resolve(PKG_ROOT, "src/query/cache.ts"), "utf8");
  assert.match(src, /createHash|sha256/);
  assert.match(src, /model.*mode.*q|model\+.*mode\+.*q/);
});

test("QueryCache persiste em SQLite (query_cache table)", () => {
  const src = readFileSync(resolve(PKG_ROOT, "src/query/cache.ts"), "utf8");
  assert.match(src, /CREATE TABLE.*query_cache/i);
  assert.match(src, /query_hash.*PRIMARY KEY/);
});

test("QueryCache normaliza query (trim + lowercase)", () => {
  const src = readFileSync(resolve(PKG_ROOT, "src/query/cache.ts"), "utf8");
  assert.match(src, /trim\(\)/);
  assert.match(src, /toLowerCase/);
});

test("QueryCache invalida quando modelo muda (env var)", () => {
  const src = readFileSync(resolve(PKG_ROOT, "src/query/cache.ts"), "utf8");
  assert.match(src, /DFE_EMBEDDING_MODEL|embedding_model/);
});

// === Behavioral test (gate code-reviewer I14) ===
// SKIP em CI: better-sqlite3 cleanup hook crasha em Node 22 Linux containers
// (assertion (env) != nullptr em RemoveEnvironmentCleanupHook). Roda apenas local.
// Sprint 15: tambem skip em Windows + Node >= 22 (mesmo sintoma).
test("QueryCache BEHAVIORAL: hit na 2a chamada identica (sem nova escrita)", async (t) => {
  if (CI) {
    t.skip();
    return;
  }
  const { QueryCache } = await import("../../dist/query/cache.js");

  // API Sprint 15 (Bug B): construtor recebe `baseDir` e abre propria conexao
  // em <baseDir>/cache.db. Antes recebia `handle: BetterSqlite3Database`.
  const tmp = mkdtempSync(join(tmpdir(), "dfe-cache-hit-"));
  let cache: any = null;
  let cacheB: any = null;
  try {
    cache = new QueryCache(tmp, { model: "test-model" });

    const vec = new Float32Array([1.0, 2.0, 3.0, 4.0]);
    cache.set("semantic", "O que e a NF-e?", vec);

    const hit = cache.get("semantic", "O que e a NF-e?");
    assert.ok(hit, "1a chamada: cache deve retornar hit");
    assert.equal(hit.length, 4);
    assert.deepEqual(Array.from(hit), Array.from(vec));

    // 2a chamada: hit com normalizacao (espacos + lowercase)
    const hit2 = cache.get("semantic", "  o QUE e a nf-e?  ");
    assert.ok(hit2, "2a chamada: cache deve hit mesmo com whitespace/case diferente");
    assert.deepEqual(Array.from(hit2), Array.from(vec));

    // Model diferente: miss (mesmo baseDir, model diferente => chave diferente)
    cacheB = new QueryCache(tmp, { model: "other-model" });
    const miss = cacheB.get("semantic", "O que e a NF-e?");
    assert.equal(miss, null, "model diferente: cache deve missar");
  } finally {
    if (cacheB) cacheB.close();
    if (cache) cache.close();
    rmSync(tmp, { recursive: true, force: true });
  }
});

// === Bug B — gate anti-regressao Sprint 15 ===
// QueryCache NAO pode acoplar ao handle de dfe.db. Deve abrir SUA PROPRIA
// conexao em <baseDir>/cache.db (read-write), isolada da base readonly.
//
// Hoje (pre-fix): construtor aceita `handle`. Set()/Get() em cache persistido
// so' funciona se o handle externo for read-write. Em query/index.ts:153
// o handle e' readonly -> CREATE TABLE quebra -> "attempt to write a readonly
// database".
//
// Apos o fix: construtor aceita `baseDir: string` e abre conexao propria.
test("QueryCache BEHAVIORAL: abre conexao propria em <baseDir>/cache.db (gate Bug B)", async (t) => {
  if (CI) {
    t.skip();
    return;
  }
  const { QueryCache } = await import("../../dist/query/cache.js");
  const tmp = mkdtempSync(join(tmpdir(), "dfe-cache-test-"));
  let cache: any = null;
  try {
    // API NOVA: construtor recebe baseDir e abre propria conexao.
    cache = new QueryCache(tmp, { model: "test-model" });

    // 1. <tmp>/cache.db deve ter sido criado (handle proprio).
    assert.ok(
      existsSync(join(tmp, "cache.db")),
      "QueryCache(tmp) deve criar <tmp>/cache.db (conexao propria, gate Bug B)",
    );

    // 2. set + get funcionam end-to-end (isolados de qualquer handle externo).
    const vec = new Float32Array([0.1, 0.2, 0.3, 0.4]);
    cache.set("semantic", "pergunta iso", vec);
    const hit = cache.get("semantic", "pergunta iso");
    assert.ok(hit, "cache hit esperado apos set");
    assert.deepEqual(Array.from(hit!), [0.1, 0.2, 0.3, 0.4]);

    // 3. Normalizacao da chave (trim + lowercase).
    const hitNormalized = cache.get("semantic", "  PERGUNTA ISO  ");
    assert.ok(hitNormalized, "normalizacao da chave deve hit");

    // 4. Model diferente -> miss.
    const cacheB = new QueryCache(tmp, { model: "outro-modelo" });
    const miss = cacheB.get("semantic", "pergunta iso");
    assert.equal(miss, null, "model diferente: cache deve missar");
    cacheB.close();
  } finally {
    if (cache) cache.close();
    rmSync(tmp, { recursive: true, force: true });
  }
});