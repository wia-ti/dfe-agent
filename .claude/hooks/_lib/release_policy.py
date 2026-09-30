"""Politica de versionamento compartilhada pelos hooks `dev` e `deployer` (Sprint 20).

Desde a Sprint 20 o versionamento e' do semantic-release no GitHub Actions
(`.github/workflows/release.yml`): ele le os commits convencionais, cria a tag
`vX.Y.Z`, a GitHub Release e publica o `@wiati/dfe-agent` no npm. Por isso:

- ``commit_message_violation``: todo `git commit` precisa seguir
  Conventional Commits, senao o semantic-release nao sabe que versao gerar.
- ``manual_release_violation``: tag `v*`, `npm publish`/`npm version` e
  release `v*` manuais sao bloqueados (competiriam com o CI). A release
  rolante `rag-base` (base RAG) continua liberada.

O comando e' tokenizado respeitando aspas e separado em `&&`, `||`, `;`, `|`,
para que texto dentro de mensagens de commit nao gere falso positivo e
`git -c k=v commit` nao escape da validacao.
"""
from __future__ import annotations

import re
import shlex
from pathlib import Path

CONVENTIONAL_TYPES: tuple[str, ...] = (
    "feat",
    "fix",
    "perf",
    "refactor",
    "docs",
    "test",
    "build",
    "ci",
    "chore",
    "style",
    "revert",
)

_CONVENTIONAL_HEADER: re.Pattern[str] = re.compile(
    r"^(?:" + "|".join(CONVENTIONAL_TYPES) + r")(?:\([\w./-]+\))?!?: \S.*$"
)
_VERSION_TAG: re.Pattern[str] = re.compile(r"^v\d+(?:\.\d+)*")
_VERSION_REFSPEC: re.Pattern[str] = re.compile(r"(?:^|:|refs/tags/)v\d+\.\d+")
_OPERATORS: frozenset[str] = frozenset({"&&", "||", ";", "|", "&"})
# Opcoes globais do git que consomem o proximo token.
_GIT_OPTS_WITH_VALUE: frozenset[str] = frozenset(
    {"-c", "-C", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
)
_UNPARSEABLE = "comando de git/npm/gh nao parseavel (aspas desbalanceadas?)"


def _segments(cmd: str) -> list[list[str]] | None:
    """Tokens de cada comando simples; ``None`` se as aspas nao fecham."""
    lexer = shlex.shlex(cmd, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return None
    segments: list[list[str]] = [[]]
    for tok in tokens:
        if tok in _OPERATORS:
            segments.append([])
        else:
            segments[-1].append(tok)
    return [s for s in segments if s]


def _program(tokens: list[str]) -> str:
    name = tokens[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
    return name.removesuffix(".exe").removesuffix(".cmd")


def _git_subcommand(tokens: list[str]) -> tuple[str, list[str]] | None:
    i = 1
    while i < len(tokens):
        tok = tokens[i]
        if tok in _GIT_OPTS_WITH_VALUE:
            i += 2
            continue
        if tok.startswith("-"):
            i += 1
            continue
        return tok, tokens[i + 1:]
    return None


def _mentions_release_tools(cmd: str) -> bool:
    return re.search(r"\b(?:git|npm|gh)\b", cmd) is not None


def _commit_messages(args: list[str]) -> list[str]:
    messages: list[str] = []
    i = 0
    while i < len(args):
        tok = args[i]
        has_next = i + 1 < len(args)
        if (tok == "--message" or re.fullmatch(r"-[a-zA-Z]*m", tok)) and has_next:
            messages.append(args[i + 1])
            i += 2
            continue
        if (tok == "--file" or re.fullmatch(r"-[a-zA-Z]*F", tok)) and has_next:
            path = Path(args[i + 1])
            messages.append(path.read_text(encoding="utf-8") if path.is_file() else "")
            i += 2
            continue
        if tok.startswith("--message="):
            messages.append(tok.split("=", 1)[1])
        elif tok.startswith("--file="):
            path = Path(tok.split("=", 1)[1])
            messages.append(path.read_text(encoding="utf-8") if path.is_file() else "")
        elif re.fullmatch(r"-m.+", tok):
            messages.append(tok[2:])
        i += 1
    return messages


def commit_message_violation(cmd: str) -> str | None:
    """Motivo do bloqueio se o `git commit` nao segue Conventional Commits."""
    segments = _segments(cmd)
    if segments is None:
        return _UNPARSEABLE if re.search(r"\bcommit\b", cmd) else None
    for tokens in segments:
        if _program(tokens) != "git":
            continue
        sub = _git_subcommand(tokens)
        if sub is None or sub[0] != "commit":
            continue
        messages = _commit_messages(sub[1])
        if not messages:
            # --amend --no-edit etc.: mensagem existente, nada para validar.
            continue
        stripped = messages[0].strip()
        header = stripped.splitlines()[0] if stripped else ""
        if not _CONVENTIONAL_HEADER.match(header):
            return (
                "mensagem de commit fora do padrao Conventional Commits "
                f"(`<tipo>(escopo): descricao`, tipos: {', '.join(CONVENTIONAL_TYPES)}). "
                f"Recebido: `{header[:80]}`"
            )
    return None


def _segment_violation(tokens: list[str]) -> str | None:
    program = _program(tokens)
    if program == "npm" and len(tokens) > 1 and tokens[1] in {"publish", "version", "unpublish"}:
        return "publicacao/versao npm e' feita pelo semantic-release no GitHub Actions"
    if program == "gh" and len(tokens) > 2 and tokens[1] == "release":
        if tokens[2] in {"create", "delete", "upload", "edit"} and any(
            _VERSION_TAG.match(t) for t in tokens[3:]
        ):
            return "releases vX.Y.Z sao criadas pelo semantic-release (so' `rag-base` e' manual)"
    if program == "git":
        sub = _git_subcommand(tokens)
        if sub is None:
            return None
        name, args = sub
        if name == "tag" and any(_VERSION_TAG.match(a) for a in args):
            return "tags vX.Y.Z sao criadas pelo semantic-release no GitHub Actions"
        if name == "push" and (
            any(a in {"--tags", "--follow-tags"} for a in args)
            or any(_VERSION_REFSPEC.search(a) for a in args if not a.startswith("-"))
        ):
            return "tags vX.Y.Z sao criadas e enviadas pelo semantic-release"
    return None


def manual_release_violation(cmd: str) -> str | None:
    """Motivo do bloqueio se o comando versiona/publica por fora do CI."""
    segments = _segments(cmd)
    if segments is None:
        return _UNPARSEABLE if _mentions_release_tools(cmd) else None
    for tokens in segments:
        reason = _segment_violation(tokens)
        if reason:
            return reason
    return None


__all__ = [
    "CONVENTIONAL_TYPES",
    "commit_message_violation",
    "manual_release_violation",
]
