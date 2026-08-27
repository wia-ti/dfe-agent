"""Testes unit do hook ``.opencode/hooks/deployer/pre_tool_use.py`` (PLAN_SPRINT18 / Task 2.2).

Cobre:

- Allow list para git push/tag/branch/remote/fetch/pull.
- Allow list para npm publish/login/dist-tag/view.
- Allow list para gh release create/delete/upload.
- Allow list para npx dfe-agent *.
- Allow list para escape hatch `npx tsx .opencode/rag/embed.ts --file`.
- Block list para Write/Edit/MultiEdit/NotebookEdit (defesa em profundidade).
- Block list para rm -rf, sed -i, redirecionamento `>`.
- Block list para curl, wget, pip install.
- Block list para python -m src.{collector --once, indexer.ingest,
  ragctl migrate/reindex/benchmark}.
- Log escrito em ``storage/agent_hooks.log``.

Estrategia: ``subprocess.run`` com ``sys.executable`` (padrao de
``tests/integration/test_agent_dispatch.py`` e de
``tests/unit/hooks/test_dev_pre_tool_use.py``).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]
HOOK_SCRIPT: Path = (
    PROJECT_ROOT / ".opencode" / "hooks" / "deployer" / "pre_tool_use.py"
)
LOG_PATH: Path = PROJECT_ROOT / "storage" / "agent_hooks.log"


def _run_hook(payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, "DFE_ACTIVE_AGENT": "deployer"},
        check=False,
        cwd=str(PROJECT_ROOT),
        timeout=30,
    )
    return proc


def _run_hook_for_tool(
    tool: str, args: dict[str, object]
) -> subprocess.CompletedProcess[str]:
    """Helper para tools que nao sao Bash (Write, Edit, etc.)."""
    return _run_hook({"tool_name": tool, "tool_input": args})


def _truncate_log() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("", encoding="utf-8")


# ============================================================
# ALLOW LIST — git push / pull / tag / branch / remote
# ============================================================


@pytest.mark.parametrize(
    "cmd",
    [
        "git push origin main",
        "git push origin feature/foo",
        "git push",
        "git push --tags",
        "git push origin v0.1.6",
        "git push origin --delete v0.1.5",
        "git push origin :refs/tags/v0.1.5",
        "git push origin :feature/legacy",
        "git pull --rebase",
        "git pull --rebase origin main",
        "git fetch origin",
        "git fetch --all",
        "git tag v0.1.6",
        "git tag -d v0.1.5",
        "git tag -a v0.1.6 -m 'release 0.1.6'",
        "git remote -v",
        "git remote set-url origin git@github.com:wia-ti/dfe-agent.git",
        "git branch -d feature/foo",
        "git branch -D feature/legacy",
        "git push origin --delete feature/legacy",
        "git push origin :feature/legacy",
    ],
    ids=[
        "git_push_origin_main",
        "git_push_origin_feature",
        "git_push_bare",
        "git_push_tags",
        "git_push_origin_tag",
        "git_push_delete_tag",
        "git_push_delete_refs_tag",
        "git_push_delete_branch",
        "git_pull_rebase",
        "git_pull_rebase_origin",
        "git_fetch_origin",
        "git_fetch_all",
        "git_tag",
        "git_tag_d",
        "git_tag_a_annotated",
        "git_remote_v",
        "git_remote_set_url",
        "git_branch_d",
        "git_branch_D",
        "git_push_delete_branch_long",
        "git_push_delete_branch_colon",
    ],
)
def test_allows_git_commands(cmd: str) -> None:
    proc = _run_hook({"tool_name": "Bash", "tool_input": {"command": cmd}})
    assert proc.returncode == 0, (
        f"`{cmd}` deveria ser permitido (allow list do deployer); "
        f"obtido rc={proc.returncode}, stderr={proc.stderr!r}"
    )


# ============================================================
# ALLOW LIST — npm
# ============================================================


@pytest.mark.parametrize(
    "cmd",
    [
        "npm login",
        "npm publish --access public --provenance",
        "npm publish",
        "npm view @wiati/dfe-agent",
        "npm view @wiati/dfe-agent versions",
        "npm dist-tag add @wiati/dfe-agent@0.1.6 latest",
        "npm dist-tag ls @wiati/dfe-agent",
        "npm whoami",
        "npm pack",
    ],
    ids=[
        "npm_login",
        "npm_publish_access_public",
        "npm_publish_bare",
        "npm_view_package",
        "npm_view_versions",
        "npm_dist_tag_add",
        "npm_dist_tag_ls",
        "npm_whoami",
        "npm_pack",
    ],
)
def test_allows_npm_commands(cmd: str) -> None:
    proc = _run_hook({"tool_name": "Bash", "tool_input": {"command": cmd}})
    assert proc.returncode == 0, (
        f"`{cmd}` deveria ser permitido (allow list do deployer); "
        f"obtido rc={proc.returncode}, stderr={proc.stderr!r}"
    )


# ============================================================
# ALLOW LIST — gh release
# ============================================================


@pytest.mark.parametrize(
    "cmd",
    [
        "gh release create v1.2.5 --notes 'changelog aqui'",
        "gh release create v0.0.1-sprint17 storage/dfe.db.gz storage/dfe.db.gz.sha256",
        "gh release delete v1.2.4",
        "gh release upload v1.2.5 extra.tar.gz",
        "gh release list",
        "gh release view v1.2.5",
    ],
    ids=[
        "gh_release_create_with_notes",
        "gh_release_create_with_assets",
        "gh_release_delete",
        "gh_release_upload",
        "gh_release_list",
        "gh_release_view",
    ],
)
def test_allows_gh_release_commands(cmd: str) -> None:
    proc = _run_hook({"tool_name": "Bash", "tool_input": {"command": cmd}})
    assert proc.returncode == 0, (
        f"`{cmd}` deveria ser permitido (allow list do deployer); "
        f"obtido rc={proc.returncode}, stderr={proc.stderr!r}"
    )


# ============================================================
# ALLOW LIST — npx dfe-agent + escape hatch RAG embed
# ============================================================


@pytest.mark.parametrize(
    "cmd",
    [
        "npx dfe-agent install",
        "npx dfe-agent install --auto-setup",
        "npx dfe-agent update",
        "npx dfe-agent status",
        "npx dfe-agent query 'O que e a NF-e?'",
        "npx --prefix .opencode tsx .opencode/rag/embed.ts --file .opencode/rag/knowledge/2026-08-27-dev-feature-deployer-agent.md",
        "npx --prefix .opencode tsx .opencode/rag/search.ts -q 'deployer git push' -a deployer --top-k 5",
    ],
    ids=[
        "npx_dfe_agent_install",
        "npx_dfe_agent_install_auto_setup",
        "npx_dfe_agent_update",
        "npx_dfe_agent_status",
        "npx_dfe_agent_query",
        "npx_rag_embed_file",
        "npx_rag_search_file",
    ],
)
def test_allows_npx_commands(cmd: str) -> None:
    proc = _run_hook({"tool_name": "Bash", "tool_input": {"command": cmd}})
    assert proc.returncode == 0, (
        f"`{cmd}` deveria ser permitido (allow list do deployer); "
        f"obtido rc={proc.returncode}, stderr={proc.stderr!r}"
    )


# ============================================================
# BLOCK LIST — Write/Edit/MultiEdit/NotebookEdit
# ============================================================


@pytest.mark.parametrize(
    "tool,args",
    [
        ("Write", {"file_path": "AGENTS.md", "content": "x"}),
        ("Edit", {"file_path": "AGENTS.md", "old_string": "x", "new_string": "y"}),
        ("MultiEdit", {"file_path": "AGENTS.md", "edits": []}),
        ("NotebookEdit", {"notebook_path": "foo.ipynb", "cell_id": "x"}),
    ],
    ids=["write", "edit", "multi_edit", "notebook_edit"],
)
def test_blocks_write_tools(tool: str, args: dict[str, object]) -> None:
    proc = _run_hook_for_tool(tool, args)
    assert proc.returncode == 2, (
        f"`{tool}` deveria ser bloqueado (permission.edit: deny + defesa em "
        f"profundidade); obtido rc={proc.returncode}, stderr={proc.stderr!r}"
    )


# ============================================================
# BLOCK LIST — bash destrutivo
# ============================================================


@pytest.mark.parametrize(
    "cmd",
    [
        "rm -rf node_modules",
        "rm -rf --force --recursive build",
        "sed -i 's/foo/bar/' file.txt",
        "echo 'malicious' > /etc/passwd",
        "echo 'oops' | tee file.txt",
        "cat foo.txt > bar.txt",
    ],
    ids=[
        "rm_rf",
        "rm_force_recursive",
        "sed_i",
        "redirection_to_etc",
        "pipe_tee",
        "redirection_from_cat",
    ],
)
def test_blocks_destructive_bash(cmd: str) -> None:
    proc = _run_hook({"tool_name": "Bash", "tool_input": {"command": cmd}})
    assert proc.returncode == 2, (
        f"`{cmd}` deveria ser bloqueado (defesa em profundidade); "
        f"obtido rc={proc.returncode}, stderr={proc.stderr!r}"
    )


# ============================================================
# BLOCK LIST — downloads HTTP / pip install
# ============================================================


@pytest.mark.parametrize(
    "cmd",
    [
        "curl https://example.com/file.tar.gz",
        "wget https://example.com/file.tar.gz",
        "pip install requests",
        "pip install -r requirements.txt",
        "poetry add requests",
        "poetry install",
    ],
    ids=[
        "curl",
        "wget",
        "pip_install",
        "pip_install_requirements",
        "poetry_add",
        "poetry_install",
    ],
)
def test_blocks_http_and_pip(cmd: str) -> None:
    proc = _run_hook({"tool_name": "Bash", "tool_input": {"command": cmd}})
    assert proc.returncode == 2, (
        f"`{cmd}` deveria ser bloqueado; "
        f"obtido rc={proc.returncode}, stderr={proc.stderr!r}"
    )


# ============================================================
# BLOCK LIST — pipeline RAG (mesmo gate do @dev)
# ============================================================


@pytest.mark.parametrize(
    "cmd",
    [
        "python -m src.collector --once",
        "python -m src.collector --once --portal nf-e",
        "python -m src.indexer.ingest",
        "python -m src.ragctl migrate",
        "python -m src.ragctl reindex",
        "python -m src.ragctl benchmark",
    ],
    ids=[
        "collector_once",
        "collector_once_portal",
        "indexer_ingest",
        "ragctl_migrate",
        "ragctl_reindex",
        "ragctl_benchmark",
    ],
)
def test_blocks_rag_pipeline(cmd: str) -> None:
    proc = _run_hook({"tool_name": "Bash", "tool_input": {"command": cmd}})
    assert proc.returncode == 2, (
        f"`{cmd}` deveria ser bloqueado (gate de pipeline RAG); "
        f"obtido rc={proc.returncode}, stderr={proc.stderr!r}"
    )


# ============================================================
# ALLOW LIST — escape hatches (mesmo do @dev)
# ============================================================


@pytest.mark.parametrize(
    "cmd",
    [
        "python -m src.ragctl stats",
        "python -m src.collector --diagnose-net",
    ],
    ids=["ragctl_stats", "collector_diagnose_net"],
)
def test_allows_readonly_ragctl(cmd: str) -> None:
    proc = _run_hook({"tool_name": "Bash", "tool_input": {"command": cmd}})
    assert proc.returncode == 0, (
        f"`{cmd}` deveria ser permitido (escape hatch read-only); "
        f"obtido rc={proc.returncode}, stderr={proc.stderr!r}"
    )


@pytest.mark.parametrize(
    "cmd",
    [
        "python -m src.ragctl stats > /tmp/foo.txt",
        "python -m src.collector --diagnose-net | tee /tmp/diag.txt",
        "python -m src.ragctl stats && rm -rf /tmp/danger",
    ],
    ids=[
        "ragctl_stats_with_redirection",
        "diagnose_net_with_tee",
        "ragctl_stats_with_rm_rf",
    ],
)
def test_blocks_ragctl_with_destructive_suffix(cmd: str) -> None:
    """Sprint 18 SUGESTAO 3: defesa em profundidade — ragctl read-only
    NAO deve bypassar gates de redirecionamento / rm -rf."""
    proc = _run_hook({"tool_name": "Bash", "tool_input": {"command": cmd}})
    assert proc.returncode == 2, (
        f"`{cmd}` deveria ser bloqueado (defesa em profundidade); "
        f"obtido rc={proc.returncode}, stderr={proc.stderr!r}"
    )


# ============================================================
# Pass-through para tool != Bash e tool != Write/Edit
# ============================================================


def test_allows_read_tool() -> None:
    proc = _run_hook({"tool_name": "Read", "tool_input": {"file_path": "AGENTS.md"}})
    assert proc.returncode == 0, (
        f"Read deveria ser permitido; obtido rc={proc.returncode}, "
        f"stderr={proc.stderr!r}"
    )


def test_allows_glob_tool() -> None:
    proc = _run_hook({"tool_name": "Glob", "tool_input": {"pattern": "**/*.py"}})
    assert proc.returncode == 0, (
        f"Glob deveria ser permitido; obtido rc={proc.returncode}, "
        f"stderr={proc.stderr!r}"
    )


def test_allows_grep_tool() -> None:
    proc = _run_hook({"tool_name": "Grep", "tool_input": {"pattern": "deployer"}})
    assert proc.returncode == 0, (
        f"Grep deveria ser permitido; obtido rc={proc.returncode}, "
        f"stderr={proc.stderr!r}"
    )


# ============================================================
# Log escrito em storage/agent_hooks.log
# ============================================================


def test_blocks_write_tools_log_event() -> None:
    """Bloqueios geram log_event em storage/agent_hooks.log."""
    _truncate_log()
    _run_hook_for_tool("Edit", {"file_path": "AGENTS.md", "old_string": "x", "new_string": "y"})
    log = LOG_PATH.read_text(encoding="utf-8")
    assert "deployer" in log or "pre_tool_use" in log, (
        f"Log deveria conter entrada do deployer. Obtido:\n{log}"
    )


def test_blocks_destructive_bash_log_event() -> None:
    """Comandos bash destrutivos bloqueados geram log."""
    _truncate_log()
    _run_hook({"tool_name": "Bash", "tool_input": {"command": "rm -rf build"}})
    log = LOG_PATH.read_text(encoding="utf-8")
    assert "deployer" in log or "pre_tool_use" in log, (
        f"Log deveria conter entrada do deployer. Obtido:\n{log}"
    )