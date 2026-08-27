import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const PKG_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

// === Behavioral test (gate code-reviewer I14 + Sprint 16 Bug C) ===
// SKIP em CI: better-sqlite3 cleanup hook crasha em Node 22 Linux.
// Sprint 15: tambem skip em Windows + Node >= 22 (mesmo sintoma pre-existente).

const _NODE_MAJOR = parseInt(process.versions.node.split(".")[0], 10);
const _IS_WIN_NODE_NATIVE_BUG = process.platform === "win32" && _NODE_MAJOR >= 22;
const _SKIP_NATIVE = process.env.CI === "true"
  || process.env.DFE_AGENT_SKIP_NATIVE_TESTS === "1"
  || _IS_WIN_NODE_NATIVE_BUG;

test("vectorSearch.ts existe e expoe vectorSearch()", () => {
  const p = resolve(PKG_ROOT, "src/query/vectorSearch.ts");
  assert.ok(existsSync(p), "src/query/vectorSearch.ts deve existir (Task E.1)");
  const src = readFileSync(p, "utf8");
  assert.match(src, /export function vectorSearch/);
  assert.match(src, /vec_chunks/);
  assert.match(src, /distance/);
});

test("vectorSearch usa schema Py real (aliases chunk_index AS chunk_id, document_id AS doc_id) — gate Bug C Sprint 16", () => {
  const src = readFileSync(resolve(PKG_ROOT, "src/query/vectorSearch.ts"), "utf8");
  // Py produz vec_chunks(document_id, chunk_index); Node precisa casar via aliases SQL.
  // Antes do fix: SELECT chunk_id, doc_id ... FROM vec_chunks — falha (no such column).
  // Apos o fix: SELECT chunk_index AS chunk_id, document_id AS doc_id ... FROM vec_chunks.
  assert.match(
    src,
    /chunk_index\s+AS\s+chunk_id/,
    "vectorSearch precisa usar alias chunk_index AS chunk_id (gate Bug C)",
  );
  assert.match(
    src,
    /document_id\s+AS\s+doc_id/,
    "vectorSearch precisa usar alias document_id AS doc_id (gate Bug C)",
  );
});

test("vectorSearch.ts NAO referencia colunas antigas chunk_id/doc_id sem alias", () => {
  const src = readFileSync(resolve(PKG_ROOT, "src/query/vectorSearch.ts"), "utf8");
  // Antes do fix: "chunk_id, doc_id" (sem alias) -> quebra runtime.
  // Apos o fix: "chunk_index AS chunk_id, document_id AS doc_id".
  // Proibe a forma antiga no SELECT.
  assert.doesNotMatch(
    src,
    /SELECT\s+chunk_id\s*,\s*doc_id/,
    "vectorSearch nao pode usar 'SELECT chunk_id, doc_id' direto (drift Py)",
  );
});

test("vectorSearch BEHAVIORAL: hits com schema Py real (document_id, chunk_index)", async (t) => {
  if (_SKIP_NATIVE) {
    t.skip();
    return;
  }
  const { vectorSearch } = await import("../../dist/query/vectorSearch.js");
  const Database = (await import("better-sqlite3")).default;

  const handle = new Database(":memory:");
  // Schema Py real (vec0 com chaves document_id/chunk_index).
  handle.exec(`
    CREATE VIRTUAL TABLE vec_chunks USING vec0(
      embedding float[4],
      document_id INTEGER,
      chunk_index INTEGER,
      text TEXT,
      source_url TEXT,
      doc_title TEXT
    );
  `);

  // 3 chunks: doc 1 (idx 0, idx 1) e doc 2 (idx 0). Embeddings normalizados.
  handle
    .prepare(
      `INSERT INTO vec_chunks (embedding, document_id, chunk_index, text, source_url, doc_title)
       VALUES (?, ?, ?, ?, ?, ?)`,
    )
    .run(Buffer.from(new Float32Array([1.0, 0.0, 0.0, 0.0]).buffer), 1, 0, "doc1 chunk0", "https://ex.com/1", "Doc1");
  handle
    .prepare(
      `INSERT INTO vec_chunks (embedding, document_id, chunk_index, text, source_url, doc_title)
       VALUES (?, ?, ?, ?, ?, ?)`,
    )
    .run(Buffer.from(new Float32Array([0.9, 0.1, 0.0, 0.0]).buffer), 1, 1, "doc1 chunk1", "https://ex.com/1", "Doc1");
  handle
    .prepare(
      `INSERT INTO vec_chunks (embedding, document_id, chunk_index, text, source_url, doc_title)
       VALUES (?, ?, ?, ?, ?, ?)`,
    )
    .run(Buffer.from(new Float32Array([0.0, 1.0, 0.0, 0.0]).buffer), 2, 0, "doc2 chunk0", "https://ex.com/2", "Doc2");

  const queryVec = new Float32Array([1.0, 0.0, 0.0, 0.0]);
  const hits = vectorSearch(handle as any, queryVec, 10);

  assert.ok(hits.length >= 1, `esperado >=1 hit; obtido ${hits.length}`);
  // doc 1 deve ranquear acima de doc 2 (mais proximo).
  assert.equal(hits[0].doc_id, 1, `doc 1 deve ser mais similar; obtido doc ${hits[0].doc_id}`);
  assert.equal(hits[0].chunk_id, 0, `chunk 0 de doc 1 esperado; obtido ${hits[0].chunk_id}`);

  handle.close();
});
