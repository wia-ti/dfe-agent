"""PreToolUse do code-reviewer (Bash): bloqueia comandos destrutivos.

Padroes proibidos (case-insensitive):
    - redirecionamento de saida (>, >>, | tee)
    - sed -i (edicao in-place)
    - rm / rmdir / del
    - git commit / git push / git reset --hard
    - pip install / pip uninstall
    - execucao do pipeline RAG: python -m src.collector --once,
      python -m src.indexer.ingest, python -m src.ragctl {migrate,reindex,benchmark}
    - qualquer coisa escrevendo em .opencode/rag/rag.db ou storage/dfe.db

Comandos read-only PERMITIDOS (regex):
    ls, dir, cat, head, tail, wc, find, rg, grep, pytest --collect-only,
    python -c "import ...", python -c "print(...)", git log/diff/show/status,
    rg, type, echo (sem redirecionamento).

Exit codes:
    0 -> comando permitido.
    2 -> comando bloqueado.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__:
    from .._lib.payload import (
        block,
        detect_active_agent,
        get_command,
        log_event,
    )
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from _lib.payload import (  # type: ignore[no-redef]
        block,
        detect_active_agent,
        get_command,
        log_event,
    )

_BLOCK_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r">\s*\S|>>\s*\S|\|\s*tee\b"), "redirecionamento de saida"),
    (re.compile(r"\bsed\s+-i\b"), "edicao in-place com sed"),
    (re.compile(r"\brm\s|\brmdir\s|\bdel\s+/\w"), "remocao de arquivos"),
    (re.compile(r"\bgit\s+commit\b|\bgit\s+push\b|\bgit\s+reset\s+--hard\b"), "escrita em git"),
    (re.compile(r"\bpip\s+install\b|\bpip\s+uninstall\b|\bpoetry\s+(add|remove)\b"),
     "instalacao de pacotes"),
    (re.compile(r"python\s+-m\s+src\.collector\b"), "execucao do coletor (altera base)"),
    (re.compile(r"python\s+-m\s+src\.indexer(?:\.|\b)"), "execucao do indexador (altera base)"),
    (re.compile(r"python\s+-m\s+src\.ragctl\s+(migrate|reindex|benchmark|stats|backfill|drop)\b"),
     "execucao de ragctl (altera base)"),
    (re.compile(r"\.opencode[\\/]+rag[\\/]+rag\.db|storage[\\/]+dfe\.db|storage[\\/]+query_cache\.db"),
     "escrita direta em banco SQLite"),
]

_ALLOW_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\s*(ls|dir)\b"),
    re.compile(r"^\s*cat\s"),
    re.compile(r"^\s*head\s|\btail\s"),
    re.compile(r"^\s*wc\s|\bfind\s|\brg\b|\bgrep\b"),
    re.compile(r"^\s*pytest\s+--collect-only\b"),
    re.compile(r"^\s*pytest\s+-q\s+--collect-only\b"),
    re.compile(r"^\s*python\s+-c\s+[\"']"),
    re.compile(r"^\s*git\s+(log|diff|show|status|branch|rev-parse|remote)\b"),
    re.compile(r"^\s*type\s|\bwhere\s"),
    re.compile(r"^\s*echo\s+[^<>|]+$"),
    re.compile(r"^\s*Get-ChildItem\b|\bGet-Content\b|\bSelect-String\b"),
]


def main() -> int:
    payload = _read_payload_safe()
    agent = detect_active_agent(payload, hook_dir_name="code-reviewer")
    cmd = get_command(payload)
    if not cmd.strip():
        return 0

    for pattern, reason in _BLOCK_PATTERNS:
        if pattern.search(cmd):
            log_event(agent, "pre_tool_use_bash_block", f"{reason}: {cmd[:80]}")
            block(
                f"[code-reviewer] BLOQUEADO: comando read-only viola regra "
                f"({reason}). Comando: `{cmd[:120]}`"
            )

    if not any(p.search(cmd) for p in _ALLOW_PATTERNS):
        log_event(agent, "pre_tool_use_bash_warn", cmd[:80])
        block(
            "[code-reviewer] BLOQUEADO: este agent soh pode executar comandos "
            "de leitura (ls, cat, git log/diff, pytest --collect-only, "
            "python -c \"import ...\"). Comando recusado: `"
            + cmd[:120] + "`"
        )
    return 0


def _read_payload_safe() -> dict:
    try:
        from _lib.payload import read_payload  # type: ignore
    except ImportError:
        return {}
    return read_payload()


if __name__ == "__main__":
    sys.exit(main())
