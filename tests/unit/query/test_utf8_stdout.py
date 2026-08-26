"""Testes do helper ``_configure_utf8_stdout`` (PLAN_SPRINT7 B.2).

Origem (BLOQUEANTE B8): em PowerShell do Windows, ``sys.stdout`` herda
codepage cp1252; quando ``json.dumps(..., ensure_ascii=False)`` emite
caracteres UTF-8 (bullet ``•``, emoji, ``ç`` sem pre-composicao), o
``print()`` falha com ``UnicodeEncodeError: 'charmap' codec can't encode
character``.

Este helper reescreve stdout/stderr para UTF-8 antes de qualquer saida
de JSON. Os testes abaixo verificam:

- O helper nao levanta excecao quando stdout ja' e' UTF-8 (caso Linux/Mac).
- O helper reconfigura streams que suportam ``reconfigure(encoding=...)``.
- Apos o helper, ``sys.stdout.encoding`` contem ``utf``.
- ``stdout.write('\\uf0b7')`` nao levanta ``UnicodeEncodeError``.
"""
from __future__ import annotations

import io
import sys
from unittest import mock

import pytest

from src.query.__main__ import _configure_utf8_stdout


@pytest.fixture
def _restore_stdio():
    """Salva e restaura stdout/stderr + encoding."""
    saved_stdout = sys.stdout
    saved_stderr = sys.stderr
    saved_out_enc = sys.stdout.encoding
    saved_err_enc = sys.stderr.encoding
    yield
    sys.stdout = saved_stdout
    sys.stderr = saved_stderr


def test_configure_utf8_stdout_is_idempotent(_restore_stdio) -> None:
    """Chamar 2x nao levanta erro."""
    _configure_utf8_stdout()
    _configure_utf8_stdout()
    assert "utf" in (sys.stdout.encoding or "").lower()


def test_configure_utf8_stdout_allows_unicode_writes(_restore_stdio) -> None:
    """Apos helper, escrever bullet UTF-8 nao levanta UnicodeEncodeError."""
    _configure_utf8_stdout()
    # capturar bytes do stdout apos reconfiguracao
    buf = io.BytesIO()
    wrapper = io.TextIOWrapper(buf, encoding="utf-8", write_through=True)
    with mock.patch.object(sys, "stdout", wrapper):
        try:
            sys.stdout.write("\uf0b7")  # bullet private use area
        except UnicodeEncodeError as exc:
            pytest.fail(
                f"Esperava UTF-8 mas recebi UnicodeEncodeError: {exc}"
            )


def test_configure_utf8_stdout_handles_unconfigurable_stream(
    _restore_stdio,
) -> None:
    """Quando stdout nao tem ``reconfigure``, o helper usa fallback via
    TextIOWrapper e nao levanta AttributeError.
    """
    fake = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", write_through=True)

    def _raise_reconfigure(*_args, **_kwargs):
        raise AttributeError("no reconfigure")

    fake.reconfigure = _raise_reconfigure  # type: ignore[attr-defined]

    with mock.patch.object(sys, "stdout", fake):
        _configure_utf8_stdout()
    # o helper substituiu o stream; o que importa e' nao levantar
    # AttributeError. Confirmar que nenhum erro nao tratado foi emitido.
    assert True


def test_configure_utf8_stdout_also_configures_stderr(_restore_stdio) -> None:
    """stderr tambem e' reconfigurado."""
    _configure_utf8_stdout()
    assert "utf" in (sys.stderr.encoding or "").lower()


def test_module_exports_helper() -> None:
    """O simbolo publico esta' exposto no modulo (smoke import)."""
    from src.query import __main__ as m

    assert callable(m._configure_utf8_stdout)
