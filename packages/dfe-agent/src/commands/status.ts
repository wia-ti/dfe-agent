/**
 * commands/status.ts — info da base instalada.
 *
 * @see PLAN_SPRINT14.md Task C.4
 */

import { existsSync, statSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { homedir, tmpdir } from "node:os";
import { fileURLToPath } from "node:url";

const PKG_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
import { VERSION } from "../index.js";

export interface StatusOptions {
  json?: boolean;
}

export async function status(opts: StatusOptions): Promise<number> {
  const baseDir = process.env.DFE_AGENT_BASE_DIR
    ?? process.env.HOME
    ?? homedir()
    ?? tmpdir();
  const dbPath = resolve(baseDir, "dfe.db");

  const info: Record<string, unknown> = {
    version: VERSION,
    packageName: "@wiati/dfe-agent",
    basePath: dbPath,
    baseExists: existsSync(dbPath),
  };

  if (info.baseExists) {
    const mtime = statSync(dbPath).mtime;
    info.baseMtime = mtime.toISOString();
    info.baseSizeBytes = statSync(dbPath).size;
    info.baseEmbeddingModel = process.env.DFE_EMBEDDING_MODEL
      ?? "paraphrase-multilingual-MiniLM-L12-v2";

    // Best-effort: contar docs (ESM: usa dynamic import; nunca `require`)
    try {
      const { default: Database } = await import("better-sqlite3");
      const handle = new Database(dbPath, { readonly: true });
      const row = handle.prepare("SELECT COUNT(*) as c FROM documents").get() as { c: number };
      info.baseDocCount = row.c;
      const uv = handle.prepare("PRAGMA user_version").get() as { user_version: number };
      info.baseSchemaVersion = uv.user_version;
      handle.close();
    } catch (err) {
      info.baseQueryError = (err as Error).message;
    }
  } else {
    info.hint = "rode 'dfe-agent update' para baixar a base";
  }

  console.log(JSON.stringify(info, null, 2));
  return 0;
}

const invokedDirectly =
  process.argv[1]?.endsWith("status.ts")
  || process.argv[1]?.endsWith("status.js");
if (invokedDirectly) {
  status({}).then(
    (code) => process.exit(code),
    (err) => {
      console.error(`[dfe-agent] erro fatal: ${(err as Error).message}`);
      process.exit(1);
    },
  );
}