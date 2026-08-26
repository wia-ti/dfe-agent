import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const PKG_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

test("embedder.ts existe e expoe encode()", () => {
  const p = resolve(PKG_ROOT, "src/query/embedder.ts");
  assert.ok(existsSync(p), "src/query/embedder.ts deve existir (Task E.1)");
  const src = readFileSync(p, "utf8");
  assert.match(src, /export.*async function encode/);
  assert.match(src, /LRU|lru/);
  assert.match(src, /paraphrase-multilingual-MiniLM-L12-v2/);
});

test("vectorSearch.ts existe e expoe vectorSearch()", () => {
  const p = resolve(PKG_ROOT, "src/query/vectorSearch.ts");
  assert.ok(existsSync(p), "src/query/vectorSearch.ts deve existir (Task E.1)");
  const src = readFileSync(p, "utf8");
  assert.match(src, /export function vectorSearch/);
  assert.match(src, /vec_chunks/);
  assert.match(src, /MATCH/);
});

test("embedder usa dimensao 384 (gate D6)", () => {
  const src = readFileSync(resolve(PKG_ROOT, "src/query/embedder.ts"), "utf8");
  assert.match(src, /384/);
});

test("vectorSearch tem dedup por doc_id", () => {
  const src = readFileSync(resolve(PKG_ROOT, "src/query/vectorSearch.ts"), "utf8");
  assert.match(src, /doc_id/);
});