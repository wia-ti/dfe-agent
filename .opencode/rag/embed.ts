// .opencode/rag/embed.ts
// Le um arquivo .md gerado por summarize.ts, quebra em chunks, gera
// embeddings com all-MiniLM-L6-v2 e persiste em .opencode/rag/rag.db.
//
// Uso:
//   tsx .opencode/rag/embed.ts --file <path-do-md> [--agent <slug>] [--force]
//   tsx .opencode/rag/embed.ts --all         # processa tudo em .opencode/rag/knowledge/
//
// Comportamento:
//   - Idempotente por content_hash: se ja existe knowledge com mesmo
//     sha256(content), pula (a menos que --force).
//   - Persiste 1 linha em `knowledge` por categoria apos classificacao.
//   - Insere N embeddings em `vec_knowledge` (1 por chunk), com rowid = knowledge_id.
//     Para 1 knowledge com K chunks, sao criados K rows em vec_knowledge
//     (todos com o mesmo knowledge_id, mas rowids diferentes).
//
// Notas de schema:
//   - vec_knowledge.knowledge_id INTEGER PRIMARY KEY significa que o rowid da
//     tabela virtual segue o valor de knowledge_id. Como queremos N rows
//     para 1 knowledge (1 por chunk), nao usamos PRIMARY KEY aqui; usamos
//     INTEGER (sem PRIMARY KEY) para deixar o sqlite atribuir rowids proprios.
//   - A relacao knowledge <-> vec_knowledge eh via knowledge_id (sem FK).

import { readFileSync, readdirSync, existsSync, statSync } from "node:fs";
import { resolve, basename, relative } from "node:path";
import { createHash } from "node:crypto";
import { pathToFileURL } from "node:url";
import { openDb, ensureKnowledgeDir, DEFAULT_DB_PATH, KNOWLEDGE_DIR } from "./lib/db.ts";
import { chunkText } from "./lib/chunker.ts";
import { embedBatch } from "./lib/embedder.ts";
import {
  classifyMarkdown,
  CATEGORIES,
  type Category,
} from "./lib/classifier.ts";

interface CliArgs {
  file?: string;
  all: boolean;
  agent?: string;
  force: boolean;
  help: boolean;
}

function parseArgs(argv: string[]): CliArgs {
  const args: CliArgs = { all: false, force: false, help: false };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--file" || a === "-f") args.file = argv[++i];
    else if (a === "--all") args.all = true;
    else if (a === "--agent" || a === "-a") args.agent = argv[++i];
    else if (a === "--force") args.force = true;
    else if (a === "--help" || a === "-h") args.help = true;
  }
  return args;
}

function printHelp(): void {
  console.log(`embed.ts -- gera embeddings para arquivos .md de conhecimento

Uso:
  tsx .opencode/rag/embed.ts --file <path> [opcoes]
  tsx .opencode/rag/embed.ts --all

Opcoes:
  -f, --file <path>    processa um unico arquivo .md
      --all            processa todos os .md em .opencode/rag/knowledge/
  -a, --agent <slug>   sobrescreve o agent inferido do nome do arquivo
      --force          reprocessa mesmo que content_hash ja exista
  -h, --help           mostra esta ajuda
`);
}

function sha256(s: string): string {
  return createHash("sha256").update(s).digest("hex");
}

function agentFromFilename(filePath: string): string {
  const base = basename(filePath, ".md");
  const parts = base.split("-");
  if (parts.length >= 4 && /^\d{4}-\d{2}-\d{2}$/.test(parts.slice(0, 3).join("-"))) {
    return parts.slice(3).join("-");
  }
  return "session";
}

interface KnowledgeRow {
  id: number;
  path: string;
  category: string;
  agent: string;
  content: string;
}

function loadAllKnowledge(db: ReturnType<typeof openDb>): KnowledgeRow[] {
  return db
    .prepare("SELECT id, path, category, agent, content FROM knowledge")
    .all() as KnowledgeRow[];
}

function findByHash(
  db: ReturnType<typeof openDb>,
  hash: string,
  cache: Map<string, KnowledgeRow>,
): KnowledgeRow | undefined {
  if (cache.has(hash)) {
    return cache.get(hash);
  }
  const rows = loadAllKnowledge(db);
  cache.clear();
  for (const r of rows) {
    const h = sha256(r.content);
    cache.set(h, r);
  }
  return cache.get(hash);
}

interface InsertedRecord {
  knowledgeId: number;
  category: Category;
  chunks: number;
}

async function embedOneFile(
  filePath: string,
  agentOverride: string | undefined,
  force: boolean,
): Promise<InsertedRecord[]> {
  const db = openDb(DEFAULT_DB_PATH);
  const fullPath = resolve(filePath);
  const content = readFileSync(fullPath, "utf-8");
  const classified = classifyMarkdown(content);
  const agent = agentOverride ?? agentFromFilename(fullPath);
  const relPath = relative(process.cwd(), fullPath).replace(/\\/g, "/");

  const sectionsToEmbed = classified.filter(
    (c) => CATEGORIES.includes(c.category) && c.content.trim().length > 40,
  );

  if (sectionsToEmbed.length === 0) {
    process.stderr.write(`[embed] ${basename(filePath)}: nenhuma secao classificada, skip\n`);
    return [];
  }

  const hashCache: Map<string, KnowledgeRow> = new Map();
  loadAllKnowledge(db).forEach((r) => hashCache.set(sha256(r.content), r));

  const insertKnowledge = db.prepare(
    `INSERT INTO knowledge (path, content, category, agent, created_at)
     VALUES (?, ?, ?, ?, ?)`,
  );
  const insertVec = db.prepare(
    `INSERT INTO vec_knowledge (embedding, knowledge_id) VALUES (?, ?)`,
  );

  const inserted: InsertedRecord[] = [];
  const allTexts: string[] = [];
  const metadata: { knowledgeId: number; category: Category; textCount: number }[] = [];

  for (const section of sectionsToEmbed) {
    const hash = sha256(section.content);
    const existing = findByHash(db, hash, hashCache);
    if (existing && !force) {
      process.stderr.write(
        `[embed] skip (hash ja existe) cat=${section.category} id=${existing.id}\n`,
      );
      continue;
    }
    const createdAt = new Date().toISOString();
    const result = insertKnowledge.run(
      relPath,
      section.content,
      section.category,
      agent,
      createdAt,
    );
    const knowledgeId = Number(result.lastInsertRowid);
    const chunks = chunkText(section.content);
    if (chunks.length === 0) continue;
    metadata.push({ knowledgeId, category: section.category, textCount: chunks.length });
    for (const chunk of chunks) {
      allTexts.push(chunk.text);
    }
    inserted.push({ knowledgeId, category: section.category, chunks: chunks.length });
  }

  if (allTexts.length === 0) {
    return inserted;
  }

  const vectors = await embedBatch(allTexts);
  if (vectors.length !== allTexts.length) {
    throw new Error(
      `dim mismatch: ${vectors.length} vetores vs ${allTexts.length} textos`,
    );
  }

  const tx = db.transaction(() => {
    let cursor = 0;
    for (const m of metadata) {
      for (let i = 0; i < m.textCount; i++) {
        insertVec.run(vectors[cursor], BigInt(m.knowledgeId));
        cursor++;
      }
    }
  });
  tx();

  for (const r of inserted) {
    process.stderr.write(
      `[embed] +${r.chunks} chunks cat=${r.category} agent=${agent} id=${r.knowledgeId}\n`,
    );
  }
  return inserted;
}

export async function main(argv: string[] = process.argv): Promise<number> {
  const args = parseArgs(argv);
  if (args.help) {
    printHelp();
    return 0;
  }

  ensureKnowledgeDir();
  if (!args.file && !args.all) {
    console.error("[embed] ERRO: use --file <path> ou --all");
    return 2;
  }

  const files: string[] = [];
  if (args.all) {
    if (!existsSync(KNOWLEDGE_DIR)) {
      console.error(`[embed] ERRO: ${KNOWLEDGE_DIR} nao existe`);
      return 2;
    }
    for (const name of readdirSync(KNOWLEDGE_DIR)) {
      if (name.endsWith(".md")) files.push(resolve(KNOWLEDGE_DIR, name));
    }
  } else if (args.file) {
    if (!existsSync(args.file)) {
      console.error(`[embed] ERRO: arquivo nao encontrado ${args.file}`);
      return 2;
    }
    if (!statSync(args.file).isFile()) {
      console.error(`[embed] ERRO: nao eh arquivo ${args.file}`);
      return 2;
    }
    files.push(resolve(args.file));
  }

  if (files.length === 0) {
    console.error("[embed] nenhum arquivo .md para processar");
    return 1;
  }

  let totalChunks = 0;
  for (const f of files) {
    try {
      const r = await embedOneFile(f, args.agent, args.force);
      totalChunks += r.reduce((acc, x) => acc + x.chunks, 0);
    } catch (err) {
      console.error(`[embed] ERRO processando ${f}: ${(err as Error).message}`);
      return 1;
    }
  }
  process.stderr.write(
    `[embed] concluido: ${totalChunks} chunks inseridos em ${files.length} arquivo(s)\n`,
  );
  return 0;
}

if (import.meta.url === pathToFileURL(resolve(process.argv[1] ?? "")).href) {
  main().then(
    (code) => process.exit(code),
    (err) => {
      console.error(`[embed] erro fatal: ${err}`);
      process.exit(1);
    },
  );
}