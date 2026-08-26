"""Testes do guard HTTP in-process ``src/utils/http_guard.py``.

Cobre (PLAN_SPRINT4 A.3 / PLAN_SPRINT11 B):
    - O guard HTTP in-process bloqueia URLs fora de ``ALLOWED_DOMAINS``
      quando ``install_http_guard`` e chamado.
    - URLs validadas passam pelo guard.
    - Nenhum modulo em ``src/`` importa ``domain_guard`` diretamente
      (regra ``git grep "from domain_guard" src/`` == 0).

A implementacao e ``src.utils.http_guard``: importado pelo coletor
para validar URLs SEM precisar importar ``hooks.domain_guard``
diretamente.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]


def test_http_guard_blocks_evil_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """``safe_get('https://evil.com/x')`` levanta ``PermissionError``.

    O guard HTTP in-process envolve ``requests.get`` e valida cada URL
    contra ``ALLOWED_DOMAINS`` antes de chamar a rede.

    Defesa em profundidade (PLAN_SPRINT8): testes anteriores (ex.:
    ``tests/unit/collector/test_main.py::test_dry_run_lists_urls_without_db_or_download``)
    podem deixar o flag ``_guards_installed=True`` enquanto mocker ja'
    restaurou ``requests.get`` para o original. ``install_http_guard``
    idempotente retorna sem instalar nesse caso, e o teste falha. A
    solucao canonica: ``uninstall_http_guard()`` antes (garante estado
    limpo) seguido de ``install_http_guard()``.
    """
    from src.utils import http_guard

    import requests as req_module

    http_guard.uninstall_http_guard()
    http_guard.install_http_guard()
    try:
        with pytest.raises(PermissionError, match="bloqueada pelo guardrail"):
            req_module.get("https://evil.com/x")
    finally:
        http_guard.uninstall_http_guard()


def test_http_guard_allows_nfe_url(
    monkeypatch: pytest.MonkeyPatch, mocker
) -> None:
    """``safe_get('https://www.nfe.fazenda.gov.br/x.pdf')`` passa adiante.

    Estrategia: stub ``requests.get`` para retornar um MagicMock
    (evita I/O real); verifica que o stub foi chamado com a URL e
    que ``PermissionError`` NAO foi levantado.
    """
    from src.utils import http_guard

    import requests as req_module

    http_guard.install_http_guard()
    try:
        fake_response = mocker.MagicMock()
        fake_response.status_code = 200
        fake_response.content = b"%PDF-fake"
        fake_response.raise_for_status = lambda: None
        mocker.patch.object(req_module, "get", return_value=fake_response)

        resp = req_module.get("https://www.nfe.fazenda.gov.br/x.pdf", timeout=5)
        assert resp is fake_response
    finally:
        http_guard.uninstall_http_guard()


def test_http_guard_blocks_evil_session_get(monkeypatch: pytest.MonkeyPatch) -> None:
    """``Session().get('https://evil.com/x')`` tambem e bloqueado.

    O guard cobre tanto ``requests.get`` (mod-level) quanto
    ``requests.Session.get`` (instance-level).
    """
    from src.utils import http_guard

    import requests as req_module

    http_guard.install_http_guard()
    try:
        session = req_module.Session()
        with pytest.raises(PermissionError, match="bloqueada pelo guardrail"):
            session.get("https://evil.com/x")
    finally:
        http_guard.uninstall_http_guard()


def test_safe_session_get_does_not_recurse(
    monkeypatch: pytest.MonkeyPatch, mocker
) -> None:
    """``safe_session_get`` nao recursiva ao chamar URL autorizada.

    Bug latente (PLAN_SPRINT6 BLOQUEANTE B6): ``safe_session_get`` chamava
    ``session.get(url, **kwargs)`` apos o monkey-patch ter substituido
    ``requests.Session.get`` por ele mesmo, gerando ``RecursionError``.
    Correcao: ``safe_session_get`` agora chama ``_original_session_get``.
    Este teste valida o caminho positivo substituindo o original por um
    contador — pre-fix a recursao estoura antes de alcancar o contador;
    post-fix o contador registra exatamente 1 chamada.

    Nota de isolamento: ``install_http_guard`` patcha AMBOS
    ``requests.get`` E ``requests.Session.get``; o ``finally`` restaura
    AMBOS diretamente para os valores capturados ANTES do install. Usar
    ``uninstall_http_guard`` nao basta porque o teardown do ``monkeypatch``
    do pytest reverte ``_original_*`` apos o retorno da funcao de teste,
    deixando os atributos ``requests.get`` / ``requests.Session.get``
    apontando para o fake.
    """
    from src.utils import http_guard

    import requests as req_module

    original_session_get = req_module.Session.get
    original_requests_get = req_module.get
    call_counter: dict[str, int] = {"n": 0}

    def fake_original_get(session: object, url: str, **kwargs: object) -> object:
        call_counter["n"] += 1
        return mocker.MagicMock(status_code=200, raise_for_status=lambda: None)

    monkeypatch.setattr(http_guard, "_original_session_get", fake_original_get)
    http_guard.install_http_guard()
    try:
        session = req_module.Session()
        resp = session.get(
            "https://www.nfe.fazenda.gov.br/portal/x.pdf", timeout=5
        )
        assert resp.status_code == 200
        assert call_counter["n"] == 1, (
            f"Esperado 1 chamada ao original, obtido {call_counter['n']} "
            f"(recursao? — pre-fix este teste levanta RecursionError)"
        )
    finally:
        req_module.Session.get = original_session_get
        req_module.get = original_requests_get
        http_guard._guards_installed = False


def test_safe_get_does_not_recurse(
    monkeypatch: pytest.MonkeyPatch, mocker
) -> None:
    """``safe_get`` (mod-level) nao recursiva ao chamar URL autorizada.

    Simetrico a ``test_safe_session_get_does_not_recurse`` para
    ``requests.get``. Sem call-site de producao em ``src/`` que dispare
    o bug hoje, mas a simetria quebrada foi corrigida para evitar
    regressao futura quando algum modulo de ``src/`` passar a usar
    ``requests.get`` diretamente.

    Nota de isolamento: mesma observacao de
    ``test_safe_session_get_does_not_recurse`` — restaurar AMBOS
    ``requests.get`` e ``requests.Session.get``.
    """
    from src.utils import http_guard

    import requests as req_module

    original_session_get = req_module.Session.get
    original_requests_get = req_module.get
    call_counter: dict[str, int] = {"n": 0}

    def fake_original_get(url: str, **kwargs: object) -> object:
        call_counter["n"] += 1
        return mocker.MagicMock(status_code=200, raise_for_status=lambda: None)

    monkeypatch.setattr(http_guard, "_original_requests_get", fake_original_get)
    http_guard.install_http_guard()
    try:
        resp = req_module.get(
            "https://www.nfe.fazenda.gov.br/portal/x.pdf", timeout=5
        )
        assert resp.status_code == 200
        assert call_counter["n"] == 1, (
            f"Esperado 1 chamada ao original, obtido {call_counter['n']} "
            f"(recursao? — pre-fix este teste levanta RecursionError)"
        )
    finally:
        req_module.Session.get = original_session_get
        req_module.get = original_requests_get
        http_guard._guards_installed = False


def test_src_has_no_direct_domain_guard_import() -> None:
    """Nenhum modulo em ``src/`` importa ``domain_guard`` diretamente.

    A unica importacao permitida e via ``src/utils/http_guard.py``
    (camada de abstracao).
    """
    import re

    pattern = re.compile(r"^\s*from\s+domain_guard\b|^\s*import\s+domain_guard\b")
    offenders: list[tuple[Path, int, str]] = []
    for py_file in (PROJECT_ROOT / "src").rglob("*.py"):
        for line_no, line in enumerate(py_file.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.match(line):
                offenders.append((py_file, line_no, line.strip()))

    assert offenders == [], (
        "Encontrado import direto de domain_guard em src/:\n"
        + "\n".join(f"{p.relative_to(PROJECT_ROOT)}:{ln}: {s}" for p, ln, s in offenders)
    )
