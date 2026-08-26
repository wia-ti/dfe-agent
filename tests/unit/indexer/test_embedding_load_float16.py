"""Teste da env var ``DFE_EMBEDDING_DTYPE`` (PLAN_SPRINT5 F.1).

Cobre:
    - Quando ``DFE_EMBEDDING_DTYPE=float16`` esta' definido antes da
      importacao do modulo, ``DEFAULT_EMBEDDING_DTYPE`` le esse valor
      (nao o default ``"float32"``).
    - Quando o env var NAO esta' definido, o default literal
      ``"float32"`` permanece.
    - ``EmbeddingProvider()`` sem argumento ``dtype`` herda o valor do
      env (``embedder._dtype == DEFAULT_EMBEDDING_DTYPE``).
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest


def test_env_var_dfe_embedding_dtype_overrides_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``DFE_EMBEDDING_DTYPE=float16`` antes do import define ``DEFAULT_EMBEDDING_DTYPE=float16``.

    Estrategia:
        - ``monkeypatch.setenv("DFE_EMBEDDING_DTYPE", "float16")`` ANTES
          do reload do modulo (a constante e' avaliada em module-load).
        - Recarrega ``src.indexer.embeddings``.
        - Verifica ``DEFAULT_EMBEDDING_DTYPE == "float16"``.
        - Instancia ``EmbeddingProvider()`` sem argumento ``dtype``.
        - Verifica ``embedder._dtype == "float16"``.
    """
    # Salva referencia ao modulo atual antes do reload.
    embeddings_module = sys.modules.get("src.indexer.embeddings")
    assert embeddings_module is not None, "src.indexer.embeddings precisa estar importado"

    monkeypatch.setenv("DFE_EMBEDDING_DTYPE", "float16")

    # Force reload para reavaliar a constante no module-level.
    importlib.reload(embeddings_module)

    assert embeddings_module.DEFAULT_EMBEDDING_DTYPE == "float16", (
        f"DEFAULT_EMBEDDING_DTYPE deveria ser 'float16' (env var), "
        f"obtido {embeddings_module.DEFAULT_EMBEDDING_DTYPE!r}"
    )

    provider = embeddings_module.EmbeddingProvider()
    assert provider._dtype == "float16", (
        f"EmbeddingProvider._dtype deveria herdar env var 'float16', "
        f"obtido {provider._dtype!r}"
    )


def test_env_var_unset_falls_back_to_float32(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sem ``DFE_EMBEDDING_DTYPE`` no env, default literal ``"float32"`` permanece."""
    embeddings_module = sys.modules.get("src.indexer.embeddings")
    assert embeddings_module is not None

    monkeypatch.delenv("DFE_EMBEDDING_DTYPE", raising=False)

    importlib.reload(embeddings_module)

    assert embeddings_module.DEFAULT_EMBEDDING_DTYPE == "float32", (
        f"DEFAULT_EMBEDDING_DTYPE deveria ser 'float32' (default), "
        f"obtido {embeddings_module.DEFAULT_EMBEDDING_DTYPE!r}"
    )

    provider = embeddings_module.EmbeddingProvider()
    assert provider._dtype == "float32"


__all__ = [
    "test_env_var_dfe_embedding_dtype_overrides_default",
    "test_env_var_unset_falls_back_to_float32",
]
