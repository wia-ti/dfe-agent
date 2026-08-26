// .opencode/rag/lib/embedder.ts
// Wrapper do all-MiniLM-L6-v2 via @xenova/transformers.
// Lazy load do modelo (so baixa na primeira chamada). Singleton.

import { env } from "@xenova/transformers";
import type { FeatureExtractionPipeline } from "@xenova/transformers";

const MODEL_ID: string = "Xenova/all-MiniLM-L6-v2";
const EMBEDDING_DIM: number = 384;

env.allowLocalModels = false;
env.useBrowserCache = false;

let pipelinePromise: Promise<FeatureExtractionPipeline> | null = null;

async function getPipeline(): Promise<FeatureExtractionPipeline> {
  if (!pipelinePromise) {
    pipelinePromise = (async (): Promise<FeatureExtractionPipeline> => {
      const transformers = await import("@xenova/transformers");
      const pipe = await transformers.pipeline("feature-extraction", MODEL_ID);
      return pipe as FeatureExtractionPipeline;
    })();
  }
  return pipelinePromise;
}

export function getModelId(): string {
  return MODEL_ID;
}

export function getEmbeddingDim(): number {
  return EMBEDDING_DIM;
}

export async function embed(text: string): Promise<Float32Array> {
  const pipe = await getPipeline();
  const output = await pipe(text, { pooling: "mean", normalize: true });
  return new Float32Array(output.data as Float32Array);
}

export async function embedBatch(texts: string[]): Promise<Float32Array[]> {
  if (texts.length === 0) {
    return [];
  }
  const pipe = await getPipeline();
  const out: Float32Array[] = [];
  for (const t of texts) {
    const v = await pipe(t, { pooling: "mean", normalize: true });
    out.push(new Float32Array(v.data as Float32Array));
  }
  return out;
}

export function toBuffer(vec: Float32Array): Buffer {
  return Buffer.from(vec.buffer, vec.byteOffset, vec.byteLength);
}

export function fromBuffer(buf: Buffer): Float32Array {
  return new Float32Array(buf.buffer, buf.byteOffset, buf.byteLength / 4);
}