"""Reproducao controlada do sintoma ``(no output)`` de I7.2.

Hipotese registrada no PLAN_SPRINT7: as chamadas ``python -m src.query
--hybrid "..."`` que retornaram ``(no output)`` no PowerShell do usuario
em 2026-08-26 sofriam do mesmo ``UnicodeEncodeError`` da BLOQUEANTE B8
(cp1252 stdout). Apos B.1 (helper ``_configure_utf8_stdout``) ser aplicado,
o problema fica resolvido por tabela.

Este modulo garante que:
    - ``_build_answer`` aceita chunks cujo contexto tem bullet UTF-8
      (``\\uf0b7``) e produz dicionario serializavel com
      ``json.dumps(..., ensure_ascii=False)``.
    - O CLI imprime em stderr uma linha ``[query] sem chunks
      relevantes`` quando a busca retorna vazio (D.2).
    - O NO_EVIDENCE_MESSAGE canonico continua sendo usado.
"""
from __future__ import annotations

import json
from unittest import mock

import pytest

from src.query.__main__ import _build_answer


def _stub_chunk(content: str, *, url: str = "https://example.gov/doc") -> mock.Mock:
    """Constroi um ScoredChunk-like com ``content`` UTF-8 arbitrario."""
    chunk = mock.Mock()
    chunk.content = content
    chunk.doc_title = "Doc com bullet"
    chunk.source_url = url
    chunk.score = 0.95
    return chunk


def test_build_answer_with_utf8_context_serializes() -> None:
    """Contexto com bullet/emojis serializa sem UnicodeEncodeError."""
    chunks = [_stub_chunk("Texto \uf0b7 com bullet e emoji \U0001F7E2.")]
    # has_sufficient_evidence e' monkey-patched para True para exercitar
    # o caminho de "com chunks relevantes" (nao NO_EVIDENCE_MESSAGE).
    with mock.patch(
        "src.query.__main__.has_sufficient_evidence", return_value=True
    ), mock.patch(
        "src.query.__main__.build_context", return_value="ctx \uf0b7"
    ):
        response = _build_answer("pergunta", chunks)
    assert "answer" in response
    assert "sources" in response
    raw = json.dumps(response, ensure_ascii=False)
    assert "\uf0b7" in raw
    assert raw.endswith("}")


def test_build_answer_returns_no_evidence_for_empty(capsys) -> None:
    """Ranked vazio -> NO_EVIDENCE_MESSAGE + log em stderr (D.2)."""
    with mock.patch(
        "src.query.__main__.has_sufficient_evidence", return_value=False
    ):
        response = _build_answer("pergunta", [])
    assert response == {"answer": "Nao encontrei base para responder", "sources": []}
    captured = capsys.readouterr()
    assert "[query] sem chunks relevantes" in captured.err
    assert "count=0" in captured.err


def test_build_answer_returns_no_evidence_for_below_threshold(capsys) -> None:
    """Chunks com score abaixo do threshold -> mesma resposta + log."""
    with mock.patch(
        "src.query.__main__.has_sufficient_evidence", return_value=False
    ):
        response = _build_answer("pergunta", [_stub_chunk("x")])
    assert response["answer"] == "Nao encontrei base para responder"
    captured = capsys.readouterr()
    assert "[query] sem chunks relevantes" in captured.err
    assert "count=1" in captured.err
