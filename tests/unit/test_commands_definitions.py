"""Validacao estrutural dos 3 slash commands: `/feature`, `/bug`, `/duvida` (PLAN_SPRINT10 D).

Cobre:

- Cada command existe em ``.claude/commands/<name>.md`` (``/deploy`` e' a
  skill ``.claude/skills/deploy/SKILL.md``, que roda no subagent ``deployer``).
- Cada command tem frontmatter YAML valido.
- ``/feature``, ``/bug`` e ``/duvida`` rodam na sessao principal (papel
  ``@dev``): sem ``agent:``/``context: fork`` no frontmatter.
- Cada command tem o padrao **RAG antes** (Fase 0 invoca ``search.ts``)
  e **RAG depois** (Fase final invoca ``embed.ts``).
- `/bug` tem gate de aprovacao humana entre investigacao e correcao.
- `/duvida` declara read-only por contrato.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

HARNESS_DIR: Path = Path(__file__).resolve().parents[2] / ".claude"
COMMANDS_DIR: Path = HARNESS_DIR / "commands"
DEPLOY_SKILL: Path = HARNESS_DIR / "skills" / "deploy" / "SKILL.md"


def _path(name: str) -> Path:
    return DEPLOY_SKILL if name == "deploy" else COMMANDS_DIR / f"{name}.md"


def _read(name: str) -> str:
    p: Path = _path(name)
    assert p.exists(), f"Arquivo {p} nao existe"
    return p.read_text(encoding="utf-8")


def _frontmatter(text: str) -> str:
    parts = text.split("---", 2)
    assert len(parts) >= 3, f"Arquivo deve ter frontmatter YAML: {text[:100]!r}"
    return parts[1]


def _read_if_exists(name: str) -> str | None:
    """Le command file se existir (helper para tests condicionais)."""
    p: Path = COMMANDS_DIR / f"{name}.md"
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "name", ["feature", "bug", "duvida"],
    ids=["feature", "bug", "duvida"],
)
def test_command_file_exists(name: str) -> None:
    p: Path = COMMANDS_DIR / f"{name}.md"
    assert p.exists(), f"Command `{name}` nao encontrado em {p}"


def test_deploy_command_file_exists() -> None:
    """`/deploy` e' a skill `.claude/skills/deploy/SKILL.md`."""
    assert DEPLOY_SKILL.exists(), f"Skill `deploy` nao encontrada em {DEPLOY_SKILL}."


def test_deploy_command_frontmatter_yaml_is_valid() -> None:
    """Frontmatter YAML do `/deploy` deve ser valido."""
    import yaml
    text = _read("deploy")
    yaml.safe_load(_frontmatter(text))


def test_deploy_command_uses_deployer_agent() -> None:
    """`/deploy` roda no subagent `deployer` (`context: fork` + `agent: deployer`)."""
    import yaml
    fm = yaml.safe_load(_frontmatter(_read("deploy")))
    assert fm.get("context") == "fork", f"`/deploy` deve usar `context: fork`: {fm}"
    assert fm.get("agent") == "deployer", f"`/deploy` deve usar `agent: deployer`: {fm}"
    assert fm.get("disable-model-invocation") is True, (
        "`/deploy` so' pode ser disparado pelo humano (disable-model-invocation)."
    )


@pytest.mark.parametrize("name", ["feature", "bug", "duvida"])
def test_command_frontmatter_yaml_is_valid(name: str) -> None:
    import yaml
    text = _read(name)
    yaml.safe_load(_frontmatter(text))


@pytest.mark.parametrize("name", ["feature", "bug", "duvida"])
def test_command_uses_dev_agent(name: str) -> None:
    """Os 3 commands rodam na sessao principal, que faz o papel do `@dev`."""
    text = _read(name)
    fm = _frontmatter(text)
    assert not re.search(r"^(agent|context):", fm, re.MULTILINE), (
        f"`/{name}` deve rodar na sessao principal (sem agent/context). Recebido:\n{fm}"
    )
    assert "`@dev`" in text, f"`/{name}` deve declarar o papel `@dev`."


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
    ``.claude/rag/``. Comando deve apontar para o novo path.
    """
    text = _read(name)
    assert "search.ts" in text, (
        f"`/{name}` deve invocar `.claude/rag/search.ts` na Fase 0."
    )
    assert ".claude/rag/search.ts" in text, (
        f"`/{name}` deve apontar para `.claude/rag/search.ts` "
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

    Sprint 12 (B12.4): scripts TS migraram para ``.claude/rag/``.
    """
    text = _read(name)
    assert "embed.ts" in text, (
        f"`/{name}` deve invocar `.claude/rag/embed.ts` na Fase final."
    )
    assert ".claude/rag/embed.ts" in text, (
        f"`/{name}` deve apontar para `.claude/rag/embed.ts` "
        f"(Sprint 12 B12.4)."
    )
    assert ".claude/scripts/embed.ts" not in text, (
        f"`/{name}` NAO deve apontar para `.claude/scripts/embed.ts` "
        f"(path legado)."
    )
    # Padrao canonico: `npx tsx .claude/rag/embed.ts --file <md>`
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


# ============================================================
# /deploy — Sprint 18 (PLAN_SPRINT18 D18.4)
# ============================================================


def test_deploy_command_calls_search_ts_with_deployer() -> None:
    """RAG antes: `/deploy` invoca `search.ts` com `-a deployer`.

    Sprint 18: slug canonico do agent e' `deployer`, NAO `dev`.
    """
    text = _read("deploy")
    assert ".claude/rag/search.ts" in text, (
        "`/deploy` deve invocar `.claude/rag/search.ts` na Fase 0."
    )
    assert ".claude/scripts/search.ts" not in text, (
        "`/deploy` NAO deve apontar para `.claude/scripts/search.ts` "
        "(path legado pre-Sprint 12)."
    )
    assert re.search(r"-a\s+deployer", text), (
        "`/deploy` deve chamar `search.ts` com `-a deployer` "
        "(slug canonico Sprint 18)."
    )


def test_deploy_command_calls_embed_ts_in_final_phase() -> None:
    """RAG depois: `/deploy` invoca `embed.ts` (sincrono) na fase final."""
    text = _read("deploy")
    assert ".claude/rag/embed.ts" in text, (
        "`/deploy` deve invocar `.claude/rag/embed.ts` na fase final."
    )
    assert re.search(r"embed\.ts\s+--file", text), (
        "`/deploy` deve rodar `embed.ts --file <md>` (sincrono)."
    )


def test_deploy_command_documents_modes() -> None:
    """Sprint 20: `/deploy` tem 2 modos (bare e `--base`); tag/npm/release sao do semantic-release."""
    text = _read("deploy")
    assert "--base" in text, "`/deploy` deve documentar o modo `--base` (base RAG na release)."
    assert "rag-base" in text, "`/deploy --base` publica na release rolante `rag-base`."
    assert "semantic-release" in text, (
        "`/deploy` deve explicar que tag/npm/release vX.Y.Z sao do semantic-release."
    )


def test_deploy_command_has_human_gate() -> None:
    """`/deploy` tem gate humano explicito antes de acoes destrutivas."""
    text = _read("deploy")
    text_lower = text.lower()
    assert "humano" in text_lower or "human" in text_lower, (
        "`/deploy` deve mencionar gate humano (deployer pede confirmacao)."
    )
    assert "confirm" in text_lower or "aprov" in text_lower, (
        "`/deploy` deve exigir confirmacao/aprovacao antes de acoes destrutivas."
    )
    # Acoes destrutivas devem ter gate explicito
    assert "--base" in text, "`/deploy` deve mencionar a flag destrutiva `--base`."


def test_no_command_references_legacy_agent_with_deployer_substring() -> None:
    """Gate anti-regressao: nenhum command fora `/deploy` usa `agent: deployer`."""
    for cmd_file in COMMANDS_DIR.glob("*.md"):
        if cmd_file.name == "deploy.md":
            continue  # deploy.md e' o legitimo
        text = cmd_file.read_text(encoding="utf-8")
        assert not re.search(
            r"^agent:\s*deployer\s*$", text, re.MULTILINE
        ), (
            f"Command `{cmd_file.name}` referencia `agent: deployer` "
            "mas deployer e' exclusivo de `/deploy`."
        )
