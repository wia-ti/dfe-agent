/**
 * query/index.ts — query engine Node (port de src/query/query_engine.py).
 *
 * @see PLAN_SPRINT14.md Fase E (5 tasks)
 * @see src/query/query_engine.py — equivalente Py
 *
 * Modos opt-in (mesmo do CLI Py):
 *   semantic    vector search com sqlite-vec (default)
 *   fts         FTS5 BM25 lexical
 *   hybrid      RRF k=60 entre vector + FTS5
 *
 * Constante NO_EVIDENCE_MESSAGE canonica — mesma string em
 * src/query/context_builder.py do Py (gate dfe-rules.md #4).
 *   NUNCA duplique este literal.
 */

import Database from "better-sqlite3";
import { homedir, tmpdir } from "node:os";
import { resolve } from "node:path";

import { encode, EMBEDDING_MODEL_NAME } from "./embedder.js";
import { vectorSearch, type VectorHit } from "./vectorSearch.js";
import { ftsSearch, type FtsHit } from "./ftsSearch.js";
import { rrf } from "./hybrid.js";
import { QueryCache } from "./cache.js";
import {
  buildContext,
  hasSufficientEvidence,
  type HydratedChunk,
} from "./contextBuilder.js";

export const NO_EVIDENCE_MESSAGE = "Nao encontrei base para responder";
export const SUPPORTED_MODES = ["semantic", "fts", "hybrid"] as const;
export type SearchMode = (typeof SUPPORTED_MODES)[number];

export interface Source {
  url: string;
  title: string;
  score: number;
}

export interface SearchResult {
  answer: string;
  sources: Source[];
}

export interface SearchOptions {
  mode?: SearchMode;
  topK?: number;
  baseDirOverride?: string;
}

/**
 * Resolve path da base RAG. Default: $DFE_AGENT_BASE_DIR ou ~/.dfe-agent.
 */
export function resolveBaseDir(override?: string): string {
  return override
    ?? process.env.DFE_AGENT_BASE_DIR
    ?? resolve(process.env.HOME ?? homedir() ?? tmpdir(), ".dfe-agent");
}

interface ChunkRow {
  chunk_id: number;
  doc_id: number;
  text: string;
  url: string;
  title: string;
}

function hydrateChunks(handle: Database.Database, hits: Array<{ chunk_id: number; doc_id: number; score: number }>): HydratedChunk[] {
  if (hits.length === 0) return [];
  const ids = hits.map((h) => h.chunk_id);
  const placeholders = ids.map(() => "?").join(",");
  const rows = handle
    .prepare(
      `SELECT c.id AS chunk_id, c.doc_id, c.text, d.url, d.title
         FROM chunks c
         JOIN documents d ON c.doc_id = d.id
        WHERE c.id IN (${placeholders})`,
    )
    .all(...ids) as ChunkRow[];
  const byId = new Map(rows.map((r) => [r.chunk_id, r]));
  return hits
    .map((h) => {
      const r = byId.get(h.chunk_id);
      if (!r) return null;
      return {
        chunk_id: r.chunk_id,
        doc_id: r.doc_id,
        text: r.text,
        url: r.url,
        title: r.title,
        score: h.score,
      } as HydratedChunk;
    })
    .filter((c): c is HydratedChunk => c !== null);
}

/**
 * Busca principal. Retorna {answer, sources[]} no contrato canonico.
 */
export async function search(
  question: string,
  opts: SearchOptions = {},
): Promise<SearchResult> {
  const mode: SearchMode = (opts.mode ?? "semantic") as SearchMode;
  const topK = opts.topK ?? 10;

  if (!SUPPORTED_MODES.includes(mode)) {
    throw new Error(`unsupported mode: ${mode}. Supported: ${SUPPORTED_MODES.join(", ")}`);
  }
  if (!question.trim()) {
    return { answer: NO_EVIDENCE_MESSAGE, sources: [] };
  }

  const dbPath = resolve(resolveBaseDir(opts.baseDirOverride), "dfe.db");
  const handle = new Database(dbPath, { readonly: true });

  try {
    // 1. Cache check
    const cache = new QueryCache(handle);
    let queryVec: Float32Array | null = null;
    if (mode !== "fts") {
      queryVec = cache.get(mode, question);
      if (!queryVec) {
        queryVec = await encode(question);
        cache.set(mode, question, queryVec);
      }
    }

    // 2. Buscar chunks
    let hits: Array<{ chunk_id: number; doc_id: number; score: number }> = [];

    if (mode === "semantic") {
      const vecHits: VectorHit[] = vectorSearch(handle, queryVec!, topK);
      // Converter distance (menor = melhor) em score (maior = melhor)
      hits = vecHits.map((h) => ({ ...h, score: 1 - h.distance }));
    } else if (mode === "fts") {
      const ftsHits: FtsHit[] = ftsSearch(handle, question, topK);
      // Converter bm25 (menor = melhor) em score (maior = melhor, normalizado 0-1)
      hits = ftsHits.map((h, i) => ({ ...h, score: 1 / (i + 1) }));
    } else {
      const vecHits = vectorSearch(handle, queryVec!, topK);
      const ftsHits = ftsSearch(handle, question, topK);
      const hybridHits = rrf(vecHits, ftsHits, topK);
      hits = hybridHits.map((h) => ({ ...h, score: h.score }));
    }

    // 3. Hidratar e montar contexto
    const hydrated = hydrateChunks(handle, hits);
    const ctx = buildContext(hydrated);
    return ctx;
  } finally {
    handle.close();
  }
}

export { EMBEDDING_MODEL_NAME };
export { hasSufficientEvidence };