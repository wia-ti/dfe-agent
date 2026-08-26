"""Fixtures compartilhadas para os testes do coletor.

Fornece:
    - fake_storage: SqliteStorage real apontando para tmp_path.
    - fake_throttler: Throttler real com intervalo zero (sem sleep).
    - fake_data_dir: diretorio temporario para downloads.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.db.sqlite_storage import SqliteStorage
from src.utils.throttler import Throttler


@pytest.fixture
def fake_storage(tmp_path: Path) -> SqliteStorage:
    storage = SqliteStorage(tmp_path / "test.db")
    storage.init_schema()
    return storage


@pytest.fixture
def fake_throttler() -> Throttler:
    return Throttler(request_interval_ms=0, jitter_ms=0)


@pytest.fixture
def fake_data_dir(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir
