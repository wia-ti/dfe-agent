/**
 * paths.ts — centraliza todos os resolves de paths do pacote.
 *
 * Sprint 15 / bug dfe-agent-runtime-path-and-cache.
 *
 * Ate' Sprint 14, dois bugs coexistiam porque a regra D4 do design doc
 * ("Base no consumidor: ~/.dfe-agent/dfe.db + override DFE_AGENT_BASE_DIR")
 * estava duplicada em 3 funcoes locais em arquivos diferentes, e cada
 * uma implementava de um jeito:
 *
 *   src/query/index.ts:64-68   -> CORRETO (resolve(..., ".dfe-agent"))
 *   src/commands/update.ts:47-52  -> ERRADO (esquece ".dfe-agent")
 *   src/commands/status.ts:20-24  -> ERRADO (mesmo)
 *
 * Sintoma: `npx dfe-agent update && npx dfe-agent query` end-to-end quebrava
 * com "Cannot open database because the directory does not exist" porque
 * cada comando apontava para um path diferente. CI passou porque nao ha
 * teste E2E (apenas tests/cli/skeleton.test.ts 100% estrutural).
 *
 * Este arquivo e' a fonte UNICA de verdade para resolver:
 *   resolveBaseDir()       -> ~/.dfe-agent (ou override)
 *   resolveDbPath()        -> <baseDir>/dfe.db
 *   resolveCacheDbPath()   -> <baseDir>/cache.db (Sprint 15 FIX Bug B)
 *
 * Bug B (cache acoplado ao handle do dfe.db readonly): QueryCache agora
 * aceita `baseDir: string` e abre SUA PROPRIA conexao em resolveCacheDbPath().
 * Justificativa: o dfe.db e' aberto com readonly: true em search(); query
 * cache precisa de RW; misturar os dois = "attempt to write a readonly db".
 *
 * @see PLAN_SPRINT14.md D4 (decisao ~/.dfe-agent)
 * @see AGENTS.md "Decisoes resolvidas (Sprint 14)" FOLLOW-UPS (geral;
 *      bugs A e B nao foram catalogados em v0.1.0 mas seguem o mesmo
 *      pattern de drift Py/Node documentado na Sprint 14 D.4 + D.7)
 * @see .opencode/rag/knowledge/2026-08-26-dev-sprint14-npm-package.md:21
 */

import { resolve } from "node:path";
import { homedir } from "node:os";

/**
 * Resolve o diretorio base onde o pacote persiste dados.
 *
 * Precedencia (gate D4):
 *   1. `baseDirOverride` explicito (injetado por testes; UNICO caminho que
 *      bypassa env + HOME).
 *   2. $DFE_AGENT_BASE_DIR (env var).
 *   3. $HOME (Unix) ou $USERPROFILE (Windows) ou `os.homedir()`. Sempre
 *      resolve para `<home>/.dfe-agent`. No Windows, `os.homedir()` consulta
 *      `process.env.USERPROFILE` internamente, entao o fallback explicito a
 *      `homedir()` cobre os 2 SOs sem branch.
 *
 * @param baseDirOverride - path custom para testes (UNICO jeito de bypassar env).
 *                       NUNCA bate em disco automaticamente: o caller decide criar.
 */
export function resolveBaseDir(baseDirOverride?: string): string {
  if (baseDirOverride) return baseDirOverride;
  if (process.env.DFE_AGENT_BASE_DIR) return process.env.DFE_AGENT_BASE_DIR;
  // `os.homedir()` nunca retorna string vazia (consulta USERPROFILE no Windows
  // e passwd no Unix); caimos nele para evitar o dead-code `?? tmpdir()`.
  const home = process.env.HOME ?? process.env.USERPROFILE ?? homedir();
  return resolve(home, ".dfe-agent");
}

/**
 * Path canonico do dfe.db (base RAG principal, read-only em runtime).
 */
export function resolveDbPath(baseDirOverride?: string): string {
  return resolve(resolveBaseDir(baseDirOverride), "dfe.db");
}

/**
 * Path canonico do cache.db (query embedding cache, read-write em runtime).
 * Separado do dfe.db por design Bug B Sprint 15: o cache NAO pode
 * compartilhar o handle readonly de search().
 */
export function resolveCacheDbPath(baseDirOverride?: string): string {
  return resolve(resolveBaseDir(baseDirOverride), "cache.db");
}
