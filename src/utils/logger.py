"""Logger factory com formatacao padrao e sem duplicacao via propagate=False."""
from __future__ import annotations

import logging


_LOG_FORMAT: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Retorna um ``logging.Logger`` configurado com ``StreamHandler`` e formatador padrao.

    O logger retornado NAO propaga para o root logger (propagate=False) para
    evitar mensagens duplicadas quando o host (ex.: pytest, opencode) ja
    configura handlers no root. Idempotente: chamadas repetidas com o mesmo
    ``name`` nao adicionam handlers duplicados.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        logger.addHandler(handler)

    return logger
