"""Testes do plugin ``.opencode/plugin/agent-hooks.ts`` (PLAN_SPRINT8 A/B/D).

Cobre:

- Plugin TypeScript compila e exporta ``default`` como funcao.
- ``opencode.json`` raiz tem campo ``plugin`` apontando para o path do
  plugin TS.
- Plugin TS injeta ``tool_writes_count`` no payload do stop event
  (PLAN_SPRINT8 B.1).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
PLUGIN_TS: Path = PROJECT_ROOT / ".opencode" / "plugin" / "agent-hooks.ts"
NODE_MODULES: Path = PROJECT_ROOT / "node_modules"
TSX_BIN: Path = (
    NODE_MODULES / ".bin" / ("tsx.cmd" if sys.platform == "win32" else "tsx")
)
OPENCODE_JSON: Path = PROJECT_ROOT / "opencode.json"


def test_plugin_ts_exists() -> None:
    """Arquivo do plugin deve existir (pre-requisito)."""
    assert PLUGIN_TS.exists(), (
        f"Plugin TS esperado em {PLUGIN_TS}; arquivo nao encontrado."
    )


def test_plugin_default_export_is_function() -> None:
    """Plugin deve exportar ``default`` como funcao (assinatura OpenCode).

    Estrategia: usa ``tsx`` para carregar o modulo e executa um eval que
    verifica o tipo do ``default export``. Se falhar (exit != 0),
    captura stdout/stderr para diagnostico.
    """
    eval_script: str = (
        f"import('./{str(PLUGIN_TS).replace(chr(92), '/')}');"
    )
    result = subprocess.run(
        [
            str(TSX_BIN),
            "-e",
            f"import p from './{PLUGIN_TS.relative_to(PROJECT_ROOT).as_posix()}'; "
            f"if (typeof p !== 'function') {{ console.error('default nao eh funcao:', typeof p); process.exit(1); }} "
            f"console.log('OK')",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(PROJECT_ROOT),
        timeout=30,
    )
    assert result.returncode == 0, (
        f"Plugin nao carregou; exit={result.returncode}. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "OK" in result.stdout, (
        f"stdout nao contem 'OK'; obtido {result.stdout!r}"
    )


def test_opencode_json_has_plugin_field() -> None:
    """``opencode.json`` raiz deve referenciar o plugin TS (PLAN_SPRINT8 A.1)."""
    config: dict = json.loads(OPENCODE_JSON.read_text(encoding="utf-8"))
    assert "plugin" in config, (
        f"opencode.json deve ter campo 'plugin'; obtido chaves: {list(config.keys())}"
    )
    plugin_field = config["plugin"]
    assert isinstance(plugin_field, list), (
        f"plugin deve ser array de paths; obtido {type(plugin_field).__name__}"
    )
    assert ".opencode/plugin/agent-hooks.ts" in plugin_field, (
        f"plugin deve conter '.opencode/plugin/agent-hooks.ts'; "
        f"obtido {plugin_field!r}"
    )


def test_plugin_ts_includes_writes_per_session_counter() -> None:
    """Plugin TS deve declarar contador ``writesPerSession`` (PLAN_SPRINT8 B.1)."""
    src: str = PLUGIN_TS.read_text(encoding="utf-8")
    assert "writesPerSession" in src, (
        "agent-hooks.ts deve declarar contador writesPerSession "
        "(PLAN_SPRINT8 B.1)."
    )
    assert "tool_writes_count" in src, (
        "agent-hooks.ts deve injetar tool_writes_count no payload do stop event."
    )


def test_plugin_ts_increments_counter_on_post_tool_use() -> None:
    """Plugin TS deve incrementar o contador dentro de tool.execute.after."""
    src: str = PLUGIN_TS.read_text(encoding="utf-8")
    pattern = re.compile(
        r'tool\.execute\.after[\s\S]*?writesPerSession\.set\(',
        re.MULTILINE,
    )
    assert pattern.search(src), (
        "agent-hooks.ts deve incrementar writesPerSession dentro de "
        "tool.execute.after (escrito antes do runPython de postToolUse)."
    )


def test_plugin_ts_clears_counter_after_stop() -> None:
    """Plugin TS deve limpar o contador apos stop (evita memory leak)."""
    src: str = PLUGIN_TS.read_text(encoding="utf-8")
    pattern = re.compile(
        r'event[\s\S]*?writesPerSession\.delete\(',
        re.MULTILINE,
    )
    assert pattern.search(src), (
        "agent-hooks.ts deve chamar writesPerSession.delete() apos o "
        "stop event ser processado (evita crescimento ilimitado)."
    )
