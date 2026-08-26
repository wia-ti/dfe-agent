"""Chunker com emissao de parent + detail (Sprint 2, Fase 14.1).

Algoritmo:
    1. Divide o texto em paragrafos via quebra dupla (``\\n\\n``).
    2. Para cada paragrafo com >= 2 sentences:
       - Emite um ``parent`` chunk com o texto integral.
       - Emite 1+ ``detail`` chunks via :func:`chunker.chunk_text`,
         cada um apontando para o parent via ``parent_chunk_id``.
    3. Para paragrafos com < 2 sentences: emite um unico ``detail``
       sem parent (compat).

Vantagem:
    - Precision alta (embeddings em chunks pequenos/densos) + retrieval
      com contexto (parent paragraph inteiro retornado no ScoredChunk).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from src.indexer.chunker import chunk_text

_SENTENCE_SEPARATORS: re.Pattern[str] = re.compile(r"(?<=[.!?\n])\s+")


@dataclass
class ParentChunk:
    """Chunk pai (paragrafo inteiro)."""

    chunk_index: int
    text: str
    kind: str = "parent"


@dataclass
class DetailChunk:
    """Chunk detail (trecho menor)."""

    chunk_index: int
    text: str
    parent_chunk_id: int | None
    kind: str = "detail"


def _split_paragraphs(text: str) -> list[str]:
    parts: list[str] = text.split("\n\n")
    return [p.strip() for p in parts if p.strip()]


def _split_sentences(text: str) -> list[str]:
    if not text.strip():
        return []
    return [
        s.strip() for s in _SENTENCE_SEPARATORS.split(text) if s.strip()
    ]


def chunk_with_parents(
    text: str,
    chunk_size: int = 600,
    chunk_overlap: int = 80,
    min_parent_sentences: int = 2,
) -> tuple[list[ParentChunk], list[DetailChunk]]:
    """Decomp ``text`` em parents + details.

    Returns:
        (parents, details): listas paralelas. ``details[i].parent_chunk_id``
            aponta (quando definido) para ``parents[j].chunk_index``.

    Apenas detalhes sao embedados; parents existem para o JOIN em
    VectorStore.search retornar contexto no ``parent_text``.
    """
    if not text or not text.strip():
        return [], []

    parents: list[ParentChunk] = []
    details: list[DetailChunk] = []

    next_idx: int = 0
    for paragraph in _split_paragraphs(text):
        sentences: list[str] = _split_sentences(paragraph)
        if len(sentences) >= min_parent_sentences:
            # Emite parent.
            parent_id: int = next_idx
            parents.append(
                ParentChunk(
                    chunk_index=parent_id,
                    text=paragraph,
                )
            )
            next_idx += 1
            # Emite details que apontam pro parent.
            for detail_text in chunk_text(
                paragraph, chunk_size=chunk_size, chunk_overlap=chunk_overlap
            ):
                details.append(
                    DetailChunk(
                        chunk_index=next_idx,
                        text=detail_text,
                        parent_chunk_id=parent_id,
                    )
                )
                next_idx += 1
        else:
            # Paragraph curto: detail sem parent.
            details.append(
                DetailChunk(
                    chunk_index=next_idx,
                    text=paragraph,
                    parent_chunk_id=None,
                )
            )
            next_idx += 1

    return parents, details


__all__ = ["DetailChunk", "ParentChunk", "chunk_with_parents"]
