import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const PKG_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

test("cli.ts existe e expoe runCli", () => {
  const cliPath = resolve(PKG_ROOT, "src/cli.ts");
  assert.ok(existsSync(cliPath));
  const src = readFileSync(cliPath, "utf8");
  assert.match(src, /export.*async function runCli/);
  assert.match(src, /parseArgs/);
  assert.match(src, /install.*update.*query.*status/);
});

test("commands/install.ts existe e expoe install()", () => {
  const p = resolve(PKG_ROOT, "src/commands/install.ts");
  assert.ok(existsSync(p));
  const src = readFileSync(p, "utf8");
  assert.match(src, /export function (install);
  // Deve copiar para .opencode/
  assert.match(src, /\.opencode\/agent\/dfe-agent\.md|\.opencode\\agent\\dfe-agent\.md/);
  assert.match(src, /\.opencode\/skills\/dfe-fiscal|\.opencode\\skills\\dfe-fiscal/);
});

test("dist/agent.md existe (pre-requisito para install copiar)", () => {
  // C.1 install copia dist/* para .opencode/. dist/* deve estar populado.
  const distAgent = resolve(PKG_ROOT, "dist/agent.md");
  assert.ok(existsSync(distAgent), "dist/agent.md deve existir (sincronizado via Fase B)");
  const distSkill = resolve(PKG_ROOT, "dist/skill/dfe-fiscal/SKILL.md");
  assert.ok(existsSync(distSkill));
});

test("USAGE em cli.ts documenta 4 subcommands", () => {
  const cliPath = resolve(PKG_ROOT, "src/cli.ts");
  const src = readFileSync(cliPath, "utf8");
  assert.match(src, /install/);
  assert.match(src, /update/);
  assert.match(src, /query/);
  assert.match(src, /status/);
});