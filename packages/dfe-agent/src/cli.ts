/**
 * cli.ts — entry point CLI para @wiati/dfe-agent.
 *
 * Subcommands:
 *   install   copia agent + skill para .opencode/ do projeto
 *   update    baixa base RAG do GitHub Releases
 *   query     busca semantica / FTS5 / hibrida na base
 *   status    info da base instalada (path, mtime, doc count)
 *
 * Exit codes:
 *   0  sucesso (incluindo NO_EVIDENCE_MESSAGE em `query`)
 *   1  erro generico / I/O
 *   2  argumentos invalidos
 *   3  base ausente / SHA mismatch em `update`
 *
 * @see PLAN_SPRINT14.md Task C.1
 */

import { parseArgs } from "node:util";
import { fileURLToPath } from "node:url";

const USAGE = `dfe-agent — agente opencode + base RAG de documentacao fiscal eletronica

Uso:
  dfe-agent install [--auto-setup]   copia agent + skill para .opencode/
  dfe-agent update                   baixa base RAG do GitHub Releases
  dfe-agent query "<pergunta>"       busca na base e retorna JSON {answer, sources[]}
  dfe-agent status                   info da base instalada
  dfe-agent --help                   imprime esta mensagem

Variaveis de ambiente:
  DFE_AGENT_BASE_DIR   path custom para base RAG (default: ~/.dfe-agent)
  NPM_CONFIG_REGISTRY  registry npm (para publicacao)
`;

export interface CliOptions {
  autoSetup?: boolean;
  json?: boolean;
  mode?: string;
  question?: string;
}

export async function runCli(argv: string[]): Promise<number> {
  // Lazy imports para evitar carregar modulos pesados (better-sqlite3) sem necessidade
  const { install } = await import("./commands/install.js");
  const { update } = await import("./commands/update.js");
  const { query } = await import("./commands/query.js");
  const { status } = await import("./commands/status.js");

  let parsed;
  try {
    parsed = parseArgs({
      args: argv,
      options: {
        auto: { type: "boolean", default: false },
        json: { type: "boolean", default: true },
        mode: { type: "string", default: "semantic" },
        help: { type: "boolean", short: "h", default: false },
        version: { type: "boolean", short: "v", default: false },
      },
      allowPositionals: true,
    });
  } catch (err) {
    console.error(`[dfe-agent] erro de argumentos: ${(err as Error).message}`);
    return 2;
  }

  const { values, positionals } = parsed;

  if (values.version) {
    const { VERSION } = await import("./index.js");
    console.log(VERSION);
    return 0;
  }

  if (values.help || positionals.length === 0) {
    console.log(USAGE);
    return 0;
  }

  const [cmd, ...rest] = positionals;

  switch (cmd) {
    case "install":
      return await install({ autoSetup: Boolean(values.auto) });

    case "update":
      return await update({});

    case "query": {
      const question = rest.join(" ").trim();
      if (!question) {
        console.error("[dfe-agent] query requer <pergunta>");
        return 2;
      }
      return await query({
        question,
        mode: String(values.mode ?? "semantic"),
        json: Boolean(values.json),
      });
    }

    case "status":
      return await status({ json: Boolean(values.json) });

    default:
      console.error(`[dfe-agent] comando desconhecido: ${cmd}`);
      console.error(USAGE);
      return 2;
  }
}

// Executa quando invocado diretamente como cli.ts OU cli.js (NÃO como binario
// dist/bin/dfe-agent.js — esse path tem seu proprio entry point).
// Comparacao exata via fileURLToPath evita heuristica fragil de endsWith.
const thisFile = fileURLToPath(import.meta.url);
const invokedDirectly =
  process.argv[1] === thisFile
  || process.argv[1]?.endsWith(`${thisFile.endsWith(".ts") ? "cli.ts" : "cli.js"}`);
if (invokedDirectly) {
  runCli(process.argv.slice(2)).then(
    (code) => process.exit(code),
    (err) => {
      console.error(`[dfe-agent] erro fatal: ${(err as Error).message}`);
      process.exit(1);
    },
  );
}