"""Bootstrap de ``sys.path`` para permitir imports de ``.opencode/hooks/`` em CLI.

O guardrail ``hooks.domain_guard`` vive em ``.opencode/hooks/``; testes pytest
adicionam esse diretorio via ``tests/conftest.py``, mas entry-points CLI
(``python -m src.<x>``) executados direto do terminal nao passam pelo conftest
e levantam ``ModuleNotFoundError`` quando ``src.utils.http_guard`` tenta
importar o pacote ``hooks`` no top-level.

Este helper faz a mesma adicao de forma idempotente e compartilhavel, sem
duplicar logica entre ``conftest.py`` e os testes de CLI.

Origem (PLAN_SPRINT7 A.1, BLOQUEANTE B7): o workaround manual de
``PYTHONPATH`` em ``tests/unit/query/test_main.py`` foi migrado para este
modulo e para ``src.utils.http_guard``.
"""
from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
OPENCODE_PATH: Path = PROJECT_ROOT / ".opencode"
SRC_PATH: Path = PROJECT_ROOT / "src"

_BOOTSTRAP_DONE: bool = False


def ensure_sys_path() -> None:
    """Prepende ``.opencode/`` e ``src/`` em ``sys.path`` (idempotente).

    Ordem de insercao: ``OPENCODE_PATH`` primeiro (para que ``import hooks``
    funcione), depois ``SRC_PATH`` (para ``import src.<x>`` em ambientes onde
    o pacote nao esteja instalado via ``pip install -e .``). Idempotente via
    flag de modulo ``_BOOTSTRAP_DONE``.

    Raises:
        RuntimeError: se os diretorios canônicos nao existirem (sinaliza
            que o modulo esta' sendo importado fora do layout esperado do
            projeto).
    """
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    if not OPENCODE_PATH.is_dir():
        raise RuntimeError(
            f"OPENCODE_PATH nao existe: {OPENCODE_PATH} "
            "(layout do projeto quebrado)"
        )
    if not SRC_PATH.is_dir():
        raise RuntimeError(
            f"SRC_PATH nao existe: {SRC_PATH} "
            "(layout do projeto quebrado)"
        )
    for entry in (OPENCODE_PATH, SRC_PATH):
        sp = str(entry)
        if sp not in sys.path:
            sys.path.insert(0, sp)
    _BOOTSTRAP_DONE = True


def reset_for_testing() -> None:
    """Reseta a flag e remove os paths prependidos (uso exclusivo de testes).

    Idempotencia do helper usa flag de modulo; para tests que precisam
    re-exercitar o bootstrap, esta funcao reseta o estado para a chamada
    subsequente surtir efeito.
    """
    global _BOOTSTRAP_DONE
    for entry in (OPENCODE_PATH, SRC_PATH):
        sp = str(entry)
        while sp in sys.path:
            sys.path.remove(sp)
    _BOOTSTRAP_DONE = False


__all__ = [
    "OPENCODE_PATH",
    "PROJECT_ROOT",
    "SRC_PATH",
    "ensure_sys_path",
    "reset_for_testing",
]
