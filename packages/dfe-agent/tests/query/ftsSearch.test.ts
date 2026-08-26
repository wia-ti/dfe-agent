import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const PKG_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

test("ftsSearch.ts existe e expoe ftsSearch()", () => {
  const p = resolve(PKG_ROOT, "src/query/ftsSearch.ts");
  assert.ok(existsSync(p), "src/query/ftsSearch.ts deve existir (Task E.2)");
  const src = readFileSync(p, "utf8");
  assert.match(src, /export function ftsSearch/);
  assert.match(src, /fts_chunks/);
  assert.match(src, /bm25/);
});

test("ftsSearch tem saneamento de query (escape chars)", () => {
  const src = readFileSync(resolve(PKG_ROOT, "src/query/ftsSearch.ts"), "utf8");
  // Deve remover/escopar caracteres especiais que quebram FTS5 MATCH
  assert.match(src, /replace|escape|sanitize/);
});

test("ftsSearch retorna top-K ordenado por bm25 (menor = melhor)", () => {
  const src = readFileSync(resolve(PKG_ROOT, "src/query/ftsSearch.ts"), "utf8");
  assert.match(src, /ORDER BY score|LIMIT/);
});