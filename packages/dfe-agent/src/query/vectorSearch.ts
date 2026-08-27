/**
 * vectorSearch.ts — busca semantica via sqlite-vec (vec_chunks).
 *
 * @see PLAN_SPRINT14.md Task E.1
 *
 * Estrategia:
 - embedding da query (384-d, cosine-normalized)
 - MATCH na tabela virtual vec_chunks (cosine distance)
 - ORDER BY distance LIMIT k
 - dedup por doc_id (mantem o chunk mais proximo por documento)
 - boost temporal opcional (nao implementado aqui; ver E.5 contextBuilder)
 */

import type { Database as BetterSqlite3Database } from "better-sqlite3";
import * as sqliteVec from "sqlite-vec";

export interface VectorHit {
  chunk_id: number;
  doc_id: number;
  distance: number;
}

/**
 * Carrega extensao sqlite-vec no handle. Idempotente.
 */
export function loadVecExtension(handle: BetterSqlite3Database): void {
  sqliteVec.load(handle);
}

/**
 * Busca top-K chunks via cosine distance. Retorna hits ordenados do mais
 * similar (menor distance) ao menos similar.
 *
 * @param handle Better-sqlite3 handle aberto em modo readonly
 * @param query_vec Vetor 384-d da query (cosine-normalized)
 * @param k Numero de hits antes do dedup
 */
export function vectorSearch(
  handle: BetterSqlite3Database,
  query_vec: Float32Array,
  k: number,
): VectorHit[] {
  loadVecExtension(handle);

  // sqlite-vec usa serializacao nativa; precisamos passar Buffer
  const vecBuf = Buffer.from(query_vec.buffer);
  // Schema Py real (gate Sprint 16 Bug C): vec_chunks(document_id, chunk_index).
  // Aliases preservam a interface Node (chunk_id, doc_id) sem mudar a chamada externa.
  const rows = handle
    .prepare(
      `SELECT chunk_index AS chunk_id, document_id AS doc_id, distance
         FROM vec_chunks
        WHERE embedding MATCH ?
        ORDER BY distance
        LIMIT ?`,
    )
    .all(vecBuf, k) as Array<{ chunk_id: number; doc_id: number; distance: number }>;

  // Dedup por doc_id (mantem o primeiro = menor distance)
  const seen = new Set<number>();
  const deduped: VectorHit[] = [];
  for (const r of rows) {
    if (seen.has(r.doc_id)) continue;
    seen.add(r.doc_id);
    deduped.push({
      chunk_id: r.chunk_id,
      doc_id: r.doc_id,
      distance: r.distance,
    });
  }
  return deduped;
}