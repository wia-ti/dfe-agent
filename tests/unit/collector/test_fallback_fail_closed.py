"""Testes do fallback fail-closed do guardrail de dominio (PLAN_SPRINT4.md A.1).

Garante que, quando o modulo ``domain_guard`` (ou o package ``hooks`` que
o contem) NAO pode ser importado, o coletor LEVANTA ``RuntimeError``
em vez de cair silenciosamente em um stub permissivo (``return True``).

Sem esse comportamento, qualquer config quebrada do guardrail abriria
a porta para o coletor baixar de dominios arbitrarios (fail-open),
violando a regra "Anti-bot como politica" e o guardrail inviolavel do
AGENTS.md (Regra seguranca).

Cenarios cobertos:
    - Import de ``src.collector.downloader`` levanta ``RuntimeError`` quando
      o guardrail nao pode ser importado.
    - Import de ``src.collector.portal_index`` levanta ``RuntimeError`` na
      mesma condicao.
    - Nenhum ``return True`` aparece dentro de funcoes nomeadas
      ``validate_url`` em ``src/collector/`` (regressao do stub).
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest


PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]


@pytest.fixture
def disabled_guardrail(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Desativa o guardrail para o teste: limpa sys.modules + remove path.

    A flag ``DFE_DISABLE_HOOKS_BOOTSTRAP`` impede que
    ``src/collector/__init__.py`` adicione ``.opencode/`` de volta
    durante o ``importlib.import_module``.

    Garante restauracao completa de ``sys.path`` e ``sys.modules`` apos
    o teste para nao contaminar a suite.

    Tambem limpa modulos em ``src/`` que importam ``hooks.domain_guard``
    transitivamente (ex.: ``src.utils.http_guard``), para que o teste
    simule com fidelidade o estado "guardrail indisponivel".
    """
    _GUARDRAIL_DEPENDENT_MODULES = (
        "domain_guard",
        "hooks",
        "src.collector",
        "src.collector.__main__",
        "src.utils.http_guard",
    )

    def _is_guardrail_dependent(name: str) -> bool:
        if name in _GUARDRAIL_DEPENDENT_MODULES:
            return True
        if name.startswith("hooks."):
            return True
        if name.startswith("src.collector."):
            return True
        return False

    monkeypatch.setenv("DFE_DISABLE_HOOKS_BOOTSTRAP", "1")

    saved_path: list[str] = list(sys.path)
    saved_modules: dict[str, object] = {
        name: mod
        for name, mod in list(sys.modules.items())
        if _is_guardrail_dependent(name)
    }

    for name in list(sys.modules):
        if _is_guardrail_dependent(name):
            sys.modules.pop(name, None)

    sys.path[:] = [p for p in sys.path if ".opencode" not in p]

    try:
        yield
    finally:
        for name in list(sys.modules):
            if _is_guardrail_dependent(name):
                sys.modules.pop(name, None)
        for name, mod in saved_modules.items():
            sys.modules[name] = mod
        sys.path[:] = saved_path


def test_collector_raises_when_domain_guard_missing(
    disabled_guardrail: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``from src.collector.downloader import DocumentCollector`` levanta RuntimeError.

    Estrategia:
        - Limpa ``sys.modules`` dos modulos do guardrail.
        - Remove o path ``.opencode`` para forcar ImportError.
        - Tenta importar o coletor; espera RuntimeError com substring
          ``"domain_guard indisponivel"``.
    """
    monkeypatch.syspath_prepend(str(PROJECT_ROOT / "src"))
    monkeypatch.syspath_prepend(str(PROJECT_ROOT))

    with pytest.raises(RuntimeError, match="domain_guard indisponivel"):
        importlib.import_module("src.collector.downloader")


def test_portal_index_raises_when_domain_guard_missing(
    disabled_guardrail: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``from src.collector.portal_index import PORTAL_URLS`` levanta RuntimeError.

    Analogo a ``test_collector_raises_when_domain_guard_missing`` mas
    para o modulo ``portal_index``.
    """
    monkeypatch.syspath_prepend(str(PROJECT_ROOT / "src"))
    monkeypatch.syspath_prepend(str(PROJECT_ROOT))

    with pytest.raises(RuntimeError, match="domain_guard indisponivel"):
        importlib.import_module("src.collector.portal_index")


def test_collector_module_has_no_permissive_return_true_stub() -> None:
    """Garantia estatica: nenhuma funcao ``validate_url`` em ``src/collector/``
    pode conter literal ``return True`` (seria regressao do stub fail-open).

    Verificacao feita via leitura de fonte (regex) e nao por import,
    porque queremos validar o codigo independentemente de sys.path.
    """
    import re

    pattern_violation = re.compile(
        r"def\s+validate_url\b[^{]*\{[^}]*return\s+True",
        re.DOTALL,
    )
    offenders: list[tuple[Path, int, str]] = []
    for py_file in (PROJECT_ROOT / "src" / "collector").glob("*.py"):
        text: str = py_file.read_text(encoding="utf-8")
        for m in pattern_violation.finditer(text):
            line_no: int = text[: m.start()].count("\n") + 1
            snippet: str = m.group(0).splitlines()[0][:80]
            offenders.append((py_file, line_no, snippet))

    assert offenders == [], (
        "Encontrado stub permissivo 'return True' em validate_url: "
        + ", ".join(f"{p.name}:{ln} ({s})" for p, ln, s in offenders)
    )
