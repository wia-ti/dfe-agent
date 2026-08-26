"""Retry linear com backoff entre tentativas.

Quando uma excecao do tipo listado em ``exceptions`` e levantada, dorme
``backoff_seconds * numero_da_tentativa`` segundos antes da proxima tentativa.
Excecoes fora do tuple propagam imediatamente sem retry.
"""
from __future__ import annotations

import time
from typing import Callable, TypeVar

T = TypeVar("T")


def retry(
    func: Callable[[], T],
    attempts: int = 3,
    backoff_seconds: float = 1.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    """Executa ``func`` ate o sucesso ou ate esgotar ``attempts``.

    Args:
        func: callable sem argumentos a ser executado. Seu retorno (de tipo ``T``)
            sera propagado ao chamador.
        attempts: numero maximo de tentativas (>=1). Defaults a 3.
        backoff_seconds: fator de linear backoff. O sono antes da tentativa
            ``n+1`` e ``backoff_seconds * n`` segundos. Defaults a 1.0.
        exceptions: tuple de tipos de excecao que justificam retry. Defaults a
            ``(Exception,)`` — apenas subclasses nao-listadas propagam sem retry.

    Returns:
        O valor retornado por ``func`` na primeira tentativa bem-sucedida.

    Raises:
        BaseException: a ultima excecao capturada quando ``attempts`` se esgota;
            ou, imediatamente, qualquer excecao fora de ``exceptions``.
    """
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except exceptions:
            if attempt >= attempts:
                raise
            time.sleep(backoff_seconds * attempt)

    raise RuntimeError("retry: loop exited without return or raise")
