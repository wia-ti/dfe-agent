"""Testes do guardrail de veracidade e do montador de contexto (src.query.context_builder).

Cobre:
    - build_context: juncao de blocos [Fonte: titulo - publicado em DATA - url] separados por ---.
    - build_context: omite data quando published_at e None.
    - has_sufficient_evidence: True quando ha pelo menos 1 chunk com score >= min.
    - NO_EVIDENCE_MESSAGE: constante exportada e literal esperada.
"""
from __future__ import annotations

from datetime import datetime

from src.db.vector_store import ScoredChunk
from src.query.context_builder import (
    NO_EVIDENCE_MESSAGE,
    build_context,
    has_sufficient_evidence,
)


def _chunk(
    text: str,
    url: str,
    title: str,
    score: float,
    published_at: datetime | None = None,
) -> ScoredChunk:
    """Construtor ergonomico para ScoredChunk em testes."""
    return ScoredChunk(
        text=text,
        source_url=url,
        doc_title=title,
        score=score,
        published_at=published_at,
    )


def test_build_context_with_multiple_chunks_includes_all_urls_and_titles_separated_by_dashes() -> None:
    """build_context une todos os chunks com titulo+url em cada bloco, separados por ---."""
    pub = datetime(2026, 8, 4)
    ranked: list[ScoredChunk] = [
        _chunk("texto do doc 1", "https://nfe.fazenda.gov.br/nt-001.pdf", "NT 2019.001", 0.9, published_at=pub),
        _chunk("texto do doc 2", "https://confaz.fazenda.gov.br/conv-123.pdf", "Convenio 123/2024", 0.8, published_at=pub),
    ]

    context = build_context(ranked)

    assert "[Fonte: NT 2019.001 - publicado em 2026-08-04 - https://nfe.fazenda.gov.br/nt-001.pdf]" in context
    assert "[Fonte: Convenio 123/2024 - publicado em 2026-08-04 - https://confaz.fazenda.gov.br/conv-123.pdf]" in context
    assert "texto do doc 1" in context
    assert "texto do doc 2" in context
    assert "\n---\n" in context
    parts = context.split("\n---\n")
    assert len(parts) == 2


def test_build_context_with_empty_list_returns_empty_string() -> None:
    """build_context([]) -> string vazia (guard contra contexto vazio para o LLM)."""
    context = build_context([])
    assert context == ""


def test_build_context_omits_published_at_when_none() -> None:
    """Quando published_at e None, o bloco nao inclui 'publicado em' e o
    cabecalho fica com formato limpo ``[Fonte: titulo - url]`` (sem ' -  - ')."""
    ranked: list[ScoredChunk] = [
        _chunk("texto", "https://nfe.fazenda.gov.br/nt.pdf", "NT 2019.001", 0.9),
    ]
    context = build_context(ranked)
    assert "publicado em" not in context
    assert "[Fonte: NT 2019.001 - https://nfe.fazenda.gov.br/nt.pdf]" in context


def test_has_sufficient_evidence_returns_true_when_score_above_threshold() -> None:
    """has_sufficient_evidence([chunk com score >= min]) -> True."""
    ranked: list[ScoredChunk] = [_chunk("t", "u", "T", 0.9)]
    assert has_sufficient_evidence(ranked) is True


def test_has_sufficient_evidence_returns_false_when_empty() -> None:
    """has_sufficient_evidence([]) -> False (nada para fundamentar resposta)."""
    assert has_sufficient_evidence([]) is False


def test_has_sufficient_evidence_returns_false_when_score_below_threshold() -> None:
    """has_sufficient_evidence([chunk com score abaixo do min]) -> False."""
    ranked: list[ScoredChunk] = [_chunk("t", "u", "T", 0.3)]
    assert has_sufficient_evidence(ranked) is False


def test_has_sufficient_evidence_uses_custom_min_score() -> None:
    """Parametro min_score customizado e respeitado (parametro opcional)."""
    ranked: list[ScoredChunk] = [_chunk("t", "u", "T", 0.6)]
    assert has_sufficient_evidence(ranked, min_score=0.5) is True
    assert has_sufficient_evidence(ranked, min_score=0.8) is False


def test_has_sufficient_evidence_uses_first_chunk_score_only() -> None:
    """Decisao de design: apenas o PRIMEIRO chunk e checado (mais relevante)."""
    ranked: list[ScoredChunk] = [
        _chunk("relevante", "u1", "T1", 0.9),
        _chunk("fraco", "u2", "T2", 0.1),
    ]
    assert has_sufficient_evidence(ranked) is True


def test_no_evidence_message_constant_exists() -> None:
    """NO_EVIDENCE_MESSAGE deve existir com a string exata esperada pelo agente."""
    assert NO_EVIDENCE_MESSAGE == "Nao encontrei base para responder"
