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

// === Behavioral test (gate code-reviewer I14) ===
// SKIP em CI: better-sqlite3 cleanup hook crasha em Node 22 Linux.
// Sprint 15: tambem skip em Windows + Node >= 22 (mesmo sintoma pre-existente).

const _NODE_MAJOR = parseInt(process.versions.node.split(".")[0], 10);
const _IS_WIN_NODE_NATIVE_BUG = process.platform === "win32" && _NODE_MAJOR >= 22;
const _SKIP_NATIVE = process.env.CI === "true"
  || process.env.DFE_AGENT_SKIP_NATIVE_TESTS === "1"
  || _IS_WIN_NODE_NATIVE_BUG;

test("sanitizeQuery BEHAVIORAL: remove chars especiais mas preserva phrase queries", async (t) => {
  if (_SKIP_NATIVE) {
    t.skip();
    return;
  }
  const { ftsSearch } = await import("../../dist/query/ftsSearch.js");
  const Database = (await import("better-sqlite3")).default;

  const handle = new Database(":memory:");
  handle.exec(`
    CREATE VIRTUAL TABLE fts_chunks USING fts5(
      chunk_id UNINDEXED, doc_id UNINDEXED, text
    );
    INSERT INTO fts_chunks (chunk_id, doc_id, text) VALUES
      (1, 100, 'nota tecnica NF-e 2024'),
      (2, 200, 'cancelamento de NFe apos publicacao'),
      (3, 300, 'prazo de validade da nota fiscal');
  `);

  const hits = ftsSearch(handle as any, "nota tecnica", 5);
  assert.ok(hits.length >= 1, `esperado >=1 hit; obtido ${hits.length}`);
  // doc 100 contem "nota tecnica" exato
  assert.equal(hits[0].doc_id, 100, `doc_id mais relevante deve ser 100; obtido ${hits[0].doc_id}`);

  handle.close();
});