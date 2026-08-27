/**
 * cache.ts — cache SQLite de embeddings de query.
 *
 * @see PLAN_SPRINT14.md Task E.4 + Sprint 13 I13.2 (QueryEmbeddingCache)
 * @see Sprint 15 BUG-B: desacoplamento do handle do dfe.db (readonly).
 *
 * Persiste em `<baseDir>/cache.db` (canonico via `resolveCacheDbPath` em
 * `paths.ts`). Chave = sha256(model|mode|q_normalized).
 *
 * Ate' Sprint 14, QueryCache aceitava `handle` no construtor e escrevia
 * `CREATE TABLE IF NOT EXISTS` no mesmo handle aberto em `readonly: true`
 * por `query/index.ts`. Isso quebrava toda busca semantica/hibrida com
 * "attempt to write a readonly database" (SQLITE_READONLY).
 *
 * Fix Sprint 15: construtor agora recebe `baseDir: string` e abre SUA
 * PROPRIA conexao (read-write) em `<baseDir>/cache.db`, isolada do
 * dfe.db. `query/index.ts` passa `resolveBaseDir(opts.baseDirOverride)`.
 *
 * HIT na 2a chamada identica (mesmo modelo + mesmo mode + mesma query
 * normalizada) NAO invoca o embedder. Gate Sprint 13 + canonico em
 * src/query/embedding_cache.py do DFe-Agent root.
 */

import { createHash } from "node:crypto";
import { mkdirSync } from "node:fs";
import { dirname } from "node:path";
import Database, { type Database as BetterSqlite3Database } from "better-sqlite3";

import { resolveCacheDbPath } from "../paths.js";

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
  private readonly dbPath: string;

  /**
   * @param baseDir diretorio base (canonico vem de `paths.ts::resolveBaseDir`).
   *                O cache sera persistido em `<baseDir>/cache.db` (RW).
   * @param opts    opções (so `model` por enquanto; cai no env ou no default).
   */
  constructor(baseDir: string, opts: QueryCacheOptions = {}) {
    this.model = opts.model
      ?? process.env.DFE_EMBEDDING_MODEL
      ?? "paraphrase-multilingual-MiniLM-L12-v2";
    this.dbPath = resolveCacheDbPath(baseDir);
    // Garante que a pasta existe; better-sqlite3 falha se o path pai nao
    // existe quando o arquivo ainda nao foi criado.
    mkdirSync(dirname(this.dbPath), { recursive: true });
    // Conexao PROPRIA read-write, isolada do dfe.db (que pode estar readonly
    // durante `search()`). Cache NAO compartilha handle com a base principal.
    this.handle = new Database(this.dbPath);
    this.handle.exec(QUERY_CACHE_SCHEMA);
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
   * Fecha a conexao SQLite propria. Idempotente. Recomendado chamar no
   * teardown de testes/scripts para evitar o crash de cleanup do
   * better-sqlite3 nativo em Node 22/24 (`RemoveEnvironmentCleanupHook`).
   */
  close(): void {
    if (this.handle.open) {
      this.handle.close();
    }
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