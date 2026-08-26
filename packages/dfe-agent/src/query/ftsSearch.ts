/**
 * ftsSearch.ts — busca lexical via FTS5 (BM25).
 *
 * @see PLAN_SPRINT14.md Task E.2
 *
 * Estrategia:
 - saneamento da query (escape chars que quebram MATCH)
 - MATCH na tabela fts_chunks (BM25 nativo)
 - ORDER BY bm25(fts_chunks) LIMIT k
 *
 * BM25 score: menor = mais relevante (FTS5 inverte o sinal).
 */

import type { Database as BetterSqlite3Database } from "better-sqlite3";

export interface FtsHit {
  chunk_id: number;
  doc_id: number;
  score: number;
}

/**
 * Remove caracteres que quebram o MATCH do FTS5. Mantemos alfanumericos,
 * espacos e aspas (para phrase queries).
 */
function sanitizeQuery(q: string): string {
  return q
    .replace(/[^\w\s"]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Busca top-K chunks por BM25. Retorna hits ordenados do mais relevante
 * (menor score BM25) ao menos relevante.
 *
 * @param handle Better-sqlite3 handle (read-only)
 * @param query Query em linguagem natural
 * @param k Numero de hits
 */
export function ftsSearch(
  handle: BetterSqlite3Database,
  query: string,
  k: number,
): FtsHit[] {
  const ftsQuery = sanitizeQuery(query);
  if (!ftsQuery) return [];

  const rows = handle
    .prepare(
      `SELECT chunk_id, doc_id, bm25(fts_chunks) AS score
         FROM fts_chunks
        WHERE fts_chunks MATCH ?
        ORDER BY score
        LIMIT ?`,
    )
    .all(ftsQuery, k) as Array<{ chunk_id: number; doc_id: number; score: number }>;

  return rows.map((r) => ({
    chunk_id: r.chunk_id,
    doc_id: r.doc_id,
    score: r.score,
  }));
}