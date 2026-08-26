/**
 * sync-assets.ts — copia .opencode/agent/dfe-agent.md e .opencode/skills/dfe-fiscal/
 * para packages/dfe-agent/dist/.
 *
 * Convencao (Sprint 14 B.3): fonte canonica mora no DFe-Agent root; copia
 * distribuida via este sync. Drift-check no CI via npm run drift-check.
 *
 * Uso:
 *   npm run sync          # copia source -> dist
 *   npm run drift-check   # verifica que dist == source
 *
 * Saida: exit 0 em sucesso, exit 1 em erro de I/O.
 */

import { cpSync, existsSync, mkdirSync, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const PKG_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const DFE_ROOT = resolve(PKG_ROOT, "../..");

interface SyncPair {
  src: string;
  dst: string;
  isDir: boolean;
}

const PAIRS: SyncPair[] = [
  {
    src: resolve(DFE_ROOT, ".opencode/agent/dfe-agent.md"),
    dst: resolve(PKG_ROOT, "dist/agent.md"),
    isDir: false,
  },
  {
    src: resolve(DFE_ROOT, ".opencode/skills/dfe-fiscal"),
    dst: resolve(PKG_ROOT, "dist/skill/dfe-fiscal"),
    isDir: true,
  },
];

function ensureExists(p: string, label: string): void {
  if (!existsSync(p)) {
    console.error(`[sync] ERRO: ${label} nao encontrado em ${p}`);
    process.exit(1);
  }
}

function syncOne(pair: SyncPair): void {
  ensureExists(pair.src, "source");
  mkdirSync(dirname(pair.dst), { recursive: true });
  if (pair.isDir) {
    cpSync(pair.src, pair.dst, { recursive: true });
  } else {
    cpSync(pair.src, pair.dst);
  }
  const size = statSync(pair.dst).size;
  console.info(`[sync] copied ${pair.src} -> ${pair.dst} (${size} bytes)`);
}

export function sync(): number {
  try {
    for (const pair of PAIRS) {
      syncOne(pair);
    }
    console.info("[sync] OK");
    return 0;
  } catch (err) {
    console.error(`[sync] ERRO: ${(err as Error).message}`);
    return 1;
  }
}

// Executa quando invocado diretamente (nao em import)
// npm run X -> argv = [node, tsx-cli, scripts/X.ts] (argv[2] endsWith X.ts)
// node --import tsx X.ts -> argv = [node, X.ts]         (argv[1] endsWith X.ts)
// tsx X.ts -> argv = [node, tsx-cli, X.ts]              (argv[2] endsWith X.ts)
// .some() cobre todas as variacoes (gate CI ubuntu+windows).
const invokedDirectly = process.argv.some(
  (a) => a.endsWith("sync-assets.ts") || a.endsWith("sync-assets.js"),
);
if (invokedDirectly) {
  process.exit(sync());
}