"""Dispatcher de hooks do Claude Code para os scripts Python por agent.

Porta do antigo plugin OpenCode ``.opencode/plugin/agent-hooks.ts``. O
``.claude/settings.json`` chama este script em cada evento
(``pre``/``post``/``stop``/``subagent-stop``) e ele decide, pelo agent
ativo, qual script de ``.claude/hooks/<agent>/`` executar.

Deteccao do agent (substitui a heuristica ``DFE_ACTIVE_AGENT`` do plugin TS):
    - Dentro de um subagent, o Claude Code envia ``agent_type`` no payload
      (``code-reviewer``, ``deployer``, ``dfe-agent``, ``Explore``...).
    - Na sessao principal nao ha ``agent_type``: a sessao principal faz o
      papel do antigo ``@dev`` (owner das alteracoes), entao recebe os hooks
      de ``dev``.
    - Subagents genericos (``general-purpose``, ``Explore``, ``Plan``) tambem
      recebem os hooks PreToolUse de ``dev`` (defesa em profundidade).
    - ``dfe-agent`` nao tem hooks (igual ao OpenCode).

Exit codes (convencao Claude Code, a mesma dos scripts):
    0 -> permite / observa.
    2 -> bloqueia (stderr e' mostrado ao Claude).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

HOOKS_DIR: Path = Path(__file__).resolve().parent
PROJECT_ROOT: Path = HOOKS_DIR.parents[1]

WRITE_TOOLS: frozenset[str] = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})

PROFILES: dict[str, dict[str, str]] = {
    "code-reviewer": {
        "pre": "code-reviewer/pre_tool_use.py",
        "pre_bash": "code-reviewer/pre_tool_use_bash.py",
    },
    "deployer": {
        "pre": "deployer/pre_tool_use.py",
        "post": "deployer/post_tool_use.py",
        "stop": "deployer/stop.py",
    },
    "dev": {
        "pre": "dev/pre_tool_use.py",
        "post": "dev/post_tool_use.py",
        "stop": "dev/stop.py",
    },
    "dfe-agent": {},
}


def resolve_agent(payload: dict[str, Any]) -> str:
    agent_type = str(payload.get("agent_type") or "").strip().lower()
    if not agent_type:
        return "dev"
    return agent_type if agent_type in PROFILES else "dev"


def count_writes_in_turn(transcript: str | None) -> int:
    """Conta Write/Edit/MultiEdit/NotebookEdit desde o ultimo prompt do usuario.

    Substitui o contador ``writesPerSession`` do plugin TS. Le o transcript
    JSONL do Claude Code; falha de leitura conta como 0.
    """
    if not transcript:
        return 0
    path = Path(transcript)
    if not path.exists():
        return 0
    count = 0
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return 0
    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = entry.get("message") or {}
        content = message.get("content")
        if entry.get("type") == "user":
            is_tool_result = isinstance(content, list) and any(
                isinstance(c, dict) and c.get("type") == "tool_result" for c in content
            )
            if not is_tool_result:
                count = 0
            continue
        if entry.get("type") == "assistant" and isinstance(content, list):
            count += sum(
                1
                for c in content
                if isinstance(c, dict)
                and c.get("type") == "tool_use"
                and c.get("name") in WRITE_TOOLS
            )
    return count


def run_script(rel: str, payload: dict[str, Any]) -> int:
    script = HOOKS_DIR / rel
    if not script.exists():
        sys.stderr.write(f"[dispatch] script ausente: {script}\n")
        return 0
    proc = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(PROJECT_ROOT),
        env={**_env(), "DFE_PROJECT_ROOT": str(PROJECT_ROOT)},
        check=False,
    )
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    return 2 if proc.returncode == 2 else 0


def _env() -> dict[str, str]:
    import os

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    return env


def main(event: str) -> int:
    raw = sys.stdin.read()
    try:
        payload: dict[str, Any] = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return 0

    agent = resolve_agent(payload)
    profile = PROFILES.get(agent, {})
    payload["agent"] = agent
    tool = str(payload.get("tool_name") or "")

    if event == "pre":
        script = profile.get("pre_bash") if tool == "Bash" and "pre_bash" in profile else profile.get("pre")
        return run_script(script, payload) if script else 0

    if event == "post":
        if tool not in WRITE_TOOLS or "post" not in profile:
            return 0
        return run_script(profile["post"], payload)

    if event in ("stop", "subagent-stop"):
        if event == "stop":
            agent, profile = "dev", PROFILES["dev"]
            transcript = payload.get("transcript_path")
        else:
            if agent != "deployer":
                return 0
            transcript = payload.get("agent_transcript_path") or payload.get("transcript_path")
        if "stop" not in profile:
            return 0
        writes = count_writes_in_turn(transcript)
        # Turno sem edicao: nada para testar nem aprender (evita rodar a suite
        # inteira a cada resposta de leitura).
        if agent == "dev" and writes == 0:
            return 0
        payload.update({"agent": agent, "tool_writes_count": writes})
        rc = run_script(profile["stop"], payload)
        # Evita loop infinito: se o Stop ja foi bloqueado uma vez neste ciclo,
        # apenas avisa (a falha fica visivel no stderr).
        if rc == 2 and payload.get("stop_hook_active"):
            sys.stderr.write("[dispatch] stop ja bloqueado neste ciclo; liberando para o humano arbitrar.\n")
            return 0
        return rc

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ""))
