// .opencode/plugin/agent-hooks.ts
// Plugin OpenCode que despacha hooks PreToolUse/PostToolUse/Stop para
// os scripts Python em .opencode/hooks/<agent>/ conforme o agent ativo.
//
// Mapeamento (PLAN_SPRINT11 C.3 + PLAN_SPRINT18 D18.7):
//   code-reviewer     -> pre_tool_use.py + pre_tool_use_bash.py
//   dev               -> pre_tool_use.py + post_tool_use.py + stop.py
//   deployer          -> pre_tool_use.py + post_tool_use.py + stop.py  (Sprint 18)
//
// Os 4 slugs legacy (backend-engineer, ml-engineer, prompt-engineer,
// qa-engineer) foram removidos em Sprint 11: o agente `@dev` e' owner
// de todas as alteracoes do projeto (Sprint 10). O agente `@deployer`
// foi adicionado em Sprint 18 para substituir o CI (GitHub Actions foi
// removido na mesma sprint).
//
// Exit code 2 -> bloqueia a tool (Claude Code convention).
// Exit code 0 -> permite.
//
// Como o opencode expõe o agent via sessionID (e nao temos
// subagent_type direto em tool.execute.before), usamos a heuristica
// abaixo: se a sessão atual foi iniciada com `--agent <slug>`, esse
// slug é propagado via `DFE_ACTIVE_AGENT` no env do shell. Caso
// contrario, o agent default é "session" e todos os hooks rodam em
// modo permissivo.

import type { Plugin, PluginInput } from "@opencode-ai/plugin";
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const PROJECT_ROOT: string = resolve(
  fileURLToPath(new URL(".", import.meta.url)),
  "../..",
);

interface AgentProfile {
  slug: string;
  preToolUse?: string;
  preToolUseBash?: string;
  postToolUse?: string;
  stop?: string;
}

const AGENTS: Record<string, AgentProfile> = {
  "code-reviewer": {
    slug: "code-reviewer",
    preToolUse: ".opencode/hooks/code-reviewer/pre_tool_use.py",
    preToolUseBash: ".opencode/hooks/code-reviewer/pre_tool_use_bash.py",
  },
  "deployer": {
    slug: "deployer",
    preToolUse: ".opencode/hooks/deployer/pre_tool_use.py",
    postToolUse: ".opencode/hooks/deployer/post_tool_use.py",
    stop: ".opencode/hooks/deployer/stop.py",
  },
  "dev": {
    slug: "dev",
    preToolUse: ".opencode/hooks/dev/pre_tool_use.py",
    postToolUse: ".opencode/hooks/dev/post_tool_use.py",
    stop: ".opencode/hooks/dev/stop.py",
  },
};

const ALL_HOOKS: AgentProfile[] = Object.values(AGENTS);

function scriptAbsPath(rel: string): string {
  return resolve(PROJECT_ROOT, rel);
}

interface RunResult {
  code: number;
  stdout: string;
  stderr: string;
}

function runPython(
  script: string,
  payload: unknown,
  timeoutMs: number,
): Promise<RunResult> {
  return new Promise((resolveRun) => {
    const abs = scriptAbsPath(script);
    if (!existsSync(abs)) {
      resolveRun({ code: 0, stdout: "", stderr: `[agent-hooks] script ausente: ${abs}` });
      return;
    }
    const child = spawn(
      process.platform === "win32" ? "python" : "python3",
      [abs],
      {
        cwd: PROJECT_ROOT,
        env: {
          ...process.env,
          PYTHONIOENCODING: "utf-8",
          PYTHONUNBUFFERED: "1",
          DFE_PROJECT_ROOT: PROJECT_ROOT,
        },
        stdio: ["pipe", "pipe", "pipe"],
      },
    );
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (d: Buffer) => {
      stdout += d.toString("utf-8");
    });
    child.stderr.on("data", (d: Buffer) => {
      stderr += d.toString("utf-8");
    });
    const timer = setTimeout(() => {
      child.kill();
      resolveRun({ code: 124, stdout, stderr: stderr + "\n[agent-hooks] timeout" });
    }, timeoutMs);
    child.on("close", (code) => {
      clearTimeout(timer);
      resolveRun({ code: code ?? 0, stdout, stderr });
    });
    child.on("error", (err) => {
      clearTimeout(timer);
      resolveRun({ code: 0, stdout, stderr: stderr + `\n[agent-hooks] spawn error: ${err.message}` });
    });
    try {
      child.stdin.write(JSON.stringify(payload ?? {}));
      child.stdin.end();
    } catch {
      // stdin ja fechado
    }
  });
}

function detectAgentFromSession(
  input: { sessionID: string },
  fallback: string,
): string {
  // Heuristica: sessionID eh um ULID nao relacionado ao agent;
  // o agent default vem do env var DFE_ACTIVE_AGENT (setado pelo
  // wrapper CLI) ou do argumento --agent da CLI.
  const fromEnv = (process.env.DFE_ACTIVE_AGENT ?? "").trim().toLowerCase();
  if (fromEnv && fromEnv in AGENTS) return fromEnv;

  // Fallback explicito PLAN_SPRINT4 B.1: scan process.argv por slug
  // conhecido (algumas versoes do opencode CLI aceitam `--agent <slug>`
  // sem setar env var). Tambem suporta `--agent=<slug>`.
  const argv = process.argv.map((s) => s.toLowerCase());
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i]!;
    if (arg === "--agent" || arg === "--subagent") {
      const next = argv[i + 1];
      if (next && next in AGENTS) return next;
    }
    if (arg.startsWith("--agent=") || arg.startsWith("--subagent=")) {
      const value = arg.split("=", 2)[1] ?? "";
      if (value in AGENTS) return value;
    }
  }

  // tenta inferir pelo sessionID (algumas CLIs injetam slug)
  const sid = (input.sessionID ?? "").toLowerCase();
  for (const slug of Object.keys(AGENTS)) {
    if (sid.includes(slug)) return slug;
  }
  return fallback;
}

// Conjunto canonico de slugs reconhecidos (PLAN_SPRINT11 C.3 + PLAN_SPRINT18 D18.7).
// Sprint 18 adicionou `deployer` para substituir o CI removido.
// Slugs orfaos como "build" ou "plan" NAO devem mais aparecer; este
// conjunto serve de referencia estavel para documentacao e warnings.
const RECOGNIZED_AGENT_SLUGS: ReadonlySet<string> = new Set([
  "dev",
  "code-reviewer",
  "deployer",
]);

function warnAgentNotDetected(sessionID: string, logPath: string): void {
  // Registra warning em storage/agent_hooks.log para auditoria.
  // Degradacao controlada (PLAN_SPRINT4 B.1): quando nenhum agent
  // for detectado, todos os hooks rodam em modo permissivo.
  try {
    const fs = require("node:fs") as typeof import("node:fs");
    const path = require("node:path") as typeof import("node:path");
    fs.mkdirSync(path.dirname(logPath), { recursive: true });
    const line =
      `[${new Date().toISOString()}] [session] agent nao detectado; ` +
      `modo permissivo (bypass ativo) session_id=${sessionID}\n`;
    fs.appendFileSync(logPath, line, "utf-8");
  } catch {
    // Falha no log NAO derruba o opencode.
  }
}

const AGENT_LOG_PATH: string = (() => {
  const path = require("node:path") as typeof import("node:path");
  return path.resolve(PROJECT_ROOT, "storage", "agent_hooks.log");
})();

export const AgentHooksPlugin: Plugin = async (
  _input: PluginInput,
): Promise<import("@opencode-ai/plugin").Hooks> => {
  // Contador de writes (Write/Edit/MultiEdit/NotebookEdit) por sessionID.
  // Plano Sprint 8 B.1: stop.py de cada agent usa este contador para
  // decidir se dispara o pipeline summarize+embed (escopo = so'
  // implementacoes).
  const writesPerSession: Map<string, number> = new Map();

  return {
    "tool.execute.before": async (toolInput, output) => {
      const tool: string = toolInput.tool ?? "";
      const agent = detectAgentFromSession(toolInput, "session");
      if (agent === "session") {
        warnAgentNotDetected(toolInput.sessionID ?? "", AGENT_LOG_PATH);
      }
      const profile = AGENTS[agent];
      if (!profile) return;

      let hookScript: string | undefined;
      if (tool === "Bash" && "preToolUseBash" in profile) {
        hookScript = profile.preToolUseBash;
      } else if ("preToolUse" in profile) {
        hookScript = profile.preToolUse;
      }
      if (!hookScript) return;

      const payload = {
        session_id: toolInput.sessionID,
        call_id: toolInput.callID,
        agent,
        tool_name: tool,
        tool_input: output.args ?? {},
      };
      const result = await runPython(hookScript, payload, 15_000);
      if (result.stderr) {
        process.stderr.write(result.stderr);
      }
      if (result.code === 2) {
        throw new Error(
          `[agent-hooks] BLOQUEADO por ${agent}: ${result.stderr.trim() || "violacao de escopo"}`,
        );
      }
    },

    "tool.execute.after": async (toolInput, output) => {
      const tool: string = toolInput.tool ?? "";
      const agent = detectAgentFromSession(toolInput, "session");
      if (agent === "session") {
        warnAgentNotDetected(toolInput.sessionID ?? "", AGENT_LOG_PATH);
      }
      const profile = AGENTS[agent];
      if (!profile || !profile.postToolUse) return;
      if (!["Write", "Edit", "MultiEdit", "NotebookEdit"].includes(tool)) return;

      // Conta o write para esta sessionID (PLAN_SPRINT8 B.1).
      const sid: string = toolInput.sessionID ?? "";
      if (sid) {
        writesPerSession.set(sid, (writesPerSession.get(sid) ?? 0) + 1);
      }

      const payload = {
        session_id: toolInput.sessionID,
        call_id: toolInput.callID,
        agent,
        tool_name: tool,
        tool_input: toolInput.args ?? {},
        title: output.title,
        output: output.output,
      };
      const result = await runPython(profile.postToolUse, payload, 180_000);
      if (result.stderr) {
        process.stderr.write(result.stderr);
      }
      // PostToolUse nunca bloqueia; soh observa.
    },

    event: async ({ event }) => {
      // Mapeia o evento opencode "session.stopped" para o hook stop.py
      // de cada agent (code-reviewer/qa-engineer nao tem stop).
      const ev: { type?: string; sessionID?: string; agent?: string } = event as {
        type?: string;
        sessionID?: string;
        agent?: string;
      };
      if (ev?.type !== "session.stopped" && ev?.type !== "session.idle") return;
      const agent = detectAgentFromSession({ sessionID: ev.sessionID ?? "" }, "session");
      if (agent === "session") {
        warnAgentNotDetected(ev.sessionID ?? "", AGENT_LOG_PATH);
      }
      const profile = AGENTS[agent];
      if (!profile || !profile.stop) return;

      const sid: string = ev.sessionID ?? "";
      const writes: number = writesPerSession.get(sid) ?? 0;
      const payload = {
        session_id: ev.sessionID,
        agent,
        tool_writes_count: writes,
      };
      const result = await runPython(profile.stop, payload, 600_000);
      if (result.stderr) {
        process.stderr.write(result.stderr);
      }
      if (result.code === 2) {
        throw new Error(
          `[agent-hooks] STOP BLOQUEADO por ${agent}: ${result.stderr.trim() || "testes falharam"}`,
        );
      }

      // Limpa contador da session apos o stop (evita crescimento ilimitado).
      if (sid) {
        writesPerSession.delete(sid);
      }
    },
  };
};

export default AgentHooksPlugin;