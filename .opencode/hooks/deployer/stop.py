"""Stop do `@deployer`: exit 0 sem pytest e sem RAG capture.

Diferenca vs `@dev/stop.py`:
    - `@dev` roda pytest geral + chama `learning.spawn_summarize_then_embed`
      se payload tem `tool_writes_count > 0`.
    - `@deployer` apenas retorna 0 (deploy e' acao atomica).

RAG capture do deployer e' feita explicitamente pelo slash command
`/deploy` na Fase 4 (comando `npx tsx .opencode/rag/embed.ts --file <md>`
sincrono), NAO via hook stop assincrono.

Exit codes:
    0 -> sempre (deployer NAO bloqueia encerramento).
"""
from __future__ import annotations

import sys
from pathlib import Path

if __package__:
    from .._lib.payload import detect_active_agent, log_event
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from _lib.payload import (  # type: ignore[no-redef]
        detect_active_agent,
        log_event,
    )


AGENT_SLUG: str = "deployer"


def main() -> int:
    payload = read_payload_safe()
    agent = detect_active_agent(payload, hook_dir_name=AGENT_SLUG)
    session_id = str(payload.get("session_id") or "unknown")
    log_event(
        agent,
        "stop_exit_zero",
        f"session_id={session_id} (deployer NAO roda pytest, NAO captura RAG)",
    )
    return 0


def read_payload_safe() -> dict:
    try:
        if __package__:
            from .._lib.payload import read_payload
        else:
            from _lib.payload import read_payload  # type: ignore[no-redef]
    except ImportError:
        return {}
    return read_payload()


if __name__ == "__main__":
    sys.exit(main())