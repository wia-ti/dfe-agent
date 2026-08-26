/**
 * commands/install.ts — copia agent + skill de dist/ para .opencode/ do projeto.
 *
 * @see PLAN_SPRINT14.md Task C.1
 *
 * Origem (read-only):
 *   <pkg>/dist/agent.md
 *   <pkg>/dist/skill/dfe-fiscal/
 *
 * Destino (escrita):
 *   <cwd>/.opencode/agent/dfe-agent.md
 *   <cwd>/.opencode/skills/dfe-fiscal/
 *
 * Exit codes:
 *   0  sucesso
 *   1  erro de I/O
 *   2  target invalido (sem permissao de escrita)
 */

import { cpSync, existsSync, mkdirSync, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const PKG_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

export interface InstallOptions {
  autoSetup?: boolean;
}

export function install(opts: InstallOptions): number {
  const target = resolve(process.cwd(), ".opencode");
  const targetAgent = `${target}/agent/dfe-agent.md`;
  const targetSkill = `${target}/skills/dfe-fiscal`;

  // 1. Validar source (dist/)
  const srcAgent = resolve(PKG_ROOT, "dist/agent.md");
  const srcSkill = resolve(PKG_ROOT, "dist/skill/dfe-fiscal");

  if (!existsSync(srcAgent)) {
    console.error(
      `[dfe-agent] dist/agent.md nao encontrado em ${srcAgent}.\n` +
        `[dfe-agent] isto indica que 'npm run sync' nao foi rodado antes do build.\n` +
        `[dfe-agent] se voce instalou via npm install, isso e' um bug do pacote — reporte em https://github.com/dfe-agent/DFe-Agent/issues`,
    );
    return 1;
  }
  if (!existsSync(srcSkill)) {
    console.error(`[dfe-agent] dist/skill/dfe-fiscal nao encontrado em ${srcSkill}`);
    return 1;
  }

  // 2. Criar target dir
  try {
    mkdirSync(`${target}/agent`, { recursive: true });
    mkdirSync(`${target}/skills/dfe-fiscal`, { recursive: true });
  } catch (err) {
    console.error(`[dfe-agent] nao foi possivel criar ${target}: ${(err as Error).message}`);
    return 2;
  }

  // 3. Copiar (sobrescreve sem warning — design B.1)
  cpSync(srcAgent, targetAgent);
  const agentSize = statSync(targetAgent).size;
  console.info(`[dfe-agent] copied agent -> ${targetAgent} (${agentSize} bytes)`);

  cpSync(srcSkill, targetSkill, { recursive: true });
  console.info(`[dfe-agent] copied skill -> ${targetSkill}`);

  // 4. Se --auto-setup, dispara update em sequencia
  if (opts.autoSetup) {
    console.info("[dfe-agent] --auto-setup acionado, disparando update...");
    // dynamic import para evitar ciclo
    return import("./update.js").then((m) => m.update({})).then((code: number) => {
      console.info(`[dfe-agent] update finalizou com exit code ${code}`);
      return code;
    }).catch((err: Error) => {
      console.error(`[dfe-agent] update falhou: ${err.message}`);
      return 3;
    }) as unknown as number;
  }

  console.info(`[dfe-agent] proximos passos:`);
  console.info(`[dfe-agent]   npx dfe-agent update   # baixa base RAG`);
  console.info(`[dfe-agent]   opencode run           # abre TUI e seleciona @dfe-agent`);
  return 0;
}