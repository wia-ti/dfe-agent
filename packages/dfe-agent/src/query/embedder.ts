/**
 * embedder.ts — wrapper de @xenova/transformers com LRU cache em memoria.
 *
 * @see PLAN_SPRINT14.md Task E.1
 *
 * Decisao D6: modelo canonico e `paraphrase-multilingual-MiniLM-L12-v2`
 * (mesmo do DFe-Agent Py via sentence-transformers). Drift entre Py e Node
 * deve ser < 0.01 (gate D.7 validado por tests/integration/test_embedding_parity).
 *
 * LRU 128: cobre uso interativo; descarta entradas mais antigas.
 */

import { createHash } from "node:crypto";
import { env, pipeline } from "@xenova/transformers";

const MODEL_NAME = "Xenova/paraphrase-multilingual-MiniLM-L12-v2";
const EMBEDDING_DIM = 384;
const LRU_SIZE = 128;

export const EMBEDDING_MODEL_NAME = MODEL_NAME;
export const EMBEDDING_DIMENSION = EMBEDDING_DIM;

export interface EmbeddingCacheEntry {
  vec: Float32Array;
  hash: string;
}

const cache: Map<string, Float32Array> = new Map();

function hash(text: string): string {
  return createHash("sha256")
    .update(text.trim().toLowerCase())
    .digest("hex");
}

let pipelineSingleton: any | null = null;

async function getExtractor(): Promise<any> {
  if (pipelineSingleton) return pipelineSingleton;
  env.allowLocalModels = false;
  env.useFS = false;
  pipelineSingleton = await pipeline("feature-extraction", MODEL_NAME);
  return pipelineSingleton;
}

/**
 * Codifica `text` em vetor 384-d (cosine-normalized).
 *
 * Cache LRU: 2a chamada com mesmo texto retorna o mesmo Float32Array sem
 * nova inferencia.
 *
 * @throws se o modelo nao conseguir carregar (problema conhecido: Node
 *         v22.21.1 com sharp/better-sqlite3 nativos; ver Sprint 13).
 */
export async function encode(text: string): Promise<Float32Array> {
  const key = hash(text);
  const cached = cache.get(key);
  if (cached) {
    // Move-to-end (LRU)
    cache.delete(key);
    cache.set(key, cached);
    return cached;
  }

  const extractor = await getExtractor();
  const out = await extractor(text, { pooling: "mean", normalize: true });
  const vec = new Float32Array(out.data as ArrayLike<number>);

  cache.set(key, vec);
  if (cache.size > LRU_SIZE) {
    const firstKey = cache.keys().next().value as string | undefined;
    if (firstKey !== undefined) cache.delete(firstKey);
  }
  return vec;
}

export function clearCache(): void {
  cache.clear();
}

export function cacheSize(): number {
  return cache.size;
}