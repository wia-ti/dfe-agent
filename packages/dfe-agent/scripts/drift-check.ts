/**
 * drift-check.ts — verifica que packages/dfe-agent/dist/* == .opencode/* fonte
 * canonica. CI gate (B.2): PR com drift e' bloqueado.
 *
 * Uso:
 *   npm run drift-check
 *
 * Saida: exit 0 se identico, exit 1 se divergente + mensagem apontando o
 * proximo passo (`npm run sync`).
 */

import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const PKG_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const DFE_ROOT = resolve(PKG_ROOT, "../..");

interface DriftPair {
  src: string;
  dst: string;
  label: string;
}

const PAIRS: DriftPair[] = [
  {
    src: resolve(DFE_ROOT, ".opencode/agent/dfe-agent.md"),
    dst: resolve(PKG_ROOT, "dist/agent.md"),
    label: "agent.md",
  },
  {
    src: resolve(DFE_ROOT, ".opencode/skills/dfe-fiscal/SKILL.md"),
    dst: resolve(PKG_ROOT, "dist/skill/dfe-fiscal/SKILL.md"),
    label: "skill/dfe-fiscal/SKILL.md",
  },
];

function sha(p: string): string {
  return createHash("sha256").update(readFileSync(p)).digest("hex");
}

export function driftCheck(): number {
  const failures: string[] = [];

  for (const pair of PAIRS) {
    if (!existsSync(pair.src)) {
      console.error(`[drift] source ausente: ${pair.src}`);
      failures.push(pair.label);
      continue;
    }
    if (!existsSync(pair.dst)) {
      console.error(`[drift] dist ausente: ${pair.dst} (rode 'npm run sync')`);
      failures.push(pair.label);
      continue;
    }
    const srcSha = sha(pair.src);
    const dstSha = sha(pair.dst);
    if (srcSha !== dstSha) {
      console.error(
        `[drift] ${pair.label} divergente:\n` +
          `  source: ${pair.src} (sha=${srcSha.slice(0, 16)}...)\n` +
          `  dist:   ${pair.dst} (sha=${dstSha.slice(0, 16)}...)\n` +
          `  fix:    rode 'npm run sync' em packages/dfe-agent/`,
      );
      failures.push(pair.label);
    } else {
      console.info(`[drift] ${pair.label} OK (sha=${srcSha.slice(0, 16)}...)`);
    }
  }

  if (failures.length > 0) {
    console.error(`[drift] FAILED: ${failures.length} drift(s) detectado(s)`);
    return 1;
  }
  console.info("[drift] OK: nenhum drift detectado");
  return 0;
}

if (import.meta.url === `file:///${process.argv[1]?.replace(/\\/g, "/")}`) {
  process.exit(driftCheck());
}