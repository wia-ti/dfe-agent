import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const PKG_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

test("cache.ts existe e expoe QueryCache", () => {
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