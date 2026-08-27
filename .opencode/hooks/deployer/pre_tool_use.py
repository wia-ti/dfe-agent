"""PreToolUse do `@deployer`: allow list explicita + block list defensiva.

Estrategia (PLAN_SPRINT18 D18.3):
    - **Allow list** (padrao): git, npm, gh release, npx dfe-agent,
      escape hatch RAG embed, comandos read-only de bash.
    - **Block list** (defesa em profundidade contra bypass):
      Write/Edit/MultiEdit/NotebookEdit (reforca `permission.edit: deny`),
      comandos destrutivos (rm -rf, sed -i, >),
      downloads HTTP (curl, wget), pipeline RAG (collector --once,
      indexer.ingest, ragctl {migrate,reindex,benchmark}),
      pip/poetry install, git commit sem --allow-empty.

Diferenca vs `@dev/pre_tool_use.py`:
    - `@dev`: block list generica (NAO toca paths).
    - `@deployer`: allow list explicita (soh git/npm/gh via Bash;
      defesa em profundidade soh para comandos destrutivos).

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
        get_tool_args,
        get_tool_name,
        log_event,
    )
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from _lib.payload import (  # type: ignore[no-redef]
        block,
        detect_active_agent,
        get_command,
        get_tool_args,
        get_tool_name,
        log_event,
    )


# ============================================================
# WRITE TOOLS — defesa em profundidade
# ============================================================

_WRITE_TOOLS: frozenset[str] = frozenset(
    {"Write", "Edit", "MultiEdit", "NotebookEdit"}
)


# ============================================================
# BASH PATTERNS — defesa em profundidade (block list)
# ============================================================

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
        re.compile(r"\bcurl\s+|\bwget\s+"),
        "downloads HTTP nao fazem parte do escopo do deployer "
        "(use `git clone` ou `npm install` se precisar de um pacote)",
    ),
    (
        re.compile(r"\bpip\s+install\b|\bpoetry\s+(add|install|remove)\b"),
        "instalacao de pacotes Python nao faz parte do escopo do deployer "
        "(decisao humana via PLAN/SPEC)",
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
            r"python\s+-m\s+src\.(collector(?!\s+--diagnose-net)|indexer\.ingest|ragctl\s+(migrate|reindex|benchmark))"
        ),
        "comandos de pipeline RAG devem ser invocados pelo usuario via CLI, "
        "NAO pelo deployer",
    ),
    (
        # git commit sem --allow-empty (NAO escreve historico;
        # deployer sobe o que o humano ja' commitou)
        re.compile(r"\bgit\s+commit\b(?![^\n]*--allow-empty)"),
        "deployer NAO faz commit; sobe o que o humano ja' commitou. "
        "Use `git commit` diretamente no shell se precisar",
    ),
]

_ALLOWED_RAGCTL_READONLY: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"python\s+-m\s+src\.ragctl\s+stats\b"), "leitura"),
    (re.compile(r"python\s+-m\s+src\.collector\s+--diagnose-net\b"), "diagnostico"),
]


def _is_ragctl_readonly(cmd: str) -> bool:
    return any(p.search(cmd) for p, _ in _ALLOWED_RAGCTL_READONLY)


def _is_allowed_bash(cmd: str) -> bool:
    """Allow list explicita do deployer (PLAN_SPRINT18 D18.3).

    Nota (Sprint 18 code-review SUGESTAO 2): os patterns ``\\bgit\\s+\\S+``
    e ``\\bnpm\\s+\\S+`` sao amplos por design — confiam no **gate humano**
    do slash command ``/deploy`` (Fase 3.5) para acoes destrutivas.
    Sub-comandos criativos (ex.: ``git config core.hooksPath``,
    ``npm exec -- curl evil.example``) sao barrados pela confirmacao
    humana antes de cada acao irreversivel, NAO pelo hook.
    """
    patterns: list[re.Pattern[str]] = [
        # git (todos os sub-comandos)
        re.compile(r"\bgit\s+\S+"),
        # npm (todos os sub-comandos)
        re.compile(r"\bnpm\s+\S+"),
        # gh release (apenas comandos release, NAO pr)
        re.compile(r"\bgh\s+release\s+\S+"),
        # npx dfe-agent
        re.compile(r"\bnpx\s+dfe-agent\b"),
        # escape hatch RAG antes (search.ts) + RAG depois (embed.ts)
        re.compile(r"\bnpx\s+--prefix\s+\.opencode\s+tsx\s+\.opencode/rag/(search|embed)\.ts\b"),
        # leitura simples de arquivos
        re.compile(r"^(ls|cat|wc|find|rg|git\s+(log|diff|show|status))\b"),
    ]
    return any(p.search(cmd) for p in patterns)


def main() -> int:
    payload = read_payload_safe()
    agent = detect_active_agent(payload, hook_dir_name="deployer")
    tool = get_tool_name(payload)

    # ---- Write tools: BLOQUEADO (defesa em profundidade) ----
    if tool in _WRITE_TOOLS:
        args = get_tool_args(payload)
        target = str(args.get("file_path") or args.get("path") or args.get("notebook_path") or args)
        log_event(agent, "pre_tool_use_block_write", f"{tool} {target}")
        block(
            f"[deployer] BLOQUEADO: este agent NAO edita arquivos "
            f"(permission.edit: deny no frontmatter). Tentativa: `{tool}` em `{target}`. "
            "Para alterar arquivos do projeto, delegue ao agent `@dev` via "
            "slash command `/feature` ou `/bug`."
        )

    if tool != "Bash":
        return 0

    cmd = get_command(payload)
    if not cmd:
        return 0

    # ---- Redirecionamento / sed -i / rm -rf: BLOQUEADO PRIMEIRO (defesa em profundidade) ----
    # Aplicado ANTES dos demais gates (Sprint 18 code-review SUGESTAO 3):
    # mesmo comandos ragctl read-only com `>` sao bloqueados.
    if _REDIRECTION.search(cmd) or _SED_INPLACE.search(cmd):
        log_event(agent, "pre_tool_use_block_redirection",
                  f"redirection/sed: {cmd[:80]}")
        block(
            f"[deployer] BLOQUEADO: escrita via shell (redirecionamento ou "
            f"sed -i). Use git/npm/gh diretamente. Comando: `{cmd[:120]}`"
        )

    if _RM_RF.search(cmd):
        log_event(agent, "pre_tool_use_block_rm_rf",
                  f"rm -rf: {cmd[:80]}")
        block(
            f"[deployer] BLOQUEADO: `rm -rf` detectado. Use `git clean` ou "
            f"`rm` (sem -rf). Comando: `{cmd[:120]}`"
        )

    # ---- Ragctl read-only: passa direto (sem redirecionamento) ----
    if _is_ragctl_readonly(cmd):
        return 0

    # ---- Block list (defesa em profundidade) ----
    for pattern, reason in _BLOCKED_BASH:
        if pattern.search(cmd):
            log_event(agent, "pre_tool_use_block_bash",
                      f"{reason}: {cmd[:80]}")
            block(f"[deployer] BLOQUEADO: {reason}. Comando: `{cmd[:120]}`")

    # ---- Allow list (default) ----
    if _is_allowed_bash(cmd):
        return 0

    # ---- Default: BLOQUEADO (whitelist strict) ----
    log_event(agent, "pre_tool_use_block_not_allowed",
              f"comando fora da allow list: {cmd[:80]}")
    block(
        f"[deployer] BLOQUEADO: comando fora da allow list. "
        f"Permitido: git/npm/gh release/npx dfe-agent/RAG embed. "
        f"Comando: `{cmd[:120]}`"
    )


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