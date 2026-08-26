"""Regressao de B7 (PLAN_SPRINT7 A.5): o CLI ``python -m src.query``
nao levanta ``RuntimeError("domain_guard indisponivel")`` quando invocado
a partir do cwd do projeto (modo real de uso), mesmo sem ``PYTHONPATH``.

Origem: o import top-level de ``hooks.domain_guard`` em
``src.utils.http_guard`` exigia que o diretorio ``.opencode/`` estivesse em
``sys.path``. Antes do PLAN_SPRINT7, isso so' funcionava via
``tests/conftest.py`` + workaround manual em
``tests/unit/query/test_main.py``. Apos o bootstrap automatico introduzido
em A.2, o CLI deve rodar em subprocesso a partir do cwd do projeto sem
``PYTHONPATH`` apontando para ``.opencode``.

Escopo deste teste: subprocess a partir do cwd do projeto (modo real
de uso: terminal do usuario, agente opencode). Subprocess em
``cwd=tmp_path`` continua precisando de ``PYTHONPATH=<project_root>``
porque o Python precisa localizar o pacote ``src`` em sys.path para
resolver ``-m src.query``.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]


def _run_query_cli_cwd_project(*args: str) -> subprocess.CompletedProcess:
    """Executa ``python -m src.query <args>`` a partir do cwd do projeto
    (modo real) sem manipulacao de ``PYTHONPATH``.

    Este caminho cobre exatamente o cenario do usuario: ele abre um
    PowerShell no diretorio do projeto e roda ``python -m src.query
    "pergunta"``. O bootstrap de A.2 e' que precisa garantir que
    ``hooks.domain_guard`` seja encontrado.
    """
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("COV_CORE_SOURCE", None)
    env.pop("COV_CORE_CONFIG", None)
    env["HF_HUB_OFFLINE"] = "1"
    env["OPENBLAS_NUM_THREADS"] = "1"
    env["OMP_NUM_THREADS"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "src.query", *args],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        env=env,
        check=False,
    )


def test_cli_runs_without_opencode_pythonpath() -> None:
    """B7 resolvido: CLI roda do cwd do projeto sem PYTHONPATH e sem
    levantar ``RuntimeError("domain_guard indisponivel")``.
    """
    result = _run_query_cli_cwd_project("qualquer pergunta")
    combined = (result.stdout or "") + (result.stderr or "")
    assert "domain_guard indisponivel" not in combined, (
        f"B7 ainda nao resolvido. stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "ModuleNotFoundError: No module named 'hooks'" not in combined


def test_cli_returns_clean_no_evidence_from_project_root() -> None:
    """Saida do CLI do cwd do projeto: JSON com NO_EVIDENCE_MESSAGE ou
    resposta; nunca um traceback.
    """
    result = _run_query_cli_cwd_project("qualquer pergunta")
    assert result.returncode == 0, (
        f"CLI retornou exit != 0 ({result.returncode}); "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "Traceback" not in (result.stdout + (result.stderr or ""))
    assert "Traceback" not in (result.stderr or "")


def test_cli_imports_via_subprocess_succeeds() -> None:
    """Verifica que o top-level do modulo CLI importa limpo em subprocess
    a partir do cwd do projeto, sem ``PYTHONPATH``.
    """
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-c", "import src.query.__main__"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        env=env,
        check=False,
    )
    assert result.returncode == 0, (
        f"Falha ao importar src.query.__main__: "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )

