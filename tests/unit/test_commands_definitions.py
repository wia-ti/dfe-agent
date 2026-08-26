"""Validacao estrutural dos 3 slash commands: `/feature`, `/bug`, `/duvida` (PLAN_SPRINT10 D).

Cobre:

- Cada command existe em ``.opencode/command/<name>.md``.
- Cada command tem frontmatter YAML valido.
- Cada command declara ``agent: dev`` (NUNCA ``build`` nem ``plan``).
- Cada command tem o padrao **RAG antes** (Fase 0 invoca ``search.ts``)
  e **RAG depois** (Fase final invoca ``embed.ts``).
- `/bug` tem gate de aprovacao humana entre investigacao e correcao.
- `/duvida` declara read-only por contrato.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

COMMANDS_DIR: Path = (
    Path(__file__).resolve().parents[2] / ".opencode" / "command"
)


def _read(name: str) -> str:
    p: Path = COMMANDS_DIR / f"{name}.md"
    assert p.exists(), f"Arquivo {p} nao existe"
    return p.read_text(encoding="utf-8")


def _frontmatter(text: str) -> str:
    parts = text.split("---", 2)
    assert len(parts) >= 3, f"Arquivo deve ter frontmatter YAML: {text[:100]!r}"
    return parts[1]


@pytest.mark.parametrize(
    "name", ["feature", "bug", "duvida"],
    ids=["feature", "bug", "duvida"],
)
def test_command_file_exists(name: str) -> None:
    p: Path = COMMANDS_DIR / f"{name}.md"
    assert p.exists(), f"Command `{name}` nao encontrado em {p}"


@pytest.mark.parametrize("name", ["feature", "bug", "duvida"])
def test_command_frontmatter_yaml_is_valid(name: str) -> None:
    import yaml
    text = _read(name)
    yaml.safe_load(_frontmatter(text))


@pytest.mark.parametrize("name", ["feature", "bug", "duvida"])
def test_command_uses_dev_agent(name: str) -> None:
    """PLAN_SPRINT10 D: os 3 commands invocam `agent: dev` (NAO `build`/`plan`)."""
    fm = _frontmatter(_read(name))
    assert re.search(r"^agent:\s*dev\s*$", fm, re.MULTILINE), (
        f"`/{name}` deve declarar `agent: dev` no frontmatter (PLAN_SPRINT10). "
        f"Recebido:\n{fm}"
    )


@pytest.mark.parametrize("name", ["build", "plan"])
def test_no_command_references_legacy_agent(name: str) -> None:
    """PLAN_SPRINT10 E.4: nenhum command referencia `agent: build` ou `agent: plan`."""
    for cmd_file in COMMANDS_DIR.glob("*.md"):
        text = cmd_file.read_text(encoding="utf-8")
        assert re.search(
            rf"^agent:\s*{re.escape(name)}\s*$", text, re.MULTILINE
        ) is None, (
            f"Command `{cmd_file.name}` ainda referencia `agent: {name}` "
            "(removido na PLAN_SPRINT10)."
        )


@pytest.mark.parametrize("name", ["feature", "bug", "duvida"])
def test_command_calls_search_ts_in_phase_zero(name: str) -> None:
    """RAG antes: Fase 0 invoca `search.ts` com `-a dev` para injerir contexto.

    Sprint 12 (B12.4): scripts TS migraram de ``.claude/scripts/`` para
    ``.opencode/rag/``. Comando deve apontar para o novo path.
    """
    text = _read(name)
    assert "search.ts" in text, (
        f"`/{name}` deve invocar `.opencode/rag/search.ts` na Fase 0."
    )
    assert ".opencode/rag/search.ts" in text, (
        f"`/{name}` deve apontar para `.opencode/rag/search.ts` "
        f"(Sprint 12 B12.4); obtido texto sem o path canonico."
    )
    assert ".claude/scripts/search.ts" not in text, (
        f"`/{name}` NAO deve apontar para `.claude/scripts/search.ts` "
        f"(path legado pre-Sprint 12)."
    )
    assert re.search(r"-a\s+dev", text), (
        f"`/{name}` deve chamar `search.ts` com `-a dev` (slug canonico)."
    )


@pytest.mark.parametrize("name", ["feature", "bug", "duvida"])
def test_command_calls_embed_ts_in_final_phase(name: str) -> None:
    """RAG depois: Fase final invoca `embed.ts` (sincrono) com o .md gerado.

    Sprint 12 (B12.4): scripts TS migraram para ``.opencode/rag/``.
    """
    text = _read(name)
    assert "embed.ts" in text, (
        f"`/{name}` deve invocar `.opencode/rag/embed.ts` na Fase final."
    )
    assert ".opencode/rag/embed.ts" in text, (
        f"`/{name}` deve apontar para `.opencode/rag/embed.ts` "
        f"(Sprint 12 B12.4)."
    )
    assert ".claude/scripts/embed.ts" not in text, (
        f"`/{name}` NAO deve apontar para `.claude/scripts/embed.ts` "
        f"(path legado)."
    )
    # Padrao canonico: `npx tsx .opencode/rag/embed.ts --file <md>`
    assert re.search(r"embed\.ts\s+--file", text), (
        f"`/{name}` deve rodar `embed.ts --file <md>` (sincrono, nao fire-and-forget)."
    )


def test_bug_command_has_human_approval_gate() -> None:
    """/bug tem gate explicito entre investigacao e correcao."""
    text = _read("bug")
    assert "APROVACAO" in text.upper() or "aprovacao" in text.lower(), (
        "/bug deve ter gate de aprovacao humana explicito."
    )
    assert "read-only" in text.lower() or "read only" in text.lower(), (
        "/bug deve explicitar que a investigacao e' read-only."
    )
    assert "Posso prosseguir" in text or "posso prosseguir" in text.lower(), (
        "/bug deve pedir aprovacao explicita antes da correcao."
    )


def test_duvida_command_declares_readonly_contract() -> None:
    """/duvida e' read-only por contrato."""
    text = _read("duvida")
    assert re.search(r"read[-\s]?only\s+por\s+contrato", text, re.IGNORECASE), (
        "/duvida deve declarar 'read-only por contrato' explicitamente."
    )
    assert "file_path:line_number" in text or "file_path:linha" in text.lower(), (
        "/duvida deve exigir citacao de evidencias via `file_path:line_number`."
    )


def test_feature_command_still_uses_tdd_loop() -> None:
    """/feature continua com ciclo TDD canonico (regressao nao pode quebrar)."""
    text = _read("feature")
    assert "TDD" in text, "/feature deve preservar o ciclo TDD."
    assert "code-reviewer" in text, "/feature deve invocar code-reviewer."
    assert "code reviewer" in text.lower() or "code-reviewer" in text, (
        "/feature deve invocar code-reviewer."
    )
