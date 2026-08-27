"""Validacao estrutural do agente `@deployer` (PLAN_SPRINT18 / Task 2.1).

Sprint 18 — agent Deployer (substituto do CI). Cobre:

- Arquivo existe em ``.opencode/agent/deployer.md`` (singular; canonico
  pos-Sprint 11 D.1).
- Frontmatter YAML valido entre ``---``.
- Campos canonicos: ``name: deployer``, ``mode: primary``, ``model``.
- ``permission.edit: deny`` (defesa em profundidade — deployer NAO
  altera arquivos do projeto).
- ``permission.task/skill/todowrite/webfetch: deny`` (escopo restrito).
- ``permission.read/bash/glob/grep/list: allow`` (escopo minimo necessario).
- ``permission.external_directory: deny`` (deployer NAO sai do workspace).
- Corpo declara escopo canonico (git push/tag/branch + npm publish +
  gh release) e gate humano antes de acoes destrutivas.
- Corpo referencia os 3 hooks em ``.opencode/hooks/deployer/``.

Precedente estrutural: ``tests/unit/test_dev_agent_definition.py`` (Sprint 10)
e ``tests/unit/test_code_reviewer_definition.py`` (Sprint 9).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

AGENT_FILE: Path = (
    Path(__file__).resolve().parents[2] / ".opencode" / "agent" / "deployer.md"
)


@pytest.fixture(scope="module")
def agent_text() -> str:
    assert AGENT_FILE.exists(), f"Arquivo {AGENT_FILE} nao existe"
    return AGENT_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def frontmatter(agent_text: str) -> str:
    parts = agent_text.split("---", 2)
    assert len(parts) >= 3, "Arquivo deve ter frontmatter YAML entre ---"
    return parts[1]


def test_agent_file_exists() -> None:
    assert AGENT_FILE.exists(), (
        f"Definicao do deployer esperada em {AGENT_FILE}; nao encontrada. "
        "Crie `.opencode/agent/deployer.md` (PLAN_SPRINT18 Task 2.1)."
    )


def test_frontmatter_yaml_is_valid(agent_text: str) -> None:
    import yaml
    parts = agent_text.split("---", 2)
    yaml.safe_load(parts[1])


def test_frontmatter_contains_name_deployer(frontmatter: str) -> None:
    assert re.search(r"^name:\s*deployer\s*$", frontmatter, re.MULTILINE), (
        f"frontmatter deve conter 'name: deployer'. Recebido:\n{frontmatter}"
    )


def test_frontmatter_contains_mode_primary(frontmatter: str) -> None:
    """`mode: primary` expoe `@deployer` no menu principal do opencode.

    Mesma convencao aplicada a `@dev` em Sprint 14 e `@code-reviewer` em
    Sprint 9. Slash command `/deploy` continua invocando `deployer`
    explicitamente via frontmatter, entao a promocao a primary NAO
    quebra o pipeline.
    """
    assert re.search(r"^mode:\s*primary\s*$", frontmatter, re.MULTILINE), (
        f"frontmatter deve conter 'mode: primary'. Recebido:\n{frontmatter}"
    )


def test_frontmatter_model_is_declared(frontmatter: str) -> None:
    """Mesmo placeholder `PROVIDER/MiniMax-M3` e' aceitavel."""
    assert re.search(r"^model:\s*\S+/\S+\s*$", frontmatter, re.MULTILINE), (
        f"frontmatter deve conter 'model: PROVIDER/MiniMax-M3'. "
        f"Recebido:\n{frontmatter}"
    )


def test_frontmatter_permission_denies_edit(frontmatter: str) -> None:
    """`permission.edit: deny` e' a barreira principal do deployer.

    Deployer NAO altera arquivos do projeto. Faz apenas operacoes
    remotas via Bash (git push, npm publish, gh release). Defesa em
    profundidade contra bypass via Bash + redirecionamento.
    """
    assert re.search(r"^\s*edit:\s*deny\s*$", frontmatter, re.MULTILINE), (
        f"permission.edit deve ser 'deny' (deployer NAO edita). "
        f"Recebido:\n{frontmatter}"
    )


def test_frontmatter_permission_denies_task(frontmatter: str) -> None:
    """`permission.task: deny` impede o deployer de sub-delegar."""
    assert re.search(r"^\s*task:\s*deny\s*$", frontmatter, re.MULTILINE), (
        f"permission.task deve ser 'deny' (deployer NAO delega). "
        f"Recebido:\n{frontmatter}"
    )


def test_frontmatter_permission_denies_skill(frontmatter: str) -> None:
    """`permission.skill: deny` impede o deployer de carregar skill domain."""
    assert re.search(r"^\s*skill:\s*deny\s*$", frontmatter, re.MULTILINE), (
        f"permission.skill deve ser 'deny'. Recebido:\n{frontmatter}"
    )


def test_frontmatter_permission_denies_todowrite(frontmatter: str) -> None:
    """`permission.todowrite: deny` — fluxo de deploy e' curto, sem TODO."""
    assert re.search(r"^\s*todowrite:\s*deny\s*$", frontmatter, re.MULTILINE), (
        f"permission.todowrite deve ser 'deny'. Recebido:\n{frontmatter}"
    )


def test_frontmatter_permission_denies_webfetch(frontmatter: str) -> None:
    """`permission.webfetch: deny` — deployer NAO consulta web."""
    assert re.search(r"^\s*webfetch:\s*deny\s*$", frontmatter, re.MULTILINE), (
        f"permission.webfetch deve ser 'deny'. Recebido:\n{frontmatter}"
    )


def test_frontmatter_permission_denies_external_directory(frontmatter: str) -> None:
    """`permission.external_directory: deny` impede escrita fora do workspace."""
    assert re.search(
        r"^\s*external_directory:\s*deny\s*$", frontmatter, re.MULTILINE
    ), (
        f"permission.external_directory deve ser 'deny'. "
        f"Recebido:\n{frontmatter}"
    )


def test_frontmatter_permission_allows_read(frontmatter: str) -> None:
    """`permission.read: allow` — deployer precisa ler (git status, etc.)."""
    assert re.search(r"^\s*read:\s*allow\s*$", frontmatter, re.MULTILINE), (
        f"permission.read deve ser 'allow'. Recebido:\n{frontmatter}"
    )


def test_frontmatter_permission_allows_bash(frontmatter: str) -> None:
    """`permission.bash: allow` — deployer roda git/npm/gh via Bash.

    O hook ``pre_tool_use.py`` do deployer implementa allow list
    explicita + block list de defesa em profundidade.
    """
    assert re.search(r"^\s*bash:\s*allow\s*$", frontmatter, re.MULTILINE), (
        f"permission.bash deve ser 'allow'. Recebido:\n{frontmatter}"
    )


def test_frontmatter_permission_allows_glob(frontmatter: str) -> None:
    """`permission.glob: allow` — deployer inspeciona working tree."""
    assert re.search(r"^\s*glob:\s*allow\s*$", frontmatter, re.MULTILINE), (
        f"permission.glob deve ser 'allow'. Recebido:\n{frontmatter}"
    )


def test_frontmatter_permission_allows_grep(frontmatter: str) -> None:
    """`permission.grep: allow` — deployer busca em logs e configs."""
    assert re.search(r"^\s*grep:\s*allow\s*$", frontmatter, re.MULTILINE), (
        f"permission.grep deve ser 'allow'. Recebido:\n{frontmatter}"
    )


def test_frontmatter_permission_allows_list(frontmatter: str) -> None:
    """`permission.list: allow` — deployer lista diretorios."""
    assert re.search(r"^\s*list:\s*allow\s*$", frontmatter, re.MULTILINE), (
        f"permission.list deve ser 'allow'. Recebido:\n{frontmatter}"
    )


def test_body_declares_scope_git(agent_text: str) -> None:
    """Corpo declara escopo canonico: git push/pull/tag/branch/remote."""
    for term in ("git push", "git tag", "git pull", "git remote"):
        assert term in agent_text, (
            f"Corpo do deployer deve mencionar '{term}' (escopo canonico). "
            f"Recebido (primeiros 500 chars):\n{agent_text[:500]}"
        )


def test_body_declares_scope_npm(agent_text: str) -> None:
    """Corpo declara escopo canonico: npm publish/login/dist-tag."""
    for term in ("npm publish", "npm login", "npm dist-tag"):
        assert term in agent_text, (
            f"Corpo do deployer deve mencionar '{term}' (escopo canonico). "
            f"Recebido (primeiros 500 chars):\n{agent_text[:500]}"
        )


def test_body_declares_scope_gh_release(agent_text: str) -> None:
    """Corpo declara escopo canonico: gh release create/delete/upload."""
    assert "gh release" in agent_text, (
        "Corpo do deployer deve mencionar 'gh release' (escopo canonico)."
    )


def test_body_documents_human_gate(agent_text: str) -> None:
    """Corpo documenta gate humano antes de acoes destrutivas.

    Acoes destrutivas: `--npm` (publica no registry), `--release`
    (cria release no GitHub), `--tag` (cria tag que sera' pushed).
    Gate humano: pedir confirmacao explicita antes de cada.
    """
    text_lower = agent_text.lower()
    assert "humano" in text_lower or "human" in text_lower, (
        "Corpo deve mencionar gate humano (deployer pede confirmacao)."
    )
    assert "confirm" in text_lower or "aprov" in text_lower, (
        "Corpo deve mencionar confirmacao/aprovacao antes de acoes destrutivas."
    )


def test_body_references_pre_tool_use_hook(agent_text: str) -> None:
    """Corpo referencia o hook ``pre_tool_use.py`` do deployer."""
    assert ".opencode/hooks/deployer/pre_tool_use.py" in agent_text, (
        "Corpo deve referenciar `.opencode/hooks/deployer/pre_tool_use.py` "
        "(defesa em profundidade: allow list + block list)."
    )


def test_body_references_post_tool_use_hook(agent_text: str) -> None:
    """Corpo referencia o hook ``post_tool_use.py`` do deployer."""
    assert ".opencode/hooks/deployer/post_tool_use.py" in agent_text, (
        "Corpo deve referenciar `.opencode/hooks/deployer/post_tool_use.py` "
        "(observer)."
    )


def test_body_references_stop_hook(agent_text: str) -> None:
    """Corpo referencia o hook ``stop.py`` do deployer."""
    assert ".opencode/hooks/deployer/stop.py" in agent_text, (
        "Corpo deve referenciar `.opencode/hooks/deployer/stop.py` "
        "(exit 0 sem pytest e sem RAG capture)."
    )


def test_body_states_only_deployer_can_push(agent_text: str) -> None:
    """Corpo explicita que apenas o `@deployer` pode fazer push/publish.

    Diferenca essencial vs `@dev` e `@code-reviewer`:
    - `@dev` BLOQUEIA `git push` em `pre_tool_use.py`.
    - `@code-reviewer` tem `permission.edit: deny` (read-only).
    - `@deployer` ALLOW `git push` (allow list explicita).
    """
    text_lower = agent_text.lower()
    assert "deployer" in text_lower and (
        "apenas" in text_lower or "so' " in text_lower or "somente" in text_lower
        or "only" in text_lower
    ), (
        "Corpo deve explicitar que apenas @deployer pode fazer push/publish."
    )


def test_body_documents_not_in_scope(agent_text: str) -> None:
    """Corpo explicita o que NAO esta' em escopo do deployer."""
    text_lower = agent_text.lower()
    # NAO edita arquivos
    assert "edit" in text_lower and (
        "nao" in text_lower or "not" in text_lower or "negad" in text_lower
        or "denied" in text_lower or "deny" in text_lower
    ), (
        "Corpo deve explicitar que deployer NAO edita arquivos."
    )