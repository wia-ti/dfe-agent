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

import Database, {
  type Database as BetterSqlite3Database,
} from "better-sqlite3";

import { resolveBaseDir, resolveDbPath } from "../paths.js";
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
import {
  NO_EVIDENCE_MESSAGE,
  SUPPORTED_MODES,
  DEFAULT_TOP_K,
  MIN_RELEVANCE_SCORE,
  RECENCY_WEIGHT,
  RECENCY_HALF_LIFE_DAYS,
  type SearchMode,
} from "./constants.js";

// Re-exports para manter compat: callers antigos podem importar
// `resolveBaseDir` de `query/index.ts` como antes. A fonte unica da
// verdade eh `paths.ts` (gate Sprint 15 BUG-A).
export { resolveBaseDir } from "../paths.js";
export { NO_EVIDENCE_MESSAGE, SUPPORTED_MODES, DEFAULT_TOP_K };
export type { SearchMode };

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
 * Recency boost (gate paridade com Py `src/query/query_engine.py:34-36`).
 *
 * Decaimento exponencial: doc recente (now) -> 1.0; doc com idade = half_life
 * -> 0.5; doc 2x half_life -> 0.25; etc. Doc sem published_at -> 0.5 (neutro).
 */
function recencyScore(publishedAt: string | null, now: number = Date.now()): number {
  if (!publishedAt) return 0.5;
  const ts = Date.parse(publishedAt);
  if (Number.isNaN(ts)) return 0.5;
  const ageDays = (now - ts) / 86_400_000;
  return Math.pow(0.5, ageDays / RECENCY_HALF_LIFE_DAYS);
}

/**
 * Combina score (semantico/fts/rrf) com recencia via peso RECENCY_WEIGHT.
 * Espelha Py `_apply_recency_and_topk` em query_engine.py:288-291.
 */
function applyRecency(score: number, publishedAt: string | null): number {
  const rec = recencyScore(publishedAt);
  return (1 - RECENCY_WEIGHT) * score + RECENCY_WEIGHT * rec;
}

/**
 * Hidrata hits com texto + metadados do documento. Gate Sprint 16 Bug C:
 * usa `vec_chunks` (chave composta document_id/chunk_index) e JOIN em
 * `documents` por `document_id` — schema Py real. A tabela `chunks` antiga
 * nao existe mais desde Sprint 12 (foi substituida por vec_chunks + sidecar
 * chunk_metadata).
 *
 * Exportado para testes (tests/query/index.test.ts). NAO re-exportar em
 * src/index.ts — helper interno.
 */
export function hydrateChunks(
  handle: BetterSqlite3Database,
  hits: Array<{ chunk_id: number; doc_id: number; score: number }>,
): HydratedChunk[] {
  if (hits.length === 0) return [];
  // Tuplas WHERE IN: cada hit vira (?,?) para (document_id, chunk_index).
  const tuples = hits.map(() => "(?,?)").join(",");
  const params = hits.flatMap((h) => [h.doc_id, h.chunk_id]);
  const rows = handle
    .prepare(
      `SELECT vc.document_id,
              vc.chunk_index,
              vc.text,
              d.url,
              d.title,
              d.published_at
         FROM vec_chunks vc
         JOIN documents d ON d.id = vc.document_id
        WHERE (vc.document_id, vc.chunk_index) IN (${tuples})`,
    )
    .all(...params) as Array<{
      document_id: number;
      chunk_index: number;
      text: string;
      url: string;
      title: string;
      published_at: string | null;
    }>;
  // Indexar por (doc_id, chunk_id) — chave composta de hydrateChunks.
  const byKey = new Map<string, (typeof rows)[number]>(
    rows.map((r) => [`${r.document_id}:${r.chunk_index}`, r]),
  );
  return hits
    .map((h): HydratedChunk | null => {
      const r = byKey.get(`${h.doc_id}:${h.chunk_id}`);
      if (!r) return null;
      return {
        chunk_id: h.chunk_id,
        doc_id: h.doc_id,
        text: r.text,
        url: r.url,
        title: r.title,
        published_at: r.published_at,
        score: h.score,
      };
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
  const topK = opts.topK ?? DEFAULT_TOP_K;

  if (!SUPPORTED_MODES.includes(mode)) {
    throw new Error(`unsupported mode: ${mode}. Supported: ${SUPPORTED_MODES.join(", ")}`);
  }
  if (!question.trim()) {
    return { answer: NO_EVIDENCE_MESSAGE, sources: [] };
  }

  const dbPath = resolveDbPath(opts.baseDirOverride);
  const handle = new Database(dbPath, { readonly: true });

  try {
    // 1. Cache check
    // Bug B Sprint 15: cache abre SUA PROPRIA conexao em <baseDir>/cache.db
    // (read-write), isolada do dfe.db (read-only).
    const cache = new QueryCache(resolveBaseDir(opts.baseDirOverride));
    let queryVec: Float32Array | null = null;
    if (mode !== "fts") {
      queryVec = cache.get(mode, question);
      if (!queryVec) {
        queryVec = await encode(question);
        cache.set(mode, question, queryVec);
      }
    }

    // 2. Buscar chunks (score pre-recency)
    let hits: Array<{ chunk_id: number; doc_id: number; score: number }> = [];

    if (mode === "semantic") {
      const vecHits: VectorHit[] = vectorSearch(handle, queryVec!, topK);
      // Converter distance (menor = melhor) em score (maior = melhor)
      hits = vecHits.map((h) => ({ ...h, score: 1 - h.distance }));
    } else if (mode === "fts") {
      // FTS5 retorna bm25 (menor = mais relevante); normalizamos para score
      // crescente via 1/(1+bm25_normalized). Para paridade com Py, mantemos
      // bm25 relativo (bm25 do chunk / -bm25_max).
      const ftsHits: FtsHit[] = ftsSearch(handle, question, topK);
      // FTS5 bm25() retorna score NEGATIVO (menor = melhor); invertemos.
      // Exemplo: bm25 = -2.5 (bom) -> score = 2.5; bm25 = -0.5 (ruim) -> score = 0.5.
      hits = ftsHits.map((h) => ({ ...h, score: -h.score }));
    } else {
      const vecHits = vectorSearch(handle, queryVec!, topK);
      const ftsHits = ftsSearch(handle, question, topK);
      const hybridHits = rrf(vecHits, ftsHits, topK);
      hits = hybridHits.map((h) => ({ ...h, score: h.score }));
    }

    // 3. Hidratar (precisa de published_at para recency)
    const hydrated = hydrateChunks(handle, hits);

    // 4. Aplicar recency boost (gate paridade Py query_engine.py:288-291)
    for (const c of hydrated) {
      c.score = applyRecency(c.score, c.published_at ?? null);
    }

    // 5. Re-ordenar por score final (recency-adjusted)
    hydrated.sort((a, b) => b.score - a.score);

    // 6. Cortar para top-K final
    const topKFinal = hydrated.slice(0, topK);

    // 7. Montar contexto
    return buildContext(topKFinal);
  } finally {
    handle.close();
  }
}

export { EMBEDDING_MODEL_NAME, MIN_RELEVANCE_SCORE };
export { hasSufficientEvidence };