"""Testes do diagnostico de falha de load do embedding (PLAN_SPRINT5 F.1).

Cobre:
    - ``OSError 1455`` (page file do Windows insuficiente) e' envolvido
      em ``RuntimeError`` com mensagem acionavel que aponta para
      ``DFE_EMBEDDING_DTYPE=float16`` (workaround canonico).
    - Qualquer outro ``OSError`` NAO e' mascarado — passa direto para
      o caller (protege contra falsos positivos que escondem bugs de
      filesystem / permission / file-not-found).

Origem do problema (achado da revisao de 2026-08-25):
    O arquivo ``scripts/answer_nf_e_10_2026.py`` (descartado em F.2)
    foi gerado pelo proprio agente LLM apos o CLI ``python -m
    src.query`` retornar ``NO_EVIDENCE_MESSAGE`` em razao de
    ``OSError 1455`` no load do ``paraphrase-multilingual-MiniLM-L12-v2``.
    O agente interpretou "sem evidencia" como "CLI quebrado" e escreveu
    SQL raw, contornando o guardrail de veracidade. Esta tarefa
    blindou o caminho: o stack trace agora vem com workaround canonico
    e o agente nao precisa improvisar.
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from src.indexer.embeddings import (
    DEFAULT_EMBEDDING_DTYPE,
    DEFAULT_MODEL_NAME,
    EmbeddingProvider,
)


def test_load_oserror_1455_raises_runtimeerror_with_workaround(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``OSError(1455, ...)`` em ``SentenceTransformer(...)`` vira ``RuntimeError`` com workaround.

    Estrategia:
        - Monkeypatch ``sentence_transformers.SentenceTransformer`` para
          raise ``OSError(1455, "page file too small")``.
        - Instancia ``EmbeddingProvider`` (sem load).
        - Chama ``.dim`` para disparar ``_load``.
        - Espera ``RuntimeError`` com substring
          ``"DFE_EMBEDDING_DTYPE=float16"`` (workaround canonico).
    """
    target_exc: OSError = OSError(1455, "page file too small")

    def fake_sentence_transformer(*_args: object, **_kwargs: object) -> None:
        raise target_exc

    # Patch no modulo ja importado (sentence_transformers).
    with patch(
        "src.indexer.embeddings.SentenceTransformer",
        side_effect=fake_sentence_transformer,
    ):
        provider = EmbeddingProvider()
        with pytest.raises(RuntimeError) as exc_info:
            provider.dim

    msg: str = str(exc_info.value)
    assert "DFE_EMBEDDING_DTYPE=float16" in msg, (
        f"Mensagem de erro deveria conter workaround 'DFE_EMBEDDING_DTYPE=float16'. "
        f"Obtido: {msg!r}"
    )
    assert "all-MiniLM-L6-v2" in msg, (
        f"Mensagem deveria mencionar fallback 'all-MiniLM-L6-v2'. Obtido: {msg!r}"
    )
    # Chained exception preserva o OSError original.
    assert exc_info.value.__cause__ is target_exc


def test_load_other_oserror_passes_through_unmodified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``OSError`` que NAO e' 1455/page-file NAO e' mascarado.

    Garante que o try/except nao engole erros de filesystem legitimos
    (permission denied, file not found, invalid argument) — esses
    devem subir como ``OSError`` para o caller decidir o que fazer.
    """
    target_exc: OSError = OSError(22, "Invalid argument")

    def fake_sentence_transformer(*_args: object, **_kwargs: object) -> None:
        raise target_exc

    with patch(
        "src.indexer.embeddings.SentenceTransformer",
        side_effect=fake_sentence_transformer,
    ):
        provider = EmbeddingProvider()
        with pytest.raises(OSError) as exc_info:
            provider.dim

    assert exc_info.value is target_exc, (
        "OSError que nao e' 1455 deve passar direto, sem envelopamento em RuntimeError"
    )
    assert exc_info.value.errno == 22


__all__ = [
    "test_load_oserror_1455_raises_runtimeerror_with_workaround",
    "test_load_other_oserror_passes_through_unmodified",
]
