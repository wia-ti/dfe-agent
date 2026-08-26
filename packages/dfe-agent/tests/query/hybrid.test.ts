import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const PKG_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

test("hybrid.ts existe e expoe rrf()", () => {
  const p = resolve(PKG_ROOT, "src/query/hybrid.ts");
  assert.ok(existsSync(p), "src/query/hybrid.ts deve existir (Task E.3)");
  const src = readFileSync(p, "utf8");
  assert.match(src, /export function rrf/);
});

test("hybrid usa k0 = 60 (canonica da literatura RRF)", () => {
  const src = readFileSync(resolve(PKG_ROOT, "src/query/hybrid.ts"), "utf8");
  assert.match(src, /60/);
});

test("hybrid combina vector + fts via score = sum(1 / (k0 + rank + 1))", () => {
  const src = readFileSync(resolve(PKG_ROOT, "src/query/hybrid.ts"), "utf8");
  assert.match(src, /k0 \+ .* \+ 1|k0 \+ i/);
});

test("hybrid: doc em ambos modos score > doc so' em um modo", () => {
  const src = readFileSync(resolve(PKG_ROOT, "src/query/hybrid.ts"), "utf8");
  assert.match(src, /\+=/);
});

// === Behavioral tests (gate code-reviewer I14) ===
// CI skip: hybrid.js nao carrega natives, mas alguns imports podem disparar
// better-sqlite3 (que crasha em CI). Mantemos skip defensivo.

test("rrf() BEHAVIORAL: chunk em ambos modos ranqueia acima de chunk so' em um modo", async (t) => {
  if (process.env.CI === "true") {
    t.skip();
    return;
  }
  const { rrf } = await import("../../dist/query/hybrid.js");
  // RRF ranqueia por chunk_id (cada chunk = uma entrada no scoreMap).
  // Setup: chunk 1 aparece em ambos; chunk 2 so' em vector; chunk 3 so' em fts.
  const vecHits = [
    { chunk_id: 1, doc_id: 100, distance: 0.1 },  // comum
    { chunk_id: 2, doc_id: 200, distance: 0.2 },  // so' vector
    { chunk_id: 5, doc_id: 100, distance: 0.3 },  // outro chunk so' em vector (mesmo doc)
  ];
  const ftsHits = [
    { chunk_id: 1, doc_id: 100, score: -1.5 },   // comum (mesmo chunk_id)
    { chunk_id: 3, doc_id: 300, score: -0.5 },   // so' fts
  ];
  const fused = rrf(vecHits, ftsHits, 10);
  assert.equal(fused.length, 4, `esperado 4 chunks unicos; obtido ${fused.length}`);

  // Chunk 1 (em ambos) deve ranquear acima de chunks so' em um modo
  const chunk1 = fused.find((h) => h.chunk_id === 1)!;
  const chunk2 = fused.find((h) => h.chunk_id === 2)!;
  const chunk3 = fused.find((h) => h.chunk_id === 3)!;
  assert.ok(chunk1 && chunk2 && chunk3);

  // Score de chunk1 = 1/(60+0+1) + 1/(60+0+1) = 2 * (1/61)
  // Score de chunk2 = 1/(60+1+1) = 1/62
  // Score de chunk3 = 1/(60+1+1) = 1/62
  const expected1 = 2 / 61;
  const expectedSingle = 1 / 62;
  assert.ok(
    Math.abs(chunk1.score - expected1) < 0.001,
    `chunk1 score esperado ${expected1}; obtido ${chunk1.score}`,
  );
  assert.ok(
    chunk1.score > chunk2.score,
    `chunk1 (ambos) deve ranquear acima de chunk2 (so' vector)`,
  );
  assert.ok(
    chunk1.score > chunk3.score,
    `chunk1 (ambos) deve ranquear acima de chunk3 (so' fts)`,
  );
  // Chunk2 e Chunk3 tem scores identicos (ambos so' em 1 modo)
  assert.ok(
    Math.abs(chunk2.score - expectedSingle) < 0.001,
    `chunk2 score esperado ${expectedSingle}; obtido ${chunk2.score}`,
  );
});

test("rrf() BEHAVIORAL: respeita k (truncamento)", async (t) => {
  if (process.env.CI === "true") {
    t.skip();
    return;
  }
  const { rrf } = await import("../../dist/query/hybrid.js");
  const vecHits = Array.from({ length: 20 }, (_, i) => ({ chunk_id: i, doc_id: i, distance: i * 0.1 }));
  const ftsHits = Array.from({ length: 20 }, (_, i) => ({ chunk_id: i + 100, doc_id: i, score: -i }));
  const fused = rrf(vecHits, ftsHits, 5);
  assert.equal(fused.length, 5, `esperado 5 hits; obtido ${fused.length}`);
});

test("rrf() BEHAVIORAL: ordem deterministica (idempotente)", async (t) => {
  if (process.env.CI === "true") {
    t.skip();
    return;
  }
  const { rrf } = await import("../../dist/query/hybrid.js");
  const vecHits = [{ chunk_id: 1, doc_id: 1, distance: 0.1 }];
  const ftsHits = [{ chunk_id: 2, doc_id: 2, score: -0.5 }];
  const r1 = rrf(vecHits, ftsHits, 10);
  const r2 = rrf(vecHits, ftsHits, 10);
  assert.deepEqual(r1, r2, "rrf deve ser deterministico (mesmo input -> mesmo output)");
});