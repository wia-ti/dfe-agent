"""Testes unitarios de ``--diagnose-net`` (PLAN_SPRINT7 C.1, C.3).

Como ``mocker.patch.object`` do pytest-mock NAO propaga para subprocessos,
testes de subprocess do CLI nao conseguem mockar ``socket.getaddrinfo``
ou ``_probe_host``. Por isso, este modulo cobre a logica de
``_probe_host`` e ``_run_diagnose_net`` em UNIT (no mesmo processo),
sem invocar subprocess.

O flag --diagnose-net em si e' coberto em
``tests/unit/collector/test_main.py::test_help_documents_diagnose_net_flag``.
"""
from __future__ import annotations

import io
import json
import socket

import pytest

from src.collector import __main__ as cli_main


def _hosts_payload(captured: str) -> dict:
    return json.loads(captured)


@pytest.fixture
def _capture_stdout(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    """Substitui ``sys.stdout`` por um buffer em memoria para inspecionar.

    O helper ``_run_diagnose_net`` chama ``sys.stdout.reconfigure`` (que
    falha em StringIO via try/except) e depois ``print(json.dumps(...))``.
    Por isso usamos ``capsys`` (fixture pytest) via argumento explicito
    nos testes que precisam ler saida; este fixture fica como
    compatibilidade legada.
    """
    del monkeypatch
    return io.StringIO()


def test_probe_host_resolves_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DNS NXDOMAIN retorna resolves=false e reachable=false."""

    def _fake_getaddrinfo(_host, *_a, **_kw):
        raise socket.gaierror(-2, "Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    out = cli_main._probe_host("example.invalid")
    assert out["resolves"] is False
    assert out["reachable"] is False
    assert "Name or service not known" in out["error"]


def test_probe_host_reachable_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DNS OK + HTTP 200/3xx = reachable."""

    def _fake_getaddrinfo(_host, *_a, **_kw):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]

    class _Resp:
        status_code = 200

    def _fake_get(url, *, timeout, allow_redirects):
        assert url == "https://example.ok/"
        return _Resp()

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    monkeypatch.setattr(cli_main.requests, "get", _fake_get)
    out = cli_main._probe_host("example.ok")
    assert out["resolves"] is True
    assert out["reachable"] is True
    assert out["error"] is None
    assert isinstance(out["latency_ms"], int)


def test_probe_host_http_5xx_marks_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP 503 (ou >=500) -> reachable=false."""

    def _fake_getaddrinfo(_host, *_a, **_kw):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]

    class _Resp:
        status_code = 503

    def _fake_get(url, *, timeout, allow_redirects):
        return _Resp()

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    monkeypatch.setattr(cli_main.requests, "get", _fake_get)
    out = cli_main._probe_host("example.degraded")
    assert out["resolves"] is True
    assert out["reachable"] is False
    assert "HTTP 503" in out["error"]


def test_probe_host_timeout_marks_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Timeout do getaddrinfo/request -> reachable=false."""

    def _fake_getaddrinfo(_host, *_a, **_kw):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]

    def _fake_get(url, *, timeout, allow_redirects):
        import requests as _r

        raise _r.exceptions.ConnectTimeout("timeout")

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    monkeypatch.setattr(cli_main.requests, "get", _fake_get)
    out = cli_main._probe_host("example.slow")
    assert out["resolves"] is True
    assert out["reachable"] is False
    assert "ConnectTimeout" in out["error"]


def test_run_diagnose_net_all_unreachable_returns_1(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Quando todos os hosts falham, retorna exit code 1 (util para CI)."""

    def _fake_getaddrinfo(_host, *_a, **_kw):
        raise socket.gaierror(-2, "Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    rc = cli_main._run_diagnose_net()
    captured = capsys.readouterr()
    assert rc == 1
    payload = _hosts_payload(captured.out)
    assert payload["summary"]["resolves"] == 0
    assert payload["summary"]["reachable"] == 0
    assert all(h["resolves"] is False for h in payload["hosts"])


def test_run_diagnose_net_all_ok_returns_0(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Quando todos reachable, exit 0."""

    def _fake_probe(_host: str) -> dict:
        return {
            "host": _host,
            "resolves": True,
            "reachable": True,
            "latency_ms": 12,
            "error": None,
        }

    monkeypatch.setattr(cli_main, "_probe_host", _fake_probe)
    rc = cli_main._run_diagnose_net()
    captured = capsys.readouterr()
    assert rc == 0
    payload = _hosts_payload(captured.out)
    assert payload["summary"]["total"] >= 1
    assert payload["summary"]["reachable"] == payload["summary"]["total"]


def test_categorize_request_error_distinguishes_dns() -> None:
    """``_categorize_request_error`` distingue NXDOMAIN vs timeout vs
    ConnectionRefused vs erro generico."""
    class _FakeDNS(Exception):
        pass

    class _FakeTimeout(Exception):
        pass

    class _FakeRefused(Exception):
        pass

    class _Generic(Exception):
        pass

    class _DNSLike(_FakeDNS):
        def __str__(self) -> str:  # type: ignore[override]
            return "Failed to resolve: NameResolutionError"

    dns = cli_main._categorize_request_error(_DNSLike("x"))
    timeout = cli_main._categorize_request_error(_FakeTimeout("connect timeout 5.0s"))
    refused = cli_main._categorize_request_error(_FakeRefused("Connection refused"))
    generic = cli_main._categorize_request_error(_Generic("qualquer coisa"))

    assert "NameResolutionError" in dns
    assert "host nao resolve" in dns.lower()
    assert "Timeout" in timeout
    assert "host nao respondeu" in timeout.lower()
    assert "ConnectionRefused" in refused
    assert "porta 443" in refused.lower()
    assert "qualquer coisa" in generic
