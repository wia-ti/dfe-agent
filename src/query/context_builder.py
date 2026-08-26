"""Montagem de contexto para o LLM e guardrail de veracidade.

Decisao de design:
    O contexto para o LLM e uma unica string com blocos ``[Fonte: titulo (data) - url]``
    concatenados por ``---``. Nao usamos listas/objetos porque a string sera
    injetada literalmente no prompt.

Coexistencia com Task 6.1:
    Este modulo depende apenas de ``ScoredChunk`` (Task 2.2) e de
    ``MIN_RELEVANCE_SCORE`` (Task 6.1). NAO importa ``QueryEngine`` para nao
    travar o modulo caso Task 6.1 ainda esteja em andamento.
"""
from __future__ import annotations

from src.db.vector_store import ScoredChunk
from src.query.constants import MIN_RELEVANCE_SCORE


NO_EVIDENCE_MESSAGE: str = "Nao encontrei base para responder"

_BLOCK_SEP: str = "\n---\n"


def _format_published_at(published_at) -> str:
    """Formata published_at como ' publicado em YYYY-MM-DD' ou '' se None."""
    if published_at is None:
        return ""
    return f" publicado em {published_at.strftime('%Y-%m-%d')}"


def build_context(ranked: list[ScoredChunk]) -> str:
    """Monta contexto para o LLM a partir de chunks ranqueados.

    Cada bloco tem o formato::

        [Fonte: {doc_title} - publicado em {YYYY-MM-DD} - {source_url}]
        {text}

    Quando ``published_at`` e None, o segmento de data e omitido (evita
    aparecer como ' - - ' no bloco). Os blocos sao juntados por ``---``.

    A data de publicacao ajuda o LLM a preferir a versao mais recente quando
    ha conflitos entre versoes de uma mesma NT.

    Ordenacao: respeita a ordem recebida (chamador ja ranqueou por score).
    """
    if not ranked:
        return ""
    blocks: list[str] = []
    for c in ranked:
        date_segment = _format_published_at(c.published_at)
        if date_segment:
            header = f"[Fonte: {c.doc_title} -{date_segment} - {c.source_url}]"
        else:
            header = f"[Fonte: {c.doc_title} - {c.source_url}]"
        blocks.append(f"{header}\n{c.text}\n")
    return _BLOCK_SEP.join(blocks)


def has_sufficient_evidence(
    ranked: list[ScoredChunk],
    min_score: float = MIN_RELEVANCE_SCORE,
) -> bool:
    """Guardrail de veracidade: retorna ``True`` apenas se ha pelo menos 1 chunk
    com ``score >= min_score``.

    Convencao: olhamos apenas o PRIMEIRO chunk (mais relevante no ranking).
    Se ele nao atinge o minimo, qualquer outro posterior tera score menor, entao
    a checagem e correta sem percorrer a lista inteira.
    """
    return len(ranked) > 0 and ranked[0].score >= min_score


__all__ = [
    "NO_EVIDENCE_MESSAGE",
    "build_context",
    "has_sufficient_evidence",
]
