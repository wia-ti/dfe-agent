"""Gate anti-regressao: CI foi REMOVIDO em Sprint 18 (PLAN_SPRINT18 / Task 2.7).

Cobre:

- Os 3 arquivos em ``.github/workflows/`` NAO existem mais.
- Diretorio ``.github/workflows/`` pode nao existir (limpo) OU existir
  vazio (gate tolerante a criacao futura de workflows novos).
- AGENTS.md NAO referencia os workflows removidos.
- opencode.json NAO referencia os workflows removidos.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR: Path = PROJECT_ROOT / ".github" / "workflows"


REMOVED_WORKFLOWS: tuple[str, ...] = (
    "test-npm-package.yml",
    "publish-npm.yml",
    "publish-base.yml",
)


@pytest.mark.parametrize("filename", REMOVED_WORKFLOWS)
def test_workflow_file_removed(filename: str) -> None:
    """Os 3 workflows NAO devem existir (Sprint 18 removeu o CI)."""
    p: Path = WORKFLOWS_DIR / filename
    assert not p.exists(), (
        f"Workflow {filename} deveria ter sido removido em Sprint 18 "
        f"(CI foi descontinuado). Path: {p}"
    )


def test_workflows_dir_empty_or_absent() -> None:
    """Diretorio workflows deve estar ausente OU vazio.

    Gate tolerante a criacao futura de workflows novos.
    """
    if not WORKFLOWS_DIR.exists():
        return  # ausencia total
    contents: list[Path] = [
        p for p in WORKFLOWS_DIR.iterdir()
        if p.is_file() and not p.name.startswith(".")
    ]
    assert not any(p.name in REMOVED_WORKFLOWS for p in contents), (
        f"Workflows removidos em Sprint 18 NAO devem voltar. "
        f"Encontrados: {[p.name for p in contents if p.name in REMOVED_WORKFLOWS]}"
    )


def test_agents_md_does_not_reference_removed_workflows() -> None:
    """AGENTS.md NAO deve mencionar os workflows removidos como ancora canonica.

    Mencoes em contexto narrativo de remocao (Sprint 18) sao permitidas:
    o bloco "Decisoes resolvidas (Sprint 18)" pode listar os 3 nomes para
    documentar o que foi removido. Este gate detecta apenas mencoes
    FORA desse contexto narrativo (ex.: link em secao canonica).
    """
    agents_md: Path = PROJECT_ROOT / "AGENTS.md"
    if not agents_md.exists():
        pytest.skip("AGENTS.md nao existe")
    text: str = agents_md.read_text(encoding="utf-8")
    # Bloco narrativo de remocao Sprint 18: ignorado pelo gate.
    sprint18_block_match = re.search(
        r"## Decisoes resolvidas \(Sprint 18\).*?(?=\n## |\Z)",
        text,
        re.DOTALL,
    )
    text_outside_sprint18 = text
    if sprint18_block_match:
        text_outside_sprint18 = (
            text[: sprint18_block_match.start()] + text[sprint18_block_match.end() :]
        )
    for wf in REMOVED_WORKFLOWS:
        assert wf not in text_outside_sprint18, (
            f"AGENTS.md NAO deve mencionar `{wf}` fora do bloco "
            f"`Decisoes resolvidas (Sprint 18)` (gate canonico). "
            f"Texto ofensivo em: "
            f"{text_outside_sprint18[max(0, text_outside_sprint18.find(wf)-50):text_outside_sprint18.find(wf)+100]}"
        )


def test_opencode_json_does_not_reference_removed_workflows() -> None:
    """opencode.json NAO deve mencionar os workflows removidos."""
    config: Path = PROJECT_ROOT / "opencode.json"
    if not config.exists():
        pytest.skip("opencode.json nao existe")
    text: str = config.read_text(encoding="utf-8")
    for wf in REMOVED_WORKFLOWS:
        assert wf not in text, (
            f"opencode.json NAO deve mencionar `{wf}` (removido em Sprint 18)."
        )


def test_plan_md_marks_ci_as_removed() -> None:
    """PLAN.md deve marcar CI como removido (gate positivo).

    Se a sprint 18 ja' atualizou PLAN.md, este teste passa. Se nao, falha
    com mensagem clara apontando o que atualizar.
    """
    plan: Path = PROJECT_ROOT / "PLAN.md"
    if not plan.exists():
        pytest.skip("PLAN.md nao existe")
    text: str = plan.read_text(encoding="utf-8")
    # Procura qualquer mencao a "CI removido" / "CI descontinuado" / "Sprint 18"
    pattern = re.compile(
        r"(CI\s+removido|CI\s+descontinuado|Sprint\s*18|Deployer)",
        re.IGNORECASE,
    )
    assert pattern.search(text), (
        "PLAN.md deve documentar que CI foi removido em Sprint 18 "
        "(gate positivo). Se esta' em outro plano, ajuste o teste."
    )