"""Testes para src.indexer.embeddings.

Cobre (PLAN.md linha 164 - Task 5.1):
    - [x] EmbeddingProvider().embed(["NF-e"]) retorna lista com 1 elemento
          de comprimento 384 e norma L2 > 0.
    - [x] embed() aceita multiplos textos e retorna 1 vetor por texto.
    - [x] dim retorna 384 (dimensao do modelo padrao).

Estrategia de skip:
    Estes testes exigem que o modelo sentence-transformers seja carregado
    (download na primeira execucao, ~470MB para o modelo padrao). Sao
    marcados com ``@pytest.mark.slow`` para permitir exclusao via
    ``-m "not slow"`` na suite padrao, e usam ``pytest.importorskip`` para
    pular graciosamente caso sentence-transformers nao esteja instalado.

    Para rodar:
        pytest tests/unit/indexer/test_embeddings.py -v -m slow --no-cov
"""
from __future__ import annotations

import math

import pytest

# Skip se sentence-transformers nao estiver instalado.
sentence_transformers = pytest.importorskip("sentence_transformers")

from src.indexer.embeddings import DEFAULT_MODEL_NAME, EmbeddingProvider  # noqa: E402


# Modelo pequeno e rapido para os testes (384 dim, ~80MB) — mesmo dim do
# modelo padrao, mas download mais leve. Para pular totalmente o download,
# use o modelo padrao se ja estiver em cache.
_TEST_MODEL_NAME: str = "all-MiniLM-L6-v2"


# --- marcadores e fixtures ---


pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def embedder() -> EmbeddingProvider:
    """Cria um EmbeddingProvider para uso em testes (modelo pequeno)."""
    return EmbeddingProvider(model_name=_TEST_MODEL_NAME)


# --- testes criticos (PLAN.md linha 164) ---


def test_embed_returns_correct_dimension(embedder: EmbeddingProvider) -> None:
    """embed(["NF-e"]) retorna 1 vetor de dimensao 384 com norma L2 > 0."""
    vectors = embedder.embed(["NF-e"])

    assert isinstance(vectors, list)
    assert len(vectors) == 1
    vector = vectors[0]
    assert isinstance(vector, list)
    assert len(vector) == 384
    # Norma L2 > 0 (vetor nao e o zero).
    norm: float = math.sqrt(sum(x * x for x in vector))
    assert norm > 0, f"norma L2 deveria ser > 0, recebi {norm}"


def test_embed_multiple_texts(embedder: EmbeddingProvider) -> None:
    """embed([t1, t2, t3]) retorna 3 vetores de dimensao 384 cada."""
    texts = ["NF-e nota fiscal", "CT-e conhecimento de transporte", "MDF-e manifesto"]
    vectors = embedder.embed(texts)

    assert len(vectors) == 3
    for vector in vectors:
        assert len(vector) == 384
        norm: float = math.sqrt(sum(x * x for x in vector))
        assert norm > 0


def test_dim_property_returns_384(embedder: EmbeddingProvider) -> None:
    """A propriedade ``dim`` retorna 384 (dimensao do modelo carregado)."""
    assert embedder.dim == 384


# --- testes de lazy load e API ---


def test_embedding_provider_lazy_loads_model() -> None:
    """Instanciar o provider NAO dispara load do modelo."""
    # Criamos uma instancia sem chamar embed/dim.
    provider = EmbeddingProvider(model_name=_TEST_MODEL_NAME)
    assert provider._model is None, (
        "modelo nao deveria ter sido carregado na instanciação (lazy load)"
    )


def test_embedding_provider_loads_model_on_first_embed() -> None:
    """O modelo e carregado apenas na primeira chamada de embed()."""
    provider = EmbeddingProvider(model_name=_TEST_MODEL_NAME)
    assert provider._model is None
    provider.embed(["hello"])
    assert provider._model is not None


def test_embedding_provider_loads_model_on_dim_access() -> None:
    """A propriedade ``dim`` dispara o load do modelo."""
    provider = EmbeddingProvider(model_name=_TEST_MODEL_NAME)
    assert provider._model is None
    _ = provider.dim
    assert provider._model is not None


def test_embedding_provider_default_model_name() -> None:
    """O nome do modelo padrao e o multilingual MiniLM."""
    assert DEFAULT_MODEL_NAME == "paraphrase-multilingual-MiniLM-L12-v2"


def test_embedding_provider_model_name_attribute() -> None:
    """O atributo ``_model_name`` armazena o nome configurado."""
    provider = EmbeddingProvider(model_name="custom-model")
    assert provider._model_name == "custom-model"


# --- testes de comportamento do embedding ---


def test_embed_similar_texts_have_higher_similarity_than_dissimilar(
    embedder: EmbeddingProvider,
) -> None:
    """Textos semanticamente similares produzem vetores mais proximos."""
    vectors = embedder.embed(
        ["Nota fiscal eletronica NF-e", "Documento auxiliar NF-e", "Receita de bolo"]
    )

    # Calcula similaridade cosseno entre pares.
    def cosine(a: list[float], b: list[float]) -> float:
        dot: float = sum(x * y for x, y in zip(a, b))
        na: float = math.sqrt(sum(x * x for x in a))
        nb: float = math.sqrt(sum(y * y for y in b))
        return dot / (na * nb)

    sim_similar: float = cosine(vectors[0], vectors[1])
    sim_dissimilar: float = cosine(vectors[0], vectors[2])

    assert sim_similar > sim_dissimilar, (
        f"textos similares deveriam ter cosseno maior: "
        f"sim({sim_similar:.3f}) vs dissim({sim_dissimilar:.3f})"
    )


def test_embed_empty_list_returns_empty_list(embedder: EmbeddingProvider) -> None:
    """embed([]) retorna lista vazia (sem vetores)."""
    vectors = embedder.embed([])
    assert vectors == []
