// .opencode/rag/init_db.ts
// Inicializa o banco rag.db (cria diretorio + aplica schema).
// Idempotente -- pode ser rodado quantas vezes quiser.

import { pathToFileURL } from "node:url";
import { resolve } from "node:path";
import { openDb, ensureKnowledgeDir, DEFAULT_DB_PATH, KNOWLEDGE_DIR } from "./lib/db.ts";

export function main(): void {
  ensureKnowledgeDir();
  const db = openDb(DEFAULT_DB_PATH);
  const tables = db
    .prepare("SELECT name FROM sqlite_master WHERE type IN ('table') ORDER BY name")
    .all() as { name: string }[];
  process.stdout.write(`[init_db] DB pronto em ${DEFAULT_DB_PATH}\n`);
  process.stdout.write(`[init_db] Diretorio de conhecimento: ${KNOWLEDGE_DIR}\n`);
  process.stdout.write(`[init_db] Tabelas: ${tables.map((t) => t.name).join(", ")}\n`);
}

function isMain(): boolean {
  if (!process.argv[1]) return false;
  const scriptUrl = pathToFileURL(resolve(process.argv[1])).href;
  return import.meta.url === scriptUrl;
}

if (isMain()) {
  main();
}