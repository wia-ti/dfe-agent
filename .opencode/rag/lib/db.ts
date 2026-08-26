// .opencode/rag/lib/db.ts
// Wrapper de conexao SQLite + sqlite-vec para o RAG meta-cognitivo.
// Carrega a extensao sqlite-vec em cada conexao (necessario para vec0).
//
// API sqlite-vec em better-sqlite3 (vide examples/simple-node do upstream):
//   - CREATE VIRTUAL TABLE vec_x USING vec0(embedding float[384], ...)
//   - INSERT com Float32Array como segundo param
//   - SELECT ... WHERE embedding MATCH ? (Float32Array) ORDER BY distance LIMIT k

import Database from "better-sqlite3";
import * as sqliteVec from "sqlite-vec";
import { readFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

export const DEFAULT_DB_PATH: string = resolve(
  __dirname,
  "..",
  "rag.db",
);

export const SCHEMA_PATH: string = resolve(__dirname, "..", "schema.sql");

export const KNOWLEDGE_DIR: string = resolve(
  __dirname,
  "..",
  "knowledge",
);

export const VEC_DIM: number = 384;

let cachedDb: Database.Database | null = null;

export function openDb(dbPath: string = DEFAULT_DB_PATH): Database.Database {
  if (cachedDb && cachedDb.name === dbPath) {
    return cachedDb;
  }
  if (cachedDb) {
    cachedDb.close();
    cachedDb = null;
  }

  const parentDir = dirname(dbPath);
  if (!existsSync(parentDir)) {
    mkdirSync(parentDir, { recursive: true });
  }

  const db = new Database(dbPath);
  db.pragma("journal_mode = WAL");
  db.pragma("synchronous = NORMAL");
  db.pragma("foreign_keys = ON");

  sqliteVec.load(db);
  initSchema(db);

  cachedDb = db;
  return db;
}

export function initSchema(db: Database.Database): void {
  const sql = readFileSync(SCHEMA_PATH, "utf-8");
  db.exec(sql);
}

export function ensureKnowledgeDir(): void {
  if (!existsSync(KNOWLEDGE_DIR)) {
    mkdirSync(KNOWLEDGE_DIR, { recursive: true });
  }
}

export function closeDb(): void {
  if (cachedDb) {
    cachedDb.close();
    cachedDb = null;
  }
}