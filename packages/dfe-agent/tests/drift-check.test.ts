import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const PKG_ROOT = process.cwd();
const DFE_ROOT = resolve(PKG_ROOT, "../..");

function sha(p: string): string {
  return createHash("sha256").update(readFileSync(p)).digest("hex");
}

test("drift-check.ts existe e expoe funcao driftCheck", () => {
  const scriptPath = resolve(PKG_ROOT, "scripts/drift-check.ts");
  assert.ok(existsSync(scriptPath), "scripts/drift-check.ts deve existir (Task B.2)");
  const src = readFileSync(scriptPath, "utf8");
  assert.match(src, /export function driftCheck|export.*function.*driftCheck/);
});

test("drift-check le source + dist e compara SHA-256", () => {
  const scriptPath = resolve(PKG_ROOT, "scripts/drift-check.ts");
  const src = readFileSync(scriptPath, "utf8");
  assert.match(src, /createHash|sha256/);
  // driftCheck() retorna 0/1; o entry point faz process.exit(driftCheck())
  assert.match(src, /return 1/);  // falha
  assert.match(src, /return 0/);  // sucesso
  assert.match(src, /process\.exit\(driftCheck\(\)\)/);
});

test("drift-check: source==dist -> exit 0", () => {
  const agentSrc = resolve(DFE_ROOT, ".opencode/agent/dfe-agent.md");
  const agentDst = resolve(PKG_ROOT, "dist/agent.md");
  const skillSrc = resolve(DFE_ROOT, ".opencode/skills/dfe-fiscal/SKILL.md");
  const skillDst = resolve(PKG_ROOT, "dist/skill/dfe-fiscal/SKILL.md");
  assert.equal(sha(agentSrc), sha(agentDst));
  assert.equal(sha(skillSrc), sha(skillDst));
});