// .opencode/rag/search.ts
// Recebe uma pergunta e o agent ativo, gera embedding da pergunta, busca
// top-3 chunks mais similares em vec_knowledge e prioriza chunks da mesma
// categoria inferida do agent.
//
// Uso:
//   tsx .opencode/rag/search.ts --query "<pergunta>" --agent <slug> [--top-k N]
//
// Saida:
//   JSON para stdout no formato:
//   {
//     "chunks": [
//       {
//         "knowledge_id": 7,
//         "category": "bug_root_cause",
//         "agent": "backend-engineer",
//         "path": ".opencode/rag/knowledge/2026-08-25-backend.md",
//         "snippet": "...trecho do chunk...",
//         "distance": 0.123,
//         "score": 0.877,
//         "category_match": true
//       }
//     ],
//     "context": "bloco markdown pronto para ser injetado em prompt"
//   }
//
// Politica de ranking:
//   1. Calcula distancia cosseno para todos os chunks.
//   2. Aplica boost +0.05 se category == agentToCategory(agent).
//   3. Ordena por (1 - distance) + boost desc, top-k.

import { embed } from "./lib/embedder.ts";
import { openDb, DEFAULT_DB_PATH } from "./lib/db.ts";
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";
import {
  agentToCategory,
  type Category,
  CATEGORIES,
} from "./lib/classifier.ts";

interface CliArgs {
  query: string;
  agent: string;
  topK: number;
  help: boolean;
  minScore: number;
}

function parseArgs(argv: string[]): CliArgs {
  const args: CliArgs = {
    query: "",
    agent: "session",
    topK: 3,
    minScore: 0.3,
    help: false,
  };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--query" || a === "-q") args.query = argv[++i];
    else if (a === "--agent" || a === "-a") args.agent = argv[++i];
    else if (a === "--top-k" || a === "-k") args.topK = Number(argv[++i]);
    else if (a === "--min-score") args.minScore = Number(argv[++i]);
    else if (a === "--help" || a === "-h") args.help = true;
  }
  return args;
}

function printHelp(): void {
  console.log(`search.ts -- busca top-K chunks de conhecimento similares a pergunta

Uso:
  tsx .opencode/rag/search.ts --query "<pergunta>" --agent <slug> [opcoes]

Opcoes:
  -q, --query <texto>   pergunta a buscar (obrigatorio)
  -a, --agent <slug>    agent ativo (para priorizacao de categoria)
  -k, --top-k <N>       numero de chunks a retornar (default: 3)
      --min-score <F>   score minimo (default: 0.3)
  -h, --help            mostra esta ajuda
`);
}

interface HitRow {
  rowid: number;
  distance: number;
  knowledge_id: number;
}

interface ChunkResult {
  knowledge_id: number;
  category: Category;
  agent: string;
  path: string;
  snippet: string;
  distance: number;
  score: number;
  category_match: boolean;
}

const CATEGORY_BOOST: number = 0.05;

export async function main(argv: string[] = process.argv): Promise<number> {
  const args = parseArgs(argv);
  if (args.help) {
    printHelp();
    return 0;
  }
  if (!args.query) {
    console.error("[search] ERRO: --query <texto> eh obrigatorio");
    return 2;
  }
  if (!Number.isFinite(args.topK) || args.topK < 1) {
    console.error("[search] ERRO: --top-k deve ser >= 1");
    return 2;
  }

  const db = openDb(DEFAULT_DB_PATH);
  const preferred = agentToCategory(args.agent);

  const vec = await embed(args.query);
  const rawRows = db
    .prepare(
      `SELECT rowid, distance, knowledge_id
         FROM vec_knowledge
        WHERE embedding MATCH ?
        ORDER BY distance
        LIMIT ?`,
    )
    .all(vec, args.topK * 4) as HitRow[];

  if (rawRows.length === 0) {
    const out = { chunks: [], context: "" };
    process.stdout.write(JSON.stringify(out, null, 2) + "\n");
    return 0;
  }

  const ids = [...new Set(rawRows.map((r) => r.knowledge_id))];
  const placeholders = ids.map(() => "?").join(",");
  const metaRows = db
    .prepare(
      `SELECT id, path, category, agent, content
         FROM knowledge
        WHERE id IN (${placeholders})`,
    )
    .all(...ids) as {
    id: number;
    path: string;
    category: Category;
    agent: string;
    content: string;
  }[];

  const metaById = new Map(metaRows.map((m) => [m.id, m]));

  const hits: ChunkResult[] = [];
  for (const r of rawRows) {
    const meta = metaById.get(r.knowledge_id);
    if (!meta) continue;
    const snippet = meta.content.slice(0, 240).replace(/\s+/g, " ").trim();
    const baseScore = 1 - r.distance;
    const catMatch = preferred !== null && meta.category === preferred;
    const score = baseScore + (catMatch ? CATEGORY_BOOST : 0);
    if (score < args.minScore && !catMatch) continue;
    hits.push({
      knowledge_id: r.knowledge_id,
      category: meta.category,
      agent: meta.agent,
      path: meta.path,
      snippet,
      distance: r.distance,
      score,
      category_match: catMatch,
    });
  }

  hits.sort((a, b) => b.score - a.score);
  const top = hits.slice(0, args.topK);

  const contextLines: string[] = [];
  for (const h of top) {
    const tag = h.category_match ? "★" : "·";
    contextLines.push(
      `[${tag} ${h.category} | ${h.agent} | ${h.path}]\n${h.snippet}`,
    );
  }
  const context = contextLines.join("\n\n---\n\n");

  const out = { chunks: top, context };
  process.stdout.write(JSON.stringify(out, null, 2) + "\n");
  return 0;
}

if (import.meta.url === pathToFileURL(resolve(process.argv[1] ?? "")).href) {
  main().then(
    (code) => process.exit(code),
    (err) => {
      console.error(`[search] erro fatal: ${err}`);
      process.exit(1);
    },
  );
}