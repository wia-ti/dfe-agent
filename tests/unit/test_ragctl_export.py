"""Testes de ``python -m src.ragctl export`` (Sprint 20).

O export empacota ``storage/dfe.db`` em ``dfe.db.gz`` + ``dfe.db.gz.sha256``
para publicacao no GitHub Releases (a base RAG nao e' mais versionada no git).
"""
from __future__ import annotations

import gzip
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from src.ragctl import _build_arg_parser, cmd_export, cmd_migrate


def _args(db_path: Path, out_dir: Path) -> object:
    return type("Args", (), {"db_path": db_path, "out_dir": out_dir})()


@pytest.fixture()
def migrated_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "src" / "dfe.db"
    cmd_migrate(type("Args", (), {"db_path": db_path})())
    return db_path


def test_parser_expoe_export() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args(["export", "--out-dir", "x"])
    assert args.func is cmd_export
    assert args.out_dir == Path("x")


def test_export_default_out_dir_e_storage() -> None:
    args = _build_arg_parser().parse_args(["export"])
    assert args.out_dir == Path("storage")


def test_export_gera_gz_e_sha(migrated_db: Path, tmp_path: Path, capsys) -> None:
    out_dir = tmp_path / "out"
    rc = cmd_export(_args(migrated_db, out_dir))
    assert rc == 0

    gz_path = out_dir / "dfe.db.gz"
    sha_path = out_dir / "dfe.db.gz.sha256"
    assert gz_path.exists() and sha_path.exists()

    expected = hashlib.sha256(gz_path.read_bytes()).hexdigest()
    assert sha_path.read_text(encoding="utf-8").strip() == expected

    report = json.loads(capsys.readouterr().out)
    assert report["sha256"] == expected
    assert report["gz_path"] == str(gz_path)


def test_export_preserva_schema_version(migrated_db: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    cmd_export(_args(migrated_db, out_dir))

    restored = tmp_path / "restored.db"
    restored.write_bytes(gzip.decompress((out_dir / "dfe.db.gz").read_bytes()))
    with sqlite3.connect(restored) as conn:
        uv = conn.execute("PRAGMA user_version").fetchone()[0]
    with sqlite3.connect(migrated_db) as conn:
        original = conn.execute("PRAGMA user_version").fetchone()[0]
    assert uv == original


def test_export_e_deterministico(migrated_db: Path, tmp_path: Path) -> None:
    """Mesma base -> mesmo sha (gzip sem mtime), para o sha versionado ser estavel."""
    cmd_export(_args(migrated_db, tmp_path / "a"))
    cmd_export(_args(migrated_db, tmp_path / "b"))
    sha_a = (tmp_path / "a" / "dfe.db.gz.sha256").read_text(encoding="utf-8")
    sha_b = (tmp_path / "b" / "dfe.db.gz.sha256").read_text(encoding="utf-8")
    assert sha_a == sha_b


def test_export_nao_deixa_snapshot_temporario(migrated_db: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    cmd_export(_args(migrated_db, out_dir))
    assert sorted(p.name for p in out_dir.iterdir()) == ["dfe.db.gz", "dfe.db.gz.sha256"]


def test_export_aceita_path_com_caracteres_especiais(tmp_path: Path) -> None:
    db_dir = tmp_path / "base #1 %20"
    db_path = db_dir / "dfe.db"
    cmd_migrate(type("Args", (), {"db_path": db_path})())
    assert cmd_export(_args(db_path, tmp_path / "out")) == 0


def test_export_snapshot_sem_wal(tmp_path: Path) -> None:
    db_path = tmp_path / "wal" / "dfe.db"
    cmd_migrate(type("Args", (), {"db_path": db_path})())
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
    out_dir = tmp_path / "out"
    cmd_export(_args(db_path, out_dir))
    restored = tmp_path / "restored.db"
    restored.write_bytes(gzip.decompress((out_dir / "dfe.db.gz").read_bytes()))
    with sqlite3.connect(restored) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"


def test_export_sem_db(tmp_path: Path, capsys) -> None:
    rc = cmd_export(_args(tmp_path / "missing.db", tmp_path / "out"))
    assert rc == 1
    assert "nao encontrado" in capsys.readouterr().err.lower()
