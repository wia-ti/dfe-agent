// .opencode/rag/smoke_test.ts
// Smoke test do sistema de RAG meta-cognitivo:
//   1. inicializa o banco
//   2. gera um transcript fake
//   3. roda summarize -> embed -> search
//   4. verifica que top-K >= 1 e que o JSON de saida tem o formato esperado

import { writeFileSync, mkdtempSync, rmSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve, join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const __filename: string = fileURLToPath(import.meta.url);
const __dirname: string = dirname(__filename);

const PROJECT_ROOT: string = resolve(__dirname, "..", "..");
const TSX_BIN: string = process.platform === "win32"
  ? join(PROJECT_ROOT, ".opencode", "node_modules", ".bin", "tsx.cmd")
  : join(PROJECT_ROOT, ".opencode", "node_modules", ".bin", "tsx");

interface SearchHit {
  knowledge_id: number;
  category: string;
  agent: string;
  path: string;
  snippet: string;
  distance: number;
  score: number;
  category_match: boolean;
}

interface SearchOutput {
  chunks: SearchHit[];
  context: string;
}

interface RunResult {
  code: number;
  stdout: string;
  stderr: string;
}

function quoteIfNeeded(arg: string): string {
  if (/[\s"#&|^()<>]/g.test(arg)) {
    return `"${arg.replace(/"/g, '\\"')}"`;
  }
  return arg;
}

function run(label: string, cmd: string, args: string[]): RunResult {
  process.stderr.write(`>>> ${label}\n`);

  if (process.platform === "win32") {
    const quotedArgs = args.map(quoteIfNeeded).join(" ");
    const fullCommand = `"${cmd}" ${quotedArgs}`;
    const result = spawnSync(fullCommand, [], {
      cwd: PROJECT_ROOT,
      encoding: "utf-8",
      env: { ...process.env, FORCE_COLOR: "0" },
      shell: true,
      windowsHide: true,
    });
    if (result.stdout) process.stderr.write(`[stdout]\n${result.stdout}\n`);
    if (result.stderr) process.stderr.write(`[stderr]\n${result.stderr}\n`);
    if (result.error) process.stderr.write(`[error] ${result.error.message}\n`);
    return {
      code: result.status ?? 1,
      stdout: result.stdout ?? "",
      stderr: result.stderr ?? "",
    };
  }

  const result = spawnSync(cmd, args, {
    cwd: PROJECT_ROOT,
    encoding: "utf-8",
    env: { ...process.env, FORCE_COLOR: "0" },
    shell: false,
  });
  if (result.stdout) process.stderr.write(`[stdout]\n${result.stdout}\n`);
  if (result.stderr) process.stderr.write(`[stderr]\n${result.stderr}\n`);
  if (result.error) process.stderr.write(`[error] ${result.error.message}\n`);
  return {
    code: result.status ?? 1,
    stdout: result.stdout ?? "",
    stderr: result.stderr ?? "",
  };
}

function expect(cond: boolean, msg: string): void {
  if (!cond) {
    console.error(`[smoke_test] FALHA: ${msg}`);
    process.exit(1);
  }
  process.stderr.write(`[ok] ${msg}\n`);
}

async function main(): Promise<void> {
  const tmp = mkdtempSync(join(tmpdir(), "dfe-rag-smoke-"));
  const transcriptPath = resolve(tmp, "transcript.txt");
  const mdPath = resolve(join(PROJECT_ROOT, ".opencode", "rag", "knowledge"));
  if (!existsSync(mdPath)) {
    process.stderr.write(`[smoke_test] criando ${mdPath}\n`);
  }

  const transcript = `

User: Como cancelar uma NF-e apos o prazo?

Assistant: Resposta: NAO inventar informacao. Consultar NT 2019.001.

User: O agent backend-engineer decidiu usar SQLite com sqlite-vec porque o ecossistema Python ja tem bindings estaveis e nao queremos dependencia adicional de Postgres. Trade-off: para escala >100k vetores seria melhor pgvector, mas para o caso atual (algumas centenas) eh suficiente.

User: Padrao do time: sempre rodar pytest tests/ antes de commit. NUNCA commitar com testes falhando.

User: Tentamos usar FAISS puro mas a manutencao do C++ binding quebrou em Windows. Abandonamos e voltamos para sqlite-vec, mais simples e sem dependencia nativa alem do SQLite.

`;

  writeFileSync(transcriptPath, transcript, "utf-8");

  const date = "2026-08-25";

  const sum = run("summarize", TSX_BIN, [
    ".opencode/rag/summarize.ts",
    "--input", transcriptPath,
    "--agent", "smoke-agent",
    "--date", date,
  ]);
  expect(sum.code === 0, `summarize retornou codigo ${sum.code}`);

  const mdFile = join(mdPath, `${date}-smoke-agent.md`);
  expect(existsSync(mdFile), `arquivo ${mdFile} foi criado`);

  const emb = run("embed", TSX_BIN, [
    ".opencode/rag/embed.ts",
    "--file", mdFile,
  ]);
  expect(emb.code === 0, `embed retornou codigo ${emb.code}`);

  const srch = run("search", TSX_BIN, [
    ".opencode/rag/search.ts",
    "--query", "como cancelar nota fiscal apos prazo",
    "--agent", "backend-engineer",
    "--top-k", "3",
  ]);
  expect(srch.code === 0, `search retornou codigo ${srch.code}`);

  let parsed: SearchOutput;
  try {
    parsed = JSON.parse(srch.stdout) as SearchOutput;
  } catch {
    console.error(`[smoke_test] stdout nao eh JSON: ${srch.stdout}`);
    process.exit(1);
  }
  expect(Array.isArray(parsed.chunks), "campo chunks eh array");
  expect(
    parsed.chunks.length >= 1,
    `pelo menos 1 chunk retornado (foi ${parsed.chunks.length})`,
  );
  expect(parsed.context.length > 0, "campo context nao vazio");
  expect(
    parsed.chunks.every((c) =>
      ["bug_root_cause", "architecture_decision", "team_pattern", "what_didnt_work"].includes(
        c.category,
      ),
    ),
    "todas as categorias sao validas",
  );

  rmSync(tmp, { recursive: true, force: true });
  process.stderr.write("[smoke_test] OK -- sistema funcional end-to-end\n");
}

main().catch((err) => {
  console.error(`[smoke_test] erro fatal: ${err}`);
  process.exit(1);
});