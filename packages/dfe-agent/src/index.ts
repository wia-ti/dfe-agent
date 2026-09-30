// @wiati/dfe-agent — entry point
// Documentado em PLAN_SPRINT14.md Task A.1 (Sprint 14)

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

// A versao e' do semantic-release (Sprint 20): ele atualiza o package.json no
// release, entao lemos de la em vez de manter uma constante duplicada.
const PKG_JSON = resolve(dirname(fileURLToPath(import.meta.url)), "../package.json");

export const VERSION: string = (
  JSON.parse(readFileSync(PKG_JSON, "utf8")) as { version: string }
).version;
export const PACKAGE_NAME = "@wiati/dfe-agent";

export { runCli } from "./cli.js";
export { search } from "./query/index.js";
export { NO_EVIDENCE_MESSAGE } from "./query/index.js";
