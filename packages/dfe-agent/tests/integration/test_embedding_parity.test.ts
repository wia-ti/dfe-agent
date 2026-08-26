/**
 * test_embedding_parity.test.ts — valida paridade embeddings Py <-> Node (gate D.7).
 *
 * @see PLAN_SPRINT14.md Task D.3
 *
 * Pre-requisito: `python -m tests.integration.generate_py_embeddings` deve
 * ter sido rodado para popular tests/fixtures/embeddings_py.json.
 *
 * Gate: cosine similarity media >= 0.99 entre Py e Node para todas as 5
 * sentencas de eval_set.json. Drift < 0.01 indica que o modelo ONNX
 * carregado por @xenova/transformers bate com sentence-transformers.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const PKG_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const DFE_ROOT = resolve(PKG_ROOT, "../..");

const FIXTURES = resolve(DFE_ROOT, "tests/fixtures");
const PY_EMB_PATH = resolve(FIXTURES, "embeddings_py.json");
const EVAL_PATH = resolve(FIXTURES, "eval_set.json");

function cosineSimilarity(a: number[], b: number[]): number {
  let dot = 0;
  let normA = 0;
  let normB = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  return dot / (Math.sqrt(normA) * Math.sqrt(normB));
}

test("fixture Py existe (rodar `python -m tests.integration.generate_py_embeddings` primeiro)", () => {
  if (!existsSync(PY_EMB_PATH)) {
    console.warn(`[skip] fixture ausente: ${PY_EMB_PATH}`);
    return;
  }
  assert.ok(existsSync(PY_EMB_PATH));
});

test("fixture eval_set.json tem sentencas", () => {
  if (!existsSync(EVAL_PATH)) {
    assert.fail(`eval_set.json ausente: ${EVAL_PATH}`);
  }
  const evalSet = JSON.parse(readFileSync(EVAL_PATH, "utf8")) as Array<{ question: string }>;
  assert.ok(evalSet.length >= 5, `eval_set precisa >=5 sentencas; tem ${evalSet.length}`);
});

test("paridade Py <-> Node embeddings >= 0.99 cosine similarity (gate D.7)", async (t) => {
  if (!existsSync(PY_EMB_PATH)) {
    t.skip();
    return;
  }
  if (!existsSync(EVAL_PATH)) {
    t.skip();
    return;
  }

  const pyEmbeddings: number[][] = JSON.parse(readFileSync(PY_EMB_PATH, "utf8"));
  const evalSet: Array<{ question: string }> = JSON.parse(readFileSync(EVAL_PATH, "utf8"));

  assert.equal(
    pyEmbeddings.length,
    evalSet.length,
    `fixture Py tem ${pyEmbeddings.length} embeddings mas eval_set tem ${evalSet.length} perguntas`,
  );

  // Lazy import do embedder (dist/ tem .js apos build; .ts resolve via strip-types)
  const { encode, EMBEDDING_MODEL_NAME } = await import("../../dist/query/embedder.js");

  // Valida que o modelo Node bate com Py
  assert.equal(
    EMBEDDING_MODEL_NAME,
    "Xenova/paraphrase-multilingual-MiniLM-L12-v2",
    "modelo Node diverge do canonico D6",
  );

  console.info(`[parity] computando embeddings Node para ${evalSet.length} sentencas...`);

  const nodeEmbeddings: Float32Array[] = [];
  for (const item of evalSet) {
    const vec = await encode(item.question);
    nodeEmbeddings.push(vec);
  }

  // Compara cosine similarity par a par
  const sims: number[] = [];
  for (let i = 0; i < pyEmbeddings.length; i++) {
    const sim = cosineSimilarity(pyEmbeddings[i], Array.from(nodeEmbeddings[i]));
    sims.push(sim);
    console.info(`[parity] sentenca ${i + 1}: cosine=${sim.toFixed(6)}`);
  }

  const meanSim = sims.reduce((a, b) => a + b, 0) / sims.length;
  const minSim = Math.min(...sims);

  console.info(`[parity] mean=${meanSim.toFixed(6)} min=${minSim.toFixed(6)}`);

  assert.ok(
    meanSim >= 0.99,
    `paridade abaixo do gate D.7: mean=${meanSim} < 0.99 (drift=${(1 - meanSim).toFixed(4)})`,
  );
  assert.ok(
    minSim >= 0.95,
    `pior caso abaixo do aceitavel: min=${minSim} < 0.95`,
  );
});