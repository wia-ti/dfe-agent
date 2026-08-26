"""Testes do helper de bootstrap de ``sys.path`` (PLAN_SPRINT7 A.5).

Cobre idempotencia por flag e por path-check, ordem de insercao,
e deteccao de layout quebrado.
"""
from __future__ import annotations

import sys

import pytest

from src.utils import syspath_bootstrap
from src.utils.syspath_bootstrap import (
    OPENCODE_PATH,
    SRC_PATH,
    ensure_sys_path,
    reset_for_testing,
)


@pytest.fixture(autouse=True)
def _reset_path_state() -> None:
    """Garante isolamento de estado entre testes."""
    reset_for_testing()
    prepended_to_remove = [str(OPENCODE_PATH), str(SRC_PATH)]
    for p in prepended_to_remove:
        while p in sys.path:
            sys.path.remove(p)
    yield
    reset_for_testing()


def test_ensure_sys_path_prepends_opencode_and_src() -> None:
    """Apos chamada, ambos os paths estao no topo de ``sys.path``."""
    assert str(OPENCODE_PATH) not in sys.path
    assert str(SRC_PATH) not in sys.path
    ensure_sys_path()
    assert sys.path[0] == str(SRC_PATH)
    assert sys.path[1] == str(OPENCODE_PATH)


def test_ensure_sys_path_idempotent() -> None:
    """Chamar ``ensure_sys_path`` 2x nao duplica entradas em ``sys.path``."""
    ensure_sys_path()
    ensure_sys_path()
    assert sys.path.count(str(OPENCODE_PATH)) == 1
    assert sys.path.count(str(SRC_PATH)) == 1


def test_ensure_sys_path_no_op_when_paths_already_present() -> None:
    """Chamar com paths ja' presentes e idempotente na pratica."""
    sys.path.insert(0, str(OPENCODE_PATH))
    sys.path.insert(0, str(SRC_PATH))
    before = list(sys.path)
    ensure_sys_path()
    assert sys.path.count(str(OPENCODE_PATH)) == 1
    assert sys.path.count(str(SRC_PATH)) == 1


def test_reset_for_testing_allows_re_bootstrap() -> None:
    """Apos ``reset_for_testing``, nova chamada re-prepende."""
    ensure_sys_path()
    assert sys.path.count(str(OPENCODE_PATH)) == 1
    reset_for_testing()
    assert str(OPENCODE_PATH) not in sys.path
    ensure_sys_path()
    assert sys.path.count(str(OPENCODE_PATH)) == 1


def test_module_paths_exist() -> None:
    """Sanidade: os paths exportados apontam para diretorios reais."""
    assert OPENCODE_PATH.is_dir()
    assert SRC_PATH.is_dir()


def test_module_attribute_accessible() -> None:
    """O modulo exporta os simbolos publicos esperados."""
    assert hasattr(syspath_bootstrap, "ensure_sys_path")
    assert hasattr(syspath_bootstrap, "reset_for_testing")
    assert hasattr(syspath_bootstrap, "OPENCODE_PATH")
    assert hasattr(syspath_bootstrap, "SRC_PATH")
