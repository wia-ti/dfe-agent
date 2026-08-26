"""Constantes de schema para o DFe-Agent.

SCHEMA_SQL: DDL relacional lido de schema.sql no momento da importacao.
Mantemos o arquivo ``schema.sql`` como fonte canonica do DDL (legivel para
DBAs, ferramentas de migracao, etc.) e expomos a string via este modulo
Python para uso programatico (executar via ``sqlite3.Connection.executescript``).
"""
from __future__ import annotations

from pathlib import Path

_SCHEMA_SQL_PATH: Path = Path(__file__).resolve().parent / "schema.sql"
SCHEMA_SQL: str = _SCHEMA_SQL_PATH.read_text(encoding="utf-8")

# Versao canonica do schema (linha de base antes de migrations).
# Por design, esta versao NAO muda quando uma migration nova e adicionada:
# a migration incrementa ``PRAGMA user_version`` e a linha de base
# (``schema.sql``) continua representando o v1.
SCHEMA_BASELINE_VERSION: int = 1
