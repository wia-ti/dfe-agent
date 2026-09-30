"""Mapeamento de arquivo editado -> suite pytest correspondente.

Cada agent de implementacao roda pytest em um subset diferente:
    - dev:              owner de TODO o projeto (Sprint 10); roda TODAS as
                        suites aplicaveis para qualquer path do projeto.

Pre-Sprint 11 existiam 3 agents com escopo parcial:
    - backend-engineer: src/collector, src/db, src/query, src/utils, src/parser
    - ml-engineer:      src/indexer
    - prompt-engineer:  N/A (arquivos .md validados por regex,
                        sem testes pytest por enquanto)

Esses 3 agents foram removidos em Sprint 11 C.2; ``dev`` absorveu
todos os escopos.

A funcao principal :func:`suites_for_path` recebe o caminho do arquivo
modificado e devolve a lista de suites pytest a executar (vazio = nada
a rodar). O resultado e uma lista para suportar caminhos compartilhados
(ex.: ``src/parser/html_parser.py`` e coberto pela suite ``parser/``).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable

PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]

_BACKEND_SUITES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^src/collector/"), "tests/unit/collector"),
    (re.compile(r"^src/parser/"),    "tests/unit/parser"),
    (re.compile(r"^src/db/"),        "tests/unit/db"),
    (re.compile(r"^src/query/"),     "tests/unit/query"),
    (re.compile(r"^src/utils/"),     "tests/unit/utils"),
    (re.compile(r"^src/ragctl\.py$|^src/db/migrations/"), "tests/unit/test_ragctl.py tests/unit/test_ragctl_backfill.py"),
]

_ML_SUITES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^src/indexer/"),   "tests/unit/indexer"),
    (re.compile(r"^src/db/vector_store\.py$|^src/db/parent_chunks\.py$|^src/db/doc_summaries\.py$|^src/db/fts_store\.py$"),
     "tests/unit/db/test_parent_chunks.py tests/unit/db/test_doc_summaries.py tests/unit/db/test_fts_store.py tests/unit/db/test_vector_store.py"),
]


def _relpath(path: str) -> str:
    p = Path(path)
    try:
        return str(p.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(p).replace("\\", "/")


def suites_for_path(rel_path: str, agent: str) -> list[str]:
    """Retorna suites pytest a executar apos edicao de ``rel_path``.

    Agentes canonicos (PLAN_SPRINT11 C, PLAN_SPRINT18):
        - ``"dev"`` (Sprint 10 B.4, owner de TODO o projeto): retorna
          todas as suites aplicaveis (uniao de ``_BACKEND_SUITES`` e
          ``_ML_SUITES``) para garantir que qualquer edicao passe pelo
          gate pytest correspondente.
        - ``"deployer"`` (Sprint 18 D18.9): retorna suite vazia. Deployer
          NAO testa codigo (e' acao atomica de git/npm/gh release).
        - qualquer outro slug: retorna suite vazia (nao ha mais agents
          legacy com escopo restrito; pre-Sprint 11, ``backend-engineer``
          e ``ml-engineer`` tinham escopos parciais que foram consolidados
          em ``dev``).
    """
    if agent == "dev":
        tables = (_BACKEND_SUITES, _ML_SUITES)
    else:
        tables: tuple[list[tuple[re.Pattern[str], str]], ...] = ()
    rel_path = rel_path.replace("\\", "/").lstrip("./")
    suites: list[str] = []
    for table in tables:
        for pattern, suite in table:
            if pattern.search(rel_path) and suite not in suites:
                suites.append(suite)
    return suites


def run_pytest(suites: Iterable[str], timeout: int = 120) -> tuple[int, str]:
    """Roda pytest em ``suites`` (string com paths separados por espaco).

    Retorna ``(returncode, output)``. Nao levanta em caso de falha de teste.
    """
    suites_list = [s for s in suites if s]
    if not suites_list:
        return 0, "[skip] nenhuma suite aplicavel"
    args = [sys.executable, "-m", "pytest", "-q", "--no-header", *suites_list]
    try:
        proc = subprocess.run(
            args,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 124, f"pytest timeout ({timeout}s) em: {' '.join(suites_list)}"
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output[-2000:]


__all__ = [
    "PROJECT_ROOT",
    "suites_for_path",
    "run_pytest",
    "_relpath",
]
