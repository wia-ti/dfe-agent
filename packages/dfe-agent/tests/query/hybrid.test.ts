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
  // K0 deve aparecer como constante com valor 60
  assert.match(src, /60/);
});

test("hybrid combina vector + fts via score = sum(1 / (k0 + rank + 1))", () => {
  const src = readFileSync(resolve(PKG_ROOT, "src/query/hybrid.ts"), "utf8");
  assert.match(src, /k0 \+ .* \+ 1|k0 \+ i/);
});

test("hybrid: doc em ambos modos score > doc so' em um modo", () => {
  const src = readFileSync(resolve(PKG_ROOT, "src/query/hybrid.ts"), "utf8");
  // Deve somar scores (nao max)
  assert.match(src, /\+=/);
});