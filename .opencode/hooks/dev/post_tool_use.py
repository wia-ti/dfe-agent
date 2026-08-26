"""PostToolUse do `@dev`: roda pytest da suite apropriada apos edicao.

Mesmo padrao dos agents legacy (removidos em Sprint 11 I11.2):
apos cada Write/Edit, determina a suite pytest correspondente via
`.opencode/hooks/_lib/test_runner.py::suites_for_path(edited_path, agent="dev")`
e roda pytest em background.

Falha NAO bloqueia imediatamente (PostToolUse soh observa). O gate final
eh no `stop.py` (suite completa).

Exit codes:
    0 -> sempre (observador).
"""
from __future__ import annotations

import sys
from pathlib import Path

if __package__:
    from .._lib.payload import (
        detect_active_agent,
        get_file_path,
        get_tool_name,
        log_event,
    )
    from .._lib.test_runner import run_pytest, suites_for_path
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from _lib.payload import (  # type: ignore[no-redef]
        detect_active_agent,
        get_file_path,
        get_tool_name,
        log_event,
    )
    from _lib.test_runner import run_pytest, suites_for_path  # type: ignore


AGENT_SLUG: str = "dev"


def main() -> int:
    payload = read_payload_safe()
    agent = detect_active_agent(payload, hook_dir_name=AGENT_SLUG)
    tool = get_tool_name(payload)

    if tool not in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        return 0

    path = get_file_path(payload)
    if not path:
        return 0

    rel = path.replace("\\", "/").lstrip("./")
    suites = suites_for_path(rel, agent=AGENT_SLUG)
    if not suites:
        return 0

    rc, output = run_pytest(suites, timeout=180)
    log_event(
        agent,
        "post_tool_use_pytest",
        f"path={rel} suites={suites} rc={rc}",
    )
    if rc != 0:
        sys.stderr.write(
            f"[dev] pytest apos edicao em {rel} falhou (rc={rc}). "
            f"Suite sera re-rodada no stop.py. Output (tail):\n{output[-500:]}\n"
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
