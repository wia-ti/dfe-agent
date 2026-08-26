/**
 * commands/query.ts — busca semantica / FTS5 / hibrida na base RAG.
 *
 * @see PLAN_SPRINT14.md Task C.3 + Fase E
 *
 * Stub inicial: delega para query/index.ts (Fase E).
 */

import { search } from "../query/index.js";

export interface QueryOptions {
  question: string;
  mode?: string;
  json?: boolean;
}

export async function query(opts: QueryOptions): Promise<number> {
  const result = await search(opts.question, { mode: (opts.mode ?? "semantic") as any });
  console.log(JSON.stringify(result, null, 2));
  return 0;
}

if (import.meta.url === `file:///${process.argv[1]?.replace(/\\/g, "/")}`) {
  const q = process.argv.slice(2).join(" ").trim();
  query({ question: q }).then((code) => process.exit(code));
}