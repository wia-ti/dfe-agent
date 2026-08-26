"""Testes do bootstrapper de guard HTTP in-process.

Cobre (PLAN_SPRINT5 A.1):
    - ``install_guard_once`` e' idempotente (chamadas repetidas nao
      duplicam o monkey-patch).
    - ``install_guard_once`` delega para ``http_guard.install_http_guard``.

Origem do guard rail (BLOQUEANTE B1):
    Entry-points CLI (``src.collector.__main__``,
    ``src.indexer.ingest``, ``src.query.__main__``) devem chamar
    ``install_guard_once`` antes de qualquer I/O HTTP, garantindo que
    o monkey-patch em ``requests.get`` / ``requests.Session.get``
    esta' ativo. O bootstrap centraliza a chamada e expoe
    ``was_bootstrap_called()`` para diagnosticos.
"""
from __future__ import annotations

import pytest

from src.utils import http_guard, http_guard_bootstrap


@pytest.fixture(autouse=True)
def _reset_bootstrap_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reseta o estado interno do bootstrap antes de cada teste.

    O modulo ``http_guard_bootstrap`` mantem uma flag de modulo
    ``_BOOTSTRAP_DONE``. Para que testes sejam independentes, resetamos
    a flag via ``monkeypatch.setattr`` antes de cada teste. Tambem
    restauramos a flag ``_guards_installed`` em ``http_guard`` e os
    originais ``requests.get`` / ``requests.Session.get`` para evitar
    contaminacao entre testes.
    """
    monkeypatch.setattr(http_guard_bootstrap, "_BOOTSTRAP_DONE", False)
    monkeypatch.setattr(http_guard, "_guards_installed", False)


def test_install_guard_once_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Chamar ``install_guard_once`` 2x nao duplica registro.

    Estrategia:
        - Spy em ``http_guard.install_http_guard``.
        - Chamar ``install_guard_once()`` 3 vezes.
        - Assert que o sub-funcion foi chamado exatamente 1 vez.
        - Teardown: ``uninstall_http_guard`` no ``finally`` para evitar
          leak de ``requests.Session.get = safe_session_get`` para testes
          posteriores (PLAN_SPRINT6 B.1; PLAN_SPRINT5 risco A.1
          documentado mas nao implementado).
    """
    call_counter: dict[str, int] = {"n": 0}
    real_install = http_guard.install_http_guard

    def fake_install() -> None:
        call_counter["n"] += 1
        real_install()

    monkeypatch.setattr(http_guard_bootstrap, "install_http_guard", fake_install)

    try:
        http_guard_bootstrap.install_guard_once()
        http_guard_bootstrap.install_guard_once()
        http_guard_bootstrap.install_guard_once()

        assert call_counter["n"] == 1, (
            f"Esperado 1 chamada de install_http_guard, obtido {call_counter['n']}"
        )
        assert http_guard_bootstrap.was_bootstrap_called() is True
    finally:
        http_guard.uninstall_http_guard()


def test_install_guard_once_invokes_install_http_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``install_guard_once`` delega para ``http_guard.install_http_guard``.

    Estrategia:
        - Spy em ``http_guard.install_http_guard``.
        - Resetar a flag ``_guards_installed`` em ``http_guard``.
        - Chamar ``install_guard_once()``.
        - Assert que ``http_guard.install_http_guard`` foi chamado 1x
          E que ``http_guard._guards_installed`` agora e' ``True``
          (efeito colateral esperado).
    """
    call_counter: dict[str, int] = {"n": 0}

    def fake_install() -> None:
        call_counter["n"] += 1
        http_guard._guards_installed = True

    monkeypatch.setattr(http_guard_bootstrap, "install_http_guard", fake_install)
    assert http_guard._guards_installed is False

    http_guard_bootstrap.install_guard_once()

    assert call_counter["n"] == 1, (
        f"Esperado 1 chamada de install_http_guard, obtido {call_counter['n']}"
    )
    assert http_guard._guards_installed is True, (
        "install_http_guard nao foi executada (flag nao foi marcada)"
    )


__all__ = [
    "test_install_guard_once_idempotent",
    "test_install_guard_once_invokes_install_http_guard",
]
