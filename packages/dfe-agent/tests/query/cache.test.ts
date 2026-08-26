import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const PKG_ROOT = process.cwd();
const DFE_ROOT = resolve(PKG_ROOT, "../..");

// Helper: CI runners (Linux + Node 22) tem bug em RemoveEnvironmentCleanupHook
// ao carregar better-sqlite3/@xenova/transformers. Sprint 14: skip behaviorals
// em CI. Rodam apenas localmente.
const CI = process.env.CI === "true" || process.env.DFE_AGENT_SKIP_NATIVE_TESTS === "1";

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
test("QueryCache BEHAVIORAL: hit na 2a chamada identica (sem nova escrita)", async (t) => {
  if (CI) {
    t.skip();
    return;
  }
  const { QueryCache } = await import("../../dist/query/cache.js");
  const Database = (await import("better-sqlite3")).default;

  const handle = new Database(":memory:");
  const cache = new QueryCache(handle as any, { model: "test-model" });

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

  // Model diferente: miss
  const cacheB = new QueryCache(handle as any, { model: "other-model" });
  const miss = cacheB.get("semantic", "O que e a NF-e?");
  assert.equal(miss, null, "model diferente: cache deve missar");

  handle.close();
});