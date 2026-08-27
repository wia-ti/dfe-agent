"""PostToolUse do `@deployer`: observer lightweight (NAO roda pytest).

Diferenca vs `@dev/post_tool_use.py`:
    - `@dev` roda pytest da suite apropriada.
    - `@deployer` apenas escreve log_event em `storage/agent_hooks.log`
      (deploy e' acao atomica; NAO ha codigo a ser testado).

Exit codes:
    0 -> sempre (observador).
"""
from __future__ import annotations

import sys
from pathlib import Path

if __package__:
    from .._lib.payload import (
        detect_active_agent,
        get_command,
        get_tool_name,
        log_event,
    )
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from _lib.payload import (  # type: ignore[no-redef]
        detect_active_agent,
        get_command,
        get_tool_name,
        log_event,
    )


AGENT_SLUG: str = "deployer"


def main() -> int:
    payload = read_payload_safe()
    agent = detect_active_agent(payload, hook_dir_name=AGENT_SLUG)
    tool = get_tool_name(payload)
    cmd = get_command(payload) if tool == "Bash" else tool

    log_event(
        agent,
        "post_tool_use_observer",
        f"tool={tool} cmd={cmd[:80] if cmd else '<empty>'}",
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