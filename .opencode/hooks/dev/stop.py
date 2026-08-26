"""Stop do `@dev`: roda pytest geral + captura aprendizados (PLAN_SPRINT10 B.3).

Diferenca para `backend-engineer/stop.py`:
    - `suites = ["tests/"]` (suite completa; @dev e' owner de todo o projeto)
    - `timeout=900` (15min) — suite completa demora mais que subset
    - Caso pytest falhe: block (exit 2) + NAO captura

Fluxo:
    1. Roda pytest geral (`tests/`).
    2. Se pytest falhar: block (exit 2) e NAO captura.
    3. Se pytest passar E payload contiver `tool_writes_count > 0`: chama
       `learning.spawn_summarize_then_embed` (fire-and-forget) com
       `transcript_path` derivado do payload OU do
       `.opencode/sessions/<session_id>.jsonl` mais recente.
    4. Senao: skip silencioso da captura.

Exit codes:
    0 -> pytest passou (captura disparada ou skipped).
    2 -> pytest falhou (encerramento bloqueado).
"""
from __future__ import annotations

import sys
from pathlib import Path

if __package__:
    from .._lib.payload import (
        block,
        detect_active_agent,
        log_event,
    )
    from .._lib.test_runner import run_pytest
    from .._lib import learning
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from _lib.payload import (  # type: ignore[no-redef]
        block,
        detect_active_agent,
        log_event,
    )
    from _lib.test_runner import run_pytest  # type: ignore
    from _lib import learning  # type: ignore[no-redef]


AGENT_SLUG: str = "dev"


def main() -> int:
    payload = read_payload()
    agent = detect_active_agent(payload, hook_dir_name=AGENT_SLUG)
    suites = ["tests/"]
    rc, output = run_pytest(suites, timeout=900)
    log_event(agent, "stop_pytest", f"rc={rc} suites={suites}")
    if rc != 0:
        block(
            "[dev] ENCERRAMENTO BLOQUEADO: pytest geral falhou (rc="
            f"{rc}). Suite: tests/\nUltimas linhas:\n{output}\n"
            "Conserte os testes e rode novamente antes de tentar encerrar."
        )

    session_id = str(payload.get("session_id") or "unknown")
    if learning.payload_has_edits(payload):
        transcript = learning.resolve_transcript(payload)
        if transcript is not None:
            learning.spawn_summarize_then_embed(
                transcript, AGENT_SLUG, session_id
            )
            log_event(
                agent,
                "learning_async",
                f"session_id={session_id} transcript={transcript.name}",
            )
        else:
            log_event(
                agent,
                "learning_skip_no_transcript",
                f"session_id={session_id}",
            )
    else:
        log_event(
            agent,
            "learning_skip_no_edits",
            f"session_id={session_id}",
        )

    return 0


def read_payload() -> dict:
    if __package__:
        from .._lib.payload import read_payload as _read
    else:
        from _lib.payload import read_payload as _read  # type: ignore[no-redef]
    return _read()


if __name__ == "__main__":
    sys.exit(main())
