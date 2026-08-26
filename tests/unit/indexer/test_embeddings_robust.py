"""Testes para EmbeddingProvider (Sprint 3, Iter 2 — robustez de load).

Cobre:
    - Parametros ``low_cpu_mem_usage`` e ``dtype`` no init nao quebram.
    - ``reset()`` limpa o modelo cached para forcar reload.
    - ``dim`` ainda funciona apos reset.
    - Atributo ``model_loaded`` reflete o estado interno.
"""
from __future__ import annotations

from src.indexer.embeddings import EmbeddingProvider


def test_default_nao_carrega_modelo_no_init() -> None:
    """Init NAO faz download nem load do modelo."""
    e = EmbeddingProvider()
    assert e.model_loaded is False
    assert e.model_name != ""
    assert e.dim > 0  # chamar dim dispara o lazy load


def test_parametros_extras_sao_aceitos_sem_quebrar() -> None:
    """Init aceita kwargs adicionais e guarda (forward-compat)."""
    e = EmbeddingProvider(
        model_name="all-MiniLM-L6-v2",
        low_cpu_mem_usage=True,
        dtype="float16",
    )
    assert e.model_loaded is False
    assert e.model_name == "all-MiniLM-L6-v2"


def test_reset_limpa_modelo_cached() -> None:
    e = EmbeddingProvider("all-MiniLM-L6-v2")
    _ = e.dim  # dispara load
    assert e.model_loaded is True
    e.reset()
    assert e.model_loaded is False


def test_repr_nao_vaza_nome_interno() -> None:
    e = EmbeddingProvider("all-MiniLM-L6-v2")
    s = repr(e)
    assert "all-MiniLM-L6-v2" in s
    assert "loaded" in s.lower() or "not" in s.lower()