"""Testes de ``.claude/hooks/_lib/release_policy.py`` (Sprint 20).

Conventional Commits obrigatorio e bloqueio de versionamento manual
(o semantic-release no GitHub Actions e' o dono das tags vX.Y.Z e do npm).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT / ".claude" / "hooks"))

from _lib.release_policy import (  # noqa: E402
    commit_message_violation,
    manual_release_violation,
)


@pytest.mark.parametrize(
    "cmd",
    [
        'git commit -m "feat(harness): semantic-release no Actions"',
        "git commit -m 'fix: corrige export'",
        'git commit -m "feat!: quebra compatibilidade"',
        'git commit -m "chore(release): 1.3.0 [skip ci]"',
        'git add -A && git commit -m "docs(agents): sprint 20"',
        'git commit -m "fix(rag): atualizar base" -m "corpo livre aqui"',
        "git commit --message='refactor(hooks): extrai politica'",
        "git commit --amend --no-edit",
        "git status",
        'git commit -m "test: cobre export" && git log -1',
    ],
)
def test_commits_validos_passam(cmd: str) -> None:
    assert commit_message_violation(cmd) is None


@pytest.mark.parametrize(
    "cmd",
    [
        'git commit -m "docs: explica npm publish"',
        'git commit -m "docs: nota sobre git tag v1.3"',
        "git push -u origin feat/v1.2-fix",
        'git commit -m "fix: a && b" && git log -1',
    ],
)
def test_texto_em_mensagem_ou_branch_nao_e_falso_positivo(cmd: str) -> None:
    assert manual_release_violation(cmd) is None
    assert commit_message_violation(cmd) is None


def test_commit_via_arquivo_e_validado(tmp_path: Path) -> None:
    ok = tmp_path / "ok.txt"
    ok.write_text("feat(x): mensagem boa\n\ncorpo", encoding="utf-8")
    bad = tmp_path / "bad.txt"
    bad.write_text("mensagem ruim", encoding="utf-8")
    assert commit_message_violation(f'git commit -F "{ok.as_posix()}"') is None
    assert commit_message_violation(f'git commit -F "{bad.as_posix()}"') is not None
    assert commit_message_violation(f'git commit --file="{bad.as_posix()}"') is not None


@pytest.mark.parametrize(
    "cmd",
    [
        'git commit -m "atualiza coisas"',
        'git -c user.name=x commit -m "sem padrao"',
        'git commit -m "wip: a && b"',
        'git add -A && git commit -m "ajuste"',
        'git commit -m "Feat: maiuscula"',
        'git commit -m "feat:sem espaco"',
        'git commit -m "wip(x): tipo invalido"',
        'git commit -am "ajustes"',
    ],
)
def test_commits_fora_do_padrao_sao_barrados(cmd: str) -> None:
    reason = commit_message_violation(cmd)
    assert reason is not None
    assert "Conventional Commits" in reason


@pytest.mark.parametrize(
    "cmd",
    [
        "npm publish",
        "npm publish --access public --provenance",
        "npm version minor",
        "npm unpublish @wiati/dfe-agent@1.0.0",
        "git tag v1.3.0",
        "git tag -a v1.3.0 -m 'x'",
        "git tag -d v1.2.5",
        "git push origin v1.3.0",
        "git push --tags",
        "git push origin :refs/tags/v1.2.5",
        "gh release create v1.3.0 --notes x",
        "gh release upload v1.2.5 storage/dfe.db.gz",
        "gh release delete v1.2.4",
        "git push --follow-tags",
        "gh release create --title x v1.3.0",
        "git -C . tag v1.3.0",
        "python -m src.ragctl stats && npm publish",
        'git commit -m "x',
    ],
)
def test_versionamento_manual_bloqueado(cmd: str) -> None:
    assert manual_release_violation(cmd) is not None


@pytest.mark.parametrize(
    "cmd",
    [
        "git push",
        "git push -u origin feat/release-semantic",
        "git push origin main",
        "git tag",
        "git tag --list",
        "gh release upload rag-base storage/dfe.db.gz storage/dfe.db.gz.sha256 --clobber",
        "gh release create rag-base --title 'Base RAG' --latest=false --notes x",
        "gh release view rag-base",
        "gh release view v1.2.5",
        "gh release list",
        "npm view @wiati/dfe-agent version",
        "npm test",
    ],
)
def test_operacoes_permitidas(cmd: str) -> None:
    assert manual_release_violation(cmd) is None
