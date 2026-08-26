"""Gera embeddings Py (sentence-transformers) para o teste de paridade D.7.

@see PLAN_SPRINT14.md Task D.3

Uso:
    python -m tests.integration.generate_py_embeddings

Saida:
    tests/fixtures/embeddings_py.json  (lista de listas, 384-d cada)

Gate: D.7 exige cosine similarity >= 0.99 entre Py e Node.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
EVAL_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "eval_set.json"
OUT_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "embeddings_py.json"


def main() -> None:
    eval_set = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    sentences = [item["question"] for item in eval_set]

    print(f"modelo: {MODEL_NAME}")
    print(f"sentencas: {len(sentences)}")

    model = SentenceTransformer(MODEL_NAME)
    embeddings = model.encode(sentences, normalize_embeddings=True)

    print(f"shape: {embeddings.shape}")
    assert embeddings.shape == (len(sentences), 384), (
        f"shape inesperada: {embeddings.shape}"
    )

    # Salva como lista de listas para JSON
    OUT_PATH.write_text(
        json.dumps(embeddings.tolist(), indent=None, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"salvo: {OUT_PATH} ({OUT_PATH.stat().st_size} bytes)")


if __name__ == "__main__":
    main()