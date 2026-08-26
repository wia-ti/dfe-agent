"""PreToolUse do `@dev`: bloqueia comandos destrutivos globais.

Diferenca para `backend-engineer/pre_tool_use.py`: o `@dev` e' owner de
TODO o projeto (escopo amplo), entao este hook NAO bloqueia paths. Apenas
bloqueia acoes globais perigosas (defesa em profundidade — alem do
`permission.*` no frontmatter).

Comandos BLOQUEADOS:
    - git push / gh pr create / gh release (acao humana)
    - pip install / poetry add (dependencias via PLAN/SPEC)
    - curl/wget (downloads HTTP vao pelo DocumentCollector)
    - rm -rf, sed -i, redirecionamento `>` (escrita shell)
    - SQL direto em `*.db` (acesso via classes em src/db/)
    - comandos do pipeline RAG (python -m src.collector --once,
      src.indexer.ingest, src.ragctl {migrate,reindex,benchmark})

Exit codes:
    0 -> permitido.
    2 -> bloqueado.
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
        get_tool_name,
        log_event,
    )
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from _lib.payload import (  # type: ignore[no-redef]
        block,
        detect_active_agent,
        get_command,
        get_tool_name,
        log_event,
    )


_REDIRECTION: re.Pattern[str] = re.compile(
    r"(?<![<>])>\s*[^\s|&;]|<\s*[^\s|&;]|\|\s*(?:tee|dd\s+of=)"
)
_SED_INPLACE: re.Pattern[str] = re.compile(r"\bsed\s+-i\b")
_RM_RF: re.Pattern[str] = re.compile(
    r"\brm\s+(?:-[a-zA-Z]*[rRfF][a-zA-Z]*[rRfF][a-zA-Z]*|"
    r"-[a-zA-Z]*[rRfF][a-zA-Z]*\s+-[a-zA-Z]*[rRfF][a-zA-Z]*|"
    r"--recursive\s+--force|--force\s+--recursive)\b"
)

_BLOCKED_BASH: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\bgit\s+push\b|\bgh\s+pr\s+create\b|\bgh\s+release\b"),
        "@dev nao faz push / abre PR (acao humana)",
    ),
    (
        re.compile(r"\bpip\s+install\b|\bpoetry\s+(add|install|remove)\b"),
        "dependencias sao decididas no PLAN/SPEC -- delegue ao humano",
    ),
    (
        re.compile(r"\bcurl\s+|\bwget\s+"),
        "downloads HTTP vao pelo DocumentCollector (escopo do coletor ja implementado)",
    ),
    (
        re.compile(r"\bsqlite3\s+.*\.(db|sqlite)\b|\bsqlitebrowser\b"),
        "acesso direto a SQLite deve passar pelas classes de src/db/",
    ),
    (
        re.compile(
            r"python\s+-c\s+[\"'].*sqlite3\.connect.*[\"']"
        ),
        "acesso direto a SQLite deve passar pelas classes de src/db/",
    ),
    (
        re.compile(
            r"npx\s+tsx\s+\.opencode/rag/(embed|search|summarize)\.ts"
        ),
        "scripts do RAG meta-cognitivo sao chamados pelos hooks learning_* ou pelos commands /feature /bug /duvida explicitamente",
    ),
    (
        re.compile(
            r"python\s+-m\s+src\.(collector(?!\s+--diagnose-net)|indexer\.ingest|ragctl\s+(migrate|reindex|benchmark))"
        ),
        "comandos de pipeline RAG devem ser invocados pelo usuario via CLI, NAO pelo agent",
    ),
]

_ALLOWED_RAGCTL_READONLY: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"python\s+-m\s+src\.ragctl\s+stats\b"), "leitura"),
    (re.compile(r"python\s+-m\s+src\.collector\s+--diagnose-net\b"), "diagnostico de rede"),
]


def _is_ragctl_readonly(cmd: str) -> bool:
    return any(p.search(cmd) for p, _ in _ALLOWED_RAGCTL_READONLY)


def main() -> int:
    payload = read_payload_safe()
    agent = detect_active_agent(payload, hook_dir_name="dev")
    tool = get_tool_name(payload)

    if tool != "Bash":
        return 0

    cmd = get_command(payload)
    if not cmd:
        return 0

    if _is_ragctl_readonly(cmd):
        return 0

    if _REDIRECTION.search(cmd) or _SED_INPLACE.search(cmd):
        log_event(
            agent,
            "pre_tool_use_block_redirection",
            f"redirection/sed detectado: {cmd[:80]}",
        )
        block(
            f"[dev] BLOQUEADO: escrita via shell (redirecionamento ou sed -i). "
            f"Use Write/Edit do opencode. Comando: `{cmd[:120]}`"
        )

    if _RM_RF.search(cmd):
        log_event(
            agent,
            "pre_tool_use_block_rm_rf",
            f"rm -rf detectado: {cmd[:80]}",
        )
        block(
            f"[dev] BLOQUEADO: `rm -rf` detectado. Use Write/Edit do opencode "
            f"ou git revert. Comando: `{cmd[:120]}`"
        )

    for pattern, reason in _BLOCKED_BASH:
        if pattern.search(cmd):
            log_event(agent, "pre_tool_use_block_bash", f"{reason}: {cmd[:80]}")
            block(
                f"[dev] BLOQUEADO: {reason}. Comando: `{cmd[:120]}`"
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
