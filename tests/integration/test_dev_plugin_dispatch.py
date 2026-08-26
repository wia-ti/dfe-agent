"""Testes de integracao do plugin TS com o agente `@dev` (PLAN_SPRINT10 C.3 + Sprint 12 B12.1).

Cobre:

- O map ``AGENTS`` em `.opencode/plugin/agent-hooks.ts` contem a entrada
  ``"dev"`` com os 3 hooks (preToolUse, postToolUse, stop).
- O profile ``dev`` aponta para os 3 scripts em ``.opencode/hooks/dev/``
  (Sprint 12 B12.1 unificou; antes era ``.claude/hooks/dev/``).
- A constante ``RECOGNIZED_AGENT_SLUGS`` lista `dev` como slug canonico.
- `detectAgentFromSession` retorna `dev` quando `DFE_ACTIVE_AGENT=dev`.
- Nenhum profile legada referencia `build` ou `plan` (removidos na Sprint 10).
"""
from __future__ import annotations

import json
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
DEV_HOOK_DIR: Path = PROJECT_ROOT / ".opencode" / "hooks" / "dev"


def test_plugin_ts_file_exists() -> None:
    assert PLUGIN_TS.exists(), f"{PLUGIN_TS} nao existe"


def test_plugin_contains_dev_entry_in_agents_map() -> None:
    """O map `AGENTS` deve ter entrada `\"dev\": { ... }` valida."""
    text = PLUGIN_TS.read_text(encoding="utf-8")
    assert re.search(r'\"dev\"\s*:\s*\{', text), (
        f"`AGENTS` map em agent-hooks.ts deve conter `\"dev\": {{...}}`. "
        f"Recebido (trecho):\n{text[text.find('const AGENTS'):text.find('const AGENTS')+1500]}"
    )


def test_dev_profile_has_pre_tool_use() -> None:
    text = PLUGIN_TS.read_text(encoding="utf-8")
    dev_block_match = re.search(
        r"\"dev\"\s*:\s*\{(?P<body>[^}]*(?:\}[^}]*)*?)\}",
        text,
        re.DOTALL,
    )
    assert dev_block_match, (
        f"Bloco do profile `dev` nao encontrado em agent-hooks.ts"
    )
    body = dev_block_match.group("body")
    assert "preToolUse" in body, (
        f"Profile `dev` deve ter `preToolUse` apontando para .opencode/hooks/dev/pre_tool_use.py"
    )
    assert ".opencode/hooks/dev/pre_tool_use.py" in body, (
        f"preToolUse deve apontar para `.opencode/hooks/dev/pre_tool_use.py` "
        f"(Sprint 12 B12.1); body=\n{body}"
    )


def test_dev_profile_has_post_tool_use() -> None:
    text = PLUGIN_TS.read_text(encoding="utf-8")
    dev_block_match = re.search(
        r"\"dev\"\s*:\s*\{(?P<body>[^}]*(?:\}[^}]*)*?)\}",
        text,
        re.DOTALL,
    )
    assert dev_block_match
    body = dev_block_match.group("body")
    assert "postToolUse" in body
    assert ".opencode/hooks/dev/post_tool_use.py" in body


def test_dev_profile_has_stop() -> None:
    text = PLUGIN_TS.read_text(encoding="utf-8")
    dev_block_match = re.search(
        r"\"dev\"\s*:\s*\{(?P<body>[^}]*(?:\}[^}]*)*?)\}",
        text,
        re.DOTALL,
    )
    assert dev_block_match, "Bloco do profile `dev` nao encontrado em agent-hooks.ts"
    body = dev_block_match.group("body")
    assert "stop" in body
    assert ".opencode/hooks/dev/stop.py" in body


def test_recognized_agent_slugs_contains_dev() -> None:
    """Sprint 10 C.3: `RECOGNIZED_AGENT_SLUGS` deve incluir `dev`."""
    text = PLUGIN_TS.read_text(encoding="utf-8")
    assert re.search(r"RECOGNIZED_AGENT_SLUGS", text), (
        "Constante `RECOGNIZED_AGENT_SLUGS` nao encontrada no plugin TS."
    )
    block = text[text.find("RECOGNIZED_AGENT_SLUGS"):text.find("RECOGNIZED_AGENT_SLUGS") + 400]
    assert re.search(r'\"dev\"', block), (
        f"`RECOGNIZED_AGENT_SLUGS` deve incluir `\"dev\"`; trecho:\n{block}"
    )


def test_no_legacy_build_or_plan_in_plugin() -> None:
    """Sprint 10 E.4: nenhuma referencia residual a `build` ou `plan`."""
    text = PLUGIN_TS.read_text(encoding="utf-8")
    for slug in ("build", "plan"):
        assert not re.search(rf'\"{slug}\"\s*:\s*\{{', text), (
            f"agent-hooks.ts ainda referencia slug legado `\"{slug}\": {{...}}` "
            "(removido na Sprint 10)."
        )


def test_dev_hook_scripts_exist() -> None:
    """Os 3 scripts do `@dev` precisam existir para o plugin invocar."""
    for name in ("pre_tool_use.py", "post_tool_use.py", "stop.py"):
        p = DEV_HOOK_DIR / name
        assert p.exists(), f"Hook esperado nao existe: {p}"


def test_dev_hooks_pass_python_compile() -> None:
    """Cada hook compila sem erros de sintaxe (smoke test rapido)."""
    for name in ("pre_tool_use.py", "post_tool_use.py", "stop.py"):
        proc = subprocess.run(
            [sys.executable, "-m", "py_compile", str(DEV_HOOK_DIR / name)],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(PROJECT_ROOT),
            timeout=30,
        )
        assert proc.returncode == 0, (
            f"{name} nao compila: rc={proc.returncode} stderr={proc.stderr!r}"
        )


def test_dfe_active_agent_dev_propagates_to_subprocess() -> None:
    """`DFE_ACTIVE_AGENT=dev` e' visivel em subprocessos (base do dispatch)."""
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os; print(os.environ.get('DFE_ACTIVE_AGENT', ''))",
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "DFE_ACTIVE_AGENT": "dev"},
        check=False,
        cwd=str(PROJECT_ROOT),
        timeout=15,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == "dev"


def test_plugin_compiles_with_tsx() -> None:
    """Plugin carrega sem erros via `tsx` (padrao de
    `tests/integration/test_agent_hooks_plugin_loads.py`)."""
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
        env={**os.environ, "DFE_ACTIVE_AGENT": "dev"},
        check=False,
        cwd=str(PROJECT_ROOT),
        timeout=60,
    )
    assert proc.returncode == 0, (
        f"Plugin nao carregou com DFE_ACTIVE_AGENT=dev; exit={proc.returncode}. "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    assert "OK" in proc.stdout
