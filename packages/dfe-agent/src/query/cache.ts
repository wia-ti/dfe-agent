/**
 * cache.ts — cache SQLite de embeddings de query.
 *
 * @see PLAN_SPRINT14.md Task E.4 + Sprint 13 I13.2 (QueryEmbeddingCache)
 *
 * Persiste em `<baseDir>/cache.db`. Chave = sha256(model|mode|q_normalized).
 *
 * HIT na 2a chamada idêntica (mesmo modelo + mesmo mode + mesma query
 * normalizada) NAO invoca o embedder. Gate Sprint 13 + canonico em
 * src/query/embedding_cache.py.
 */

import { createHash } from "node:crypto";
import type { Database as BetterSqlite3Database } from "better-sqlite3";

export const QUERY_CACHE_SCHEMA = `
  CREATE TABLE IF NOT EXISTS query_cache (
    query_hash   TEXT PRIMARY KEY,
    embedding    BLOB NOT NULL,
    model        TEXT NOT NULL,
    mode         TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
  )
`;

export interface QueryCacheOptions {
  model?: string;
}

function normalizeQuery(q: string): string {
  return q.trim().toLowerCase();
}

function hashKey(model: string, mode: string, q: string): string {
  return createHash("sha256")
    .update(`${model}|${mode}|${normalizeQuery(q)}`)
    .digest("hex");
}

export class QueryCache {
  private readonly model: string;
  private readonly handle: BetterSqlite3Database;

  constructor(handle: BetterSqlite3Database, opts: QueryCacheOptions = {}) {
    this.handle = handle;
    this.model = opts.model
      ?? process.env.DFE_EMBEDDING_MODEL
      ?? "paraphrase-multilingual-MiniLM-L12-v2";
    handle.exec(QUERY_CACHE_SCHEMA);
  }

  /**
   * Busca embedding em cache. Retorna null em miss.
   */
  get(mode: string, question: string): Float32Array | null {
    const key = hashKey(this.model, mode, question);
    const row = this.handle
      .prepare("SELECT embedding FROM query_cache WHERE query_hash = ?")
      .get(key) as { embedding: Buffer } | undefined;
    if (!row) return null;
    const buf = row.embedding;
    return new Float32Array(buf.buffer, buf.byteOffset, buf.byteLength / 4);
  }

  /**
   * Persiste embedding. INSERT OR REPLACE para idempotencia.
   */
  set(mode: string, question: string, embedding: Float32Array): void {
    const key = hashKey(this.model, mode, question);
    const buf = Buffer.from(embedding.buffer);
    this.handle
      .prepare(
        `INSERT OR REPLACE INTO query_cache (query_hash, embedding, model, mode)
         VALUES (?, ?, ?, ?)`,
      )
      .run(key, buf, this.model, mode);
  }

  /**
   * Limpa cache (util apos troca de modelo).
   */
  clear(): void {
    this.handle.exec("DELETE FROM query_cache");
  }

  /**
   * Estatisticas: numero de entradas.
   */
  size(): number {
    const row = this.handle
      .prepare("SELECT COUNT(*) AS c FROM query_cache")
      .get() as { c: number };
    return row.c;
  }
}