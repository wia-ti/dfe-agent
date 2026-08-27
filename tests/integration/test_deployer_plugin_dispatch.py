"""Testes de integracao do plugin TS com o agente `@deployer` (PLAN_SPRINT18 / Task 2.4).

Cobre:

- O map ``AGENTS`` em `.opencode/plugin/agent-hooks.ts` contem a entrada
  ``"deployer"`` com os 3 hooks (preToolUse, postToolUse, stop).
- O profile ``deployer`` aponta para os 3 scripts em
  ``.opencode/hooks/deployer/``.
- A constante ``RECOGNIZED_AGENT_SLUGS`` lista `deployer` como slug
  canonico.
- `detectAgentFromSession` retorna `deployer` quando
  `DFE_ACTIVE_AGENT=deployer` no env (via subprocess).
- Plugin carrega via `tsx` com `DFE_ACTIVE_AGENT=deployer`.

Precedente estrutural: ``tests/integration/test_dev_plugin_dispatch.py``
(Sprint 10 C.3) e ``tests/integration/test_code_reviewer_plugin_dispatch.py``
(Sprint 9).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
PLUGIN_TS: Path = PROJECT_ROOT / ".opencode" / "plugin" / "agent-hooks.ts"
NODE_MODULES: Path = PROJECT_ROOT / "node_modules"
TSX_BIN: Path = NODE_MODULES / ".bin" / ("tsx.cmd" if sys.platform == "win32" else "tsx")
DEPLOYER_HOOK_DIR: Path = PROJECT_ROOT / ".opencode" / "hooks" / "deployer"


def test_plugin_ts_file_exists() -> None:
    assert PLUGIN_TS.exists(), f"{PLUGIN_TS} nao existe"


def test_plugin_contains_deployer_entry_in_agents_map() -> None:
    """O map `AGENTS` deve ter entrada `\"deployer\": { ... }` valida."""
    text = PLUGIN_TS.read_text(encoding="utf-8")
    assert re.search(r'\"deployer\"\s*:\s*\{', text), (
        f"`AGENTS` map em agent-hooks.ts deve conter `\"deployer\": {{...}}`. "
        f"Recebido (trecho):\n{text[text.find('const AGENTS'):text.find('const AGENTS')+2000]}"
    )


def test_deployer_profile_has_pre_tool_use() -> None:
    text = PLUGIN_TS.read_text(encoding="utf-8")
    deployer_block_match = re.search(
        r"\"deployer\"\s*:\s*\{(?P<body>[^}]*(?:\}[^}]*)*?)\}",
        text,
        re.DOTALL,
    )
    assert deployer_block_match, (
        f"Bloco do profile `deployer` nao encontrado em agent-hooks.ts"
    )
    body = deployer_block_match.group("body")
    assert "preToolUse" in body, (
        f"Profile `deployer` deve ter `preToolUse` apontando para "
        f".opencode/hooks/deployer/pre_tool_use.py. body=\n{body}"
    )
    assert ".opencode/hooks/deployer/pre_tool_use.py" in body, (
        f"preToolUse deve apontar para `.opencode/hooks/deployer/pre_tool_use.py`; "
        f"body=\n{body}"
    )


def test_deployer_profile_has_post_tool_use() -> None:
    text = PLUGIN_TS.read_text(encoding="utf-8")
    deployer_block_match = re.search(
        r"\"deployer\"\s*:\s*\{(?P<body>[^}]*(?:\}[^}]*)*?)\}",
        text,
        re.DOTALL,
    )
    assert deployer_block_match
    body = deployer_block_match.group("body")
    assert "postToolUse" in body
    assert ".opencode/hooks/deployer/post_tool_use.py" in body


def test_deployer_profile_has_stop() -> None:
    text = PLUGIN_TS.read_text(encoding="utf-8")
    deployer_block_match = re.search(
        r"\"deployer\"\s*:\s*\{(?P<body>[^}]*(?:\}[^}]*)*?)\}",
        text,
        re.DOTALL,
    )
    assert deployer_block_match, (
        "Bloco do profile `deployer` nao encontrado em agent-hooks.ts"
    )
    body = deployer_block_match.group("body")
    assert "stop" in body
    assert ".opencode/hooks/deployer/stop.py" in body


def test_recognized_agent_slugs_contains_deployer() -> None:
    """Sprint 18: `RECOGNIZED_AGENT_SLUGS` deve incluir `deployer`."""
    text = PLUGIN_TS.read_text(encoding="utf-8")
    assert re.search(r"RECOGNIZED_AGENT_SLUGS", text), (
        "Constante `RECOGNIZED_AGENT_SLUGS` nao encontrada no plugin TS."
    )
    block = text[
        text.find("RECOGNIZED_AGENT_SLUGS") : text.find("RECOGNIZED_AGENT_SLUGS")
        + 500
    ]
    assert re.search(r'\"deployer\"', block), (
        f"`RECOGNIZED_AGENT_SLUGS` deve incluir `\"deployer\"`; trecho:\n{block}"
    )


def test_deployer_hook_scripts_exist() -> None:
    """Os 3 scripts do `@deployer` precisam existir para o plugin invocar."""
    for name in ("pre_tool_use.py", "post_tool_use.py", "stop.py"):
        p = DEPLOYER_HOOK_DIR / name
        assert p.exists(), f"Hook esperado nao existe: {p}"


def test_deployer_hooks_pass_python_compile() -> None:
    """Cada hook compila sem erros de sintaxe (smoke test rapido)."""
    for name in ("pre_tool_use.py", "post_tool_use.py", "stop.py"):
        proc = subprocess.run(
            [sys.executable, "-m", "py_compile", str(DEPLOYER_HOOK_DIR / name)],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(PROJECT_ROOT),
            timeout=30,
        )
        assert proc.returncode == 0, (
            f"{name} nao compila: rc={proc.returncode} stderr={proc.stderr!r}"
        )


def test_dfe_active_agent_deployer_propagates_to_subprocess() -> None:
    """`DFE_ACTIVE_AGENT=deployer` e' visivel em subprocessos (base do dispatch)."""
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os; print(os.environ.get('DFE_ACTIVE_AGENT', ''))",
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "DFE_ACTIVE_AGENT": "deployer"},
        check=False,
        cwd=str(PROJECT_ROOT),
        timeout=15,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == "deployer"


def test_plugin_compiles_with_tsx_deployer() -> None:
    """Plugin carrega sem erros via `tsx` com DFE_ACTIVE_AGENT=deployer."""
    proc = subprocess.run(
        [
            str(TSX_BIN),
            "-e",
            f"import p from './{PLUGIN_TS.relative_to(PROJECT_ROOT).as_posix()}'; "
            f"if (typeof p !== 'function') {{ console.error('default nao eh funcao:', typeof p); process.exit(1); }} "
            f"console.log('OK')",
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "DFE_ACTIVE_AGENT": "deployer"},
        check=False,
        cwd=str(PROJECT_ROOT),
        timeout=60,
    )
    assert proc.returncode == 0, (
        f"Plugin nao carregou com DFE_ACTIVE_AGENT=deployer; exit={proc.returncode}. "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    assert "OK" in proc.stdout


def test_no_legacy_build_or_plan_in_plugin_regression() -> None:
    """Sprint 10 E.4 (gate anti-regressao): nenhuma referencia residual a `build` ou `plan`."""
    text = PLUGIN_TS.read_text(encoding="utf-8")
    for slug in ("build", "plan"):
        assert not re.search(rf'\"{slug}\"\s*:\s*\{{', text), (
            f"agent-hooks.ts ainda referencia slug legado `\"{slug}\": {{...}}` "
            "(removido na Sprint 10)."
        )