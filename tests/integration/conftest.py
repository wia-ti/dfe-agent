"""Conftest dos testes de integracao: fake portal server + temp storage."""
from __future__ import annotations

import http.server
import shutil
import socket
import socketserver
import threading
import time
from collections.abc import Generator
from pathlib import Path

import pytest


FAKE_PORTAL_SRC: Path = (
    Path(__file__).resolve().parent.parent / "fixtures" / "fake_portal"
)


@pytest.fixture(scope="session")
def fake_portal_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Copia fake_portal/ para um tmp_dir e retorna o path."""
    if not FAKE_PORTAL_SRC.exists():
        pytest.skip(f"Fixture {FAKE_PORTAL_SRC} nao existe")
    dst: Path = tmp_path_factory.mktemp("fake_portal") / "portal"
    shutil.copytree(FAKE_PORTAL_SRC, dst)
    return dst


@pytest.fixture(scope="session")
def fake_portal_url(fake_portal_dir: Path) -> Generator[str, None, None]:
    """Sobe http.server em thread daemon servindo fake_portal_dir. Retorna URL base."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        port: int = s.getsockname()[1]

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args: object, directory: str | None = None, **kwargs: object) -> None:
            super().__init__(*args, directory=directory, **kwargs)

        def log_message(self, *_args: object) -> None:
            pass

    handler_factory = lambda *args: Handler(*args, directory=str(fake_portal_dir))
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", port), handler_factory)
    httpd_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    httpd_thread.start()

    time.sleep(0.1)

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()


@pytest.fixture
def temp_storage(tmp_path: Path) -> dict[str, Path]:
    """Cria diretorios storage/ e data/ isolados para o teste."""
    storage_dir: Path = tmp_path / "storage"
    data_dir: Path = tmp_path / "data"
    storage_dir.mkdir()
    data_dir.mkdir()
    return {
        "db_path": storage_dir / "test.db",
        "data_dir": data_dir,
        "root": tmp_path,
    }