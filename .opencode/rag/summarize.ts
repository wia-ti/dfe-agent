// .opencode/rag/summarize.ts
// Recebe um transcript de agent ou de sessao e extrai aprendizados em
// 4 categorias, salvando um arquivo .md em .opencode/rag/knowledge/.
//
// Input:
//   --input <path>    caminho para arquivo de transcript (JSON Lines ou texto puro)
//   --agent <slug>    slug do agent (ex.: "backend-engineer") ou "session"
//   --date <YYYY-MM-DD> (opcional; default = hoje)
//   --stdout          imprime o markdown no stdout em vez de gravar em arquivo
//   --help
//
// Categorias:
//   - bug_root_cause        Bugs resolvidos com causa raiz
//   - architecture_decision Decisoes de arquitetura e o porquê
//   - team_pattern          Padroes adotados pelo time
//   - what_didnt_work       O que nao funcionou e por quê
//
// Estrategia de extracao:
//   1. Normaliza o transcript (extrai mensagens user/assistant se JSONL).
//   2. Quebra em paragrafos/blocos significativos.
//   3. Para cada bloco, classifica via lib/classifier.ts.
//   4. Agrupa por categoria e escreve o .md final.

import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { resolve, basename } from "node:path";
import { pathToFileURL } from "node:url";
import {
  CATEGORY_LABELS,
  CATEGORIES,
  classifySection,
  type Category,
} from "./lib/classifier.ts";
import { ensureKnowledgeDir } from "./lib/db.ts";

interface CliArgs {
  input?: string;
  agent: string;
  date: string;
  stdout: boolean;
  help: boolean;
}

function parseArgs(argv: string[]): CliArgs {
  const args: CliArgs = {
    agent: "session",
    date: new Date().toISOString().slice(0, 10),
    stdout: false,
    help: false,
  };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--input" || a === "-i") {
      args.input = argv[++i];
    } else if (a === "--agent" || a === "-a") {
      args.agent = argv[++i];
    } else if (a === "--date" || a === "-d") {
      args.date = argv[++i];
    } else if (a === "--stdout") {
      args.stdout = true;
    } else if (a === "--help" || a === "-h") {
      args.help = true;
    }
  }
  return args;
}

function printHelp(): void {
  console.log(`summarize.ts -- extrai aprendizados de transcript e salva .md

Uso:
  tsx .opencode/rag/summarize.ts --input <path> --agent <slug> [opcoes]

Opcoes:
  -i, --input <path>     caminho do transcript (texto puro ou JSONL)
  -a, --agent <slug>     slug do agent (default: "session")
  -d, --date <YYYY-MM-DD> data usada no nome do arquivo (default: hoje)
      --stdout           imprime markdown no stdout em vez de gravar
  -h, --help             mostra esta ajuda

Saida:
  Grava em .opencode/rag/knowledge/<date>-<agent>.md (a menos que --stdout)
  Tambem imprime o path do arquivo em stderr para o hook consumir.
`);
}

interface ParsedMessage {
  role: "user" | "assistant" | "tool" | "system" | "other";
  content: string;
}

function parseTranscript(raw: string): ParsedMessage[] {
  const trimmed = raw.trim();
  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    const messages: ParsedMessage[] = [];
    for (const line of trimmed.split(/\r?\n/)) {
      const l = line.trim();
      if (!l) continue;
      try {
        const obj = JSON.parse(l);
        const role = (obj.role ?? obj.type ?? "other") as string;
        let content = "";
        if (typeof obj.content === "string") {
          content = obj.content;
        } else if (Array.isArray(obj.content)) {
          content = obj.content
            .map((c: { text?: string; content?: string }) => c.text ?? c.content ?? "")
            .join("\n");
        } else if (typeof obj.message === "string") {
          content = obj.message;
        } else if (typeof obj.text === "string") {
          content = obj.text;
        }
        messages.push({
          role: (["user", "assistant", "tool", "system"].includes(role)
            ? role
            : "other") as ParsedMessage["role"],
          content,
        });
      } catch {
        messages.push({ role: "other", content: l });
      }
    }
    return messages;
  }
  return [{ role: "other", content: trimmed }];
}

function isSignificantBlock(text: string): boolean {
  const t = text.trim();
  if (t.length < 40) return false;
  const letterRatio = (t.match(/[A-Za-zÀ-ÿ]/g) ?? []).length / t.length;
  if (letterRatio < 0.4) return false;
  if (/^```[\s\S]*```$/.test(t)) return false;
  return true;
}

function extractBlocks(messages: ParsedMessage[]): { role: string; text: string }[] {
  const blocks: { role: string; text: string }[] = [];
  for (const m of messages) {
    if (m.role === "tool" || m.role === "system") continue;
    const paras = m.content.split(/\n\s*\n/);
    for (const p of paras) {
      const t = p.trim();
      if (isSignificantBlock(t)) {
        blocks.push({ role: m.role, text: t });
      }
    }
  }
  return blocks;
}

function buildMarkdown(blocks: { role: string; text: string }[], agent: string, date: string): string {
  const byCategory: Record<Category, string[]> = {
    bug_root_cause: [],
    architecture_decision: [],
    team_pattern: [],
    what_didnt_work: [],
  };

  for (const block of blocks) {
    const category = classifySection(block.text);
    byCategory[category].push(block.text);
  }

  const usedCategories = CATEGORIES.filter((c) => byCategory[c].length > 0);
  const lines: string[] = [];
  lines.push(`# Aprendizados -- ${agent} -- ${date}`);
  lines.push("");
  lines.push(`> Extraido automaticamente de transcript via .opencode/rag/summarize.ts`);
  lines.push(`> Total de blocos significativos: ${blocks.length}`);
  lines.push(`> Categorias cobertas: ${usedCategories.length}/${CATEGORIES.length}`);
  lines.push("");

  for (const cat of CATEGORIES) {
    const items = byCategory[cat];
    lines.push(`## ${CATEGORY_LABELS[cat]}`);
    lines.push("");
    if (items.length === 0) {
      lines.push("_Nenhum aprendizado desta categoria no transcript._");
      lines.push("");
      continue;
    }
    for (const item of items) {
      const cleaned = item.replace(/\n+/g, " ").trim();
      lines.push(`- ${cleaned}`);
    }
    lines.push("");
  }

  return lines.join("\n");
}

function deriveOutputPath(date: string, agent: string): string {
  const safeAgent = agent
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return resolve(
    process.cwd(),
    ".opencode",
    "rag",
    "knowledge",
    `${date}-${safeAgent || "session"}.md`,
  );
}

export function main(argv: string[] = process.argv): number {
  const args = parseArgs(argv);
  if (args.help) {
    printHelp();
    return 0;
  }
  if (!args.input) {
    console.error("[summarize] ERRO: --input <path> eh obrigatorio (ou use --help)");
    return 2;
  }
  if (!existsSync(args.input)) {
    console.error(`[summarize] ERRO: arquivo nao encontrado: ${args.input}`);
    return 2;
  }

  ensureKnowledgeDir();
  const raw = readFileSync(args.input, "utf-8");
  const messages = parseTranscript(raw);
  const blocks = extractBlocks(messages);
  if (blocks.length === 0) {
    console.error(`[summarize] AVISO: nenhum bloco significativo em ${basename(args.input)}`);
    return 1;
  }
  const md = buildMarkdown(blocks, args.agent, args.date);

  if (args.stdout) {
    process.stdout.write(md);
    return 0;
  }

  const outPath = deriveOutputPath(args.date, args.agent);
  writeFileSync(outPath, md, "utf-8");
  process.stderr.write(`[summarize] gravou ${blocks.length} blocos em ${outPath}\n`);
  process.stdout.write(outPath + "\n");
  return 0;
}

if (import.meta.url === pathToFileURL(resolve(process.argv[1] ?? "")).href) {
  process.exit(main());
}