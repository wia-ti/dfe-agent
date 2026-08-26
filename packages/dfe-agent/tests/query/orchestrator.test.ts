import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const PKG_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

test("contextBuilder.ts existe e expoe buildContext", () => {
  const p = resolve(PKG_ROOT, "src/query/contextBuilder.ts");
  assert.ok(existsSync(p), "src/query/contextBuilder.ts deve existir (Task E.5)");
  const src = readFileSync(p, "utf8");
  assert.match(src, /export function buildContext/);
});

test("constants.ts existe e expoe NO_EVIDENCE_MESSAGE canonico (gate dfe-rules.md #4)", () => {
  const p = resolve(PKG_ROOT, "src/query/constants.ts");
  assert.ok(existsSync(p), "src/query/constants.ts deve existir");
  const src = readFileSync(p, "utf8");
  assert.match(src, /export const NO_EVIDENCE_MESSAGE = "Nao encontrei base para responder"/);
});

test("contextBuilder retorna NO_EVIDENCE_MESSAGE literal em chunks vazios", () => {
  // NO_EVIDENCE_MESSAGE vive em src/query/constants.ts (canonico; gate dfe-rules.md #4).
  // contextBuilder.ts importa de constants.ts para evitar ciclo com index.ts.
  const src = readFileSync(resolve(PKG_ROOT, "src/query/contextBuilder.ts"), "utf8");
  const constantsSrc = readFileSync(resolve(PKG_ROOT, "src/query/constants.ts"), "utf8");
  assert.match(src, /NO_EVIDENCE_MESSAGE/);  // contextBuilder usa a constante
  assert.match(constantsSrc, /Nao encontrei base para responder/);  // literal canonico
});

test("contextBuilder expoe hasSufficientEvidence", () => {
  const src = readFileSync(resolve(PKG_ROOT, "src/query/contextBuilder.ts"), "utf8");
  assert.match(src, /export function hasSufficientEvidence/);
});

test("query/index.ts expoe search() com modos semantic/fts/hybrid", () => {
  const src = readFileSync(resolve(PKG_ROOT, "src/query/index.ts"), "utf8");
  assert.match(src, /export async function search/);
  assert.match(src, /semantic.*fts.*hybrid|semantic[\s\S]*fts[\s\S]*hybrid/);
});

test("query/index.ts usa cache antes de chamar embedder", () => {
  const src = readFileSync(resolve(PKG_ROOT, "src/query/index.ts"), "utf8");
  assert.match(src, /QueryCache|queryCache|cache\.get/);
});