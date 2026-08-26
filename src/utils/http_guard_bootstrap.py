"""Bootstrapper idempotente para ``install_http_guard``.

Centraliza a instalacao do guard HTTP in-process para que entry-points
(``src.collector.__main__``, ``src.indexer.ingest``, ``src.query.__main__``)
nao dupliquem o monkey-patch quando invocados em processos aninhados ou
em sequencia durante uma mesma sessao de CLI.

Origem (PLAN_SPRINT5 A.1 / BLOQUEANTE B1):
    O guard rail de dominio precisa estar ativo em TODA chamada HTTP
    feita por entry-points CLI do DFe-Agent, nao apenas em
    ``collector.discover_documents`` (onde ``validate_url`` ja' e'
    aplicado manualmente). O monkey-patch em
    ``src.utils.http_guard.install_http_guard`` e' idempotente via
    flag de modulo (``_guards_installed``); este bootstrap exposto
    como uma funcao ``install_guard_once()`` para evitar que cada
    entry-point faca ``from src.utils.http_guard import
    install_http_guard`` diretamente.

Funcoes publicas:
    - ``install_guard_once()``: chama ``install_http_guard`` apenas
      uma vez por processo (via flag de modulo ``_BOOTSTRAP_DONE``).
      Idempotente: chamadas adicionais sao no-op.

Nao confundir com a flag interna ``_guards_installed`` em
``http_guard.py``: aquela e' para monkey-patch global de
``requests.get``; esta e' para evitar re-invocacao do bootstrap em si
(diagnostico / logs / metricas).
"""
from __future__ import annotations

from src.utils.http_guard import install_http_guard


_BOOTSTRAP_DONE: bool = False


def install_guard_once() -> None:
    """Instala o guard HTTP in-process exatamente uma vez.

    Chamadas subsequentes na mesma execucao do processo sao no-op
    (verificacao via ``_BOOTSTRAP_DONE``). A funcao
    ``install_http_guard`` subjacente ja' e' idempotente por
    construcao (``_guards_installed`` em ``http_guard.py``); este
    bootstrap adiciona uma camada extra para observabilidade.

    Entrypoints que devem chamar esta funcao:
        - ``src.collector.__main__.main``
        - ``src.indexer.ingest.main``
        - ``src.query.__main__.main``
    """
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    install_http_guard()
    _BOOTSTRAP_DONE = True


def was_bootstrap_called() -> bool:
    """Retorna ``True`` se ``install_guard_once`` ja' foi invocado no processo.

    Util para diagnosticos e testes que precisam verificar se
    determinado entry-point invocou o bootstrap antes de fazer I/O.
    """
    return _BOOTSTRAP_DONE


__all__ = ["install_guard_once", "was_bootstrap_called"]
