// @wiati/dfe-agent — entry point
// Documentado em PLAN_SPRINT14.md Task A.1 (Sprint 14)

export const VERSION = "0.1.5";
export const PACKAGE_NAME = "@wiati/dfe-agent";

export { runCli } from "./cli.js";
export { search } from "./query/index.js";
export { NO_EVIDENCE_MESSAGE } from "./query/index.js";