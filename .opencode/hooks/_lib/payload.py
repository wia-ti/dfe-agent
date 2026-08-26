"""Utilidades compartilhadas entre os hooks de agent.

Padrao de payload:
    Claude Code envia para hooks PreToolUse/PostToolUse um JSON via stdin
    no formato::

        {
          "session_id": "...",
          "hook_event_name": "PreToolUse",
          "tool_name": "Bash",
          "tool_input": {"command": "..."}   # ou file_path, etc.
        }

    OpenCode envia o mesmo payload, mas o `tool_name` vem como `tool`
    e os campos do input sao injetados direto. Esta camada normaliza.

Exit codes (Claude Code / OpenCode):
    0 -> permite a operacao (pass-through).
    2 -> bloqueia a operacao (stderr e mostrado ao agent).
    Qualquer outro -> erro de infra do hook; tratado como permissivo.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]

if not (PROJECT_ROOT / "AGENTS.md").exists():
    _candidates: list[Path] = [
        Path.cwd(),
        Path(__file__).resolve().parents[2],
        Path(__file__).resolve().parents[3],
    ]
    for _cand in _candidates:
        if (_cand / "AGENTS.md").exists():
            PROJECT_ROOT = _cand
            break

_ENV_AGENT: str = "DFE_ACTIVE_AGENT"
_AGENT_HINTS: list[tuple[str, re.Pattern[str]]] = [
    ("code-reviewer", re.compile(r"\bcode[-_]?reviewer|revisor\b", re.IGNORECASE)),
    ("dev", re.compile(r"\bdev\b(?!elop|ice|el|our|oid)", re.IGNORECASE)),
]


def read_payload() -> dict[str, Any]:
    """Le JSON do stdin; aceita tambem texto puro como fallback."""
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    raw = raw.strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def detect_active_agent(payload: dict[str, Any], hook_dir_name: str | None = None) -> str:
    """Descobre o agent ativo.

    Ordem de precedencia:
        1. Campo explicito ``agent`` / ``subagent_type`` no payload.
        2. Variavel de ambiente ``DFE_ACTIVE_AGENT``.
        3. Nome do diretorio onde o hook reside
           (``.../hooks/<agent>/<script>.py``).
        4. Heuristica sobre session_id / transcript_path.
    """
    for key in ("agent", "subagent_type", "agent_slug"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip().lower()

    env_agent = os.environ.get(_ENV_AGENT, "").strip().lower()
    if env_agent:
        return env_agent

    if hook_dir_name:
        return hook_dir_name.lower()

    for key in ("session_id", "transcript_path"):
        val = str(payload.get(key, ""))
        for slug, pattern in _AGENT_HINTS:
            if pattern.search(val):
                return slug
    return "session"


def get_tool_name(payload: dict[str, Any]) -> str:
    """Normaliza nome da tool entre Claude Code (`tool_name`) e OpenCode (`tool`)."""
    return str(payload.get("tool_name") or payload.get("tool") or "")


def get_tool_args(payload: dict[str, Any]) -> dict[str, Any]:
    """Normaliza argumentos da tool.

    Claude Code: ``tool_input.command`` / ``tool_input.file_path``.
    OpenCode:    argumentos injetados como ``args.command`` etc.
    """
    args = payload.get("tool_input")
    if not isinstance(args, dict):
        args = payload.get("args")
    return args if isinstance(args, dict) else {}


def get_command(payload: dict[str, Any]) -> str:
    """Extrai o comando Bash do payload."""
    return str(get_tool_args(payload).get("command") or "")


def get_file_path(payload: dict[str, Any]) -> str:
    """Extrai o caminho de arquivo do payload."""
    args = get_tool_args(payload)
    for key in ("file_path", "path", "notebook_path"):
        if key in args:
            return str(args[key])
    return ""


def block(reason: str) -> "NoReturn":
    """Imprime motivo no stderr e sai com codigo 2."""
    sys.stderr.write(reason.rstrip() + "\n")
    sys.exit(2)


def allow() -> None:
    """Saida neutra (sem stderr, exit 0)."""
    sys.exit(0)


def log_event(agent: str, hook: str, detail: str, log_path: Path | None = None) -> None:
    """Escreve uma linha no log de eventos dos hooks de agent."""
    if log_path is None:
        log_path = PROJECT_ROOT / "storage" / "agent_hooks.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{agent}] [{hook}] {detail}"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line.rstrip() + "\n")
