"""PreToolUse do code-reviewer: bloqueia modificacao de arquivos.

Ferramentas interceptadas:
    Write, Edit, MultiEdit, NotebookEdit -> qualquer arquivo do workspace.

Exit codes:
    0 -> permite (nao chegou a bater nesse hook pois matcher ja filtra).
    2 -> bloqueia com mensagem explicando que o agent eh read-only.

Origem: definido no frontmatter de ``.opencode/agent/code-reviewer.md``.
"""
from __future__ import annotations

import sys
from pathlib import Path

if __package__:
    from .._lib.payload import (
        block,
        detect_active_agent,
        get_file_path,
        get_tool_args,
        get_tool_name,
        log_event,
    )
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from _lib.payload import (  # type: ignore[no-redef]
        block,
        detect_active_agent,
        get_file_path,
        get_tool_args,
        get_tool_name,
        log_event,
    )

_WRITE_TOOLS: frozenset[str] = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})


def main() -> int:
    payload = _read_payload_safe()
    agent = detect_active_agent(payload, hook_dir_name="code-reviewer")
    tool = get_tool_name(payload)
    args = get_tool_args(payload)

    if tool not in _WRITE_TOOLS:
        return 0

    target = get_file_path(payload) or str(args)
    log_event(agent, "pre_tool_use_block_write", f"{tool} {target}")
    block(
        "[code-reviewer] BLOQUEADO: este agent eh read-only. "
        f"Tentativa de usar `{tool}` em `{target}`. "
        "Use apenas Read/Glob/Grep/WebFetch e comandos bash de leitura "
        "(ls, cat, git log/diff, pytest --collect-only). "
        "Para alterar arquivos, delegue ao agent `dev`."
    )


def _read_payload_safe() -> dict:
    try:
        from _lib.payload import read_payload  # type: ignore
    except ImportError:
        return {}
    return read_payload()


if __name__ == "__main__":
    sys.exit(main())
