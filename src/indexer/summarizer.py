"""Sumarizacao deterministica de documentos (Sprint 2, Fase 12.1).

Objetivo:
    Produzir um sumario de ate ``max_chars`` caracteres que possa ser
    embedado para o primeiro estagio do ``search_hierarchical``. Sem
    chamada de LLM — algoritmo deterministico, rapido, sem dependencia
    externa.

Estrategia (alto nivel):
    1. Normalizar whitespace e dividir o texto em sentencas via
       separadores ``. ! ?`` e quebras de linha.
    2. Descartar sentencas com menos de ``MIN_SENTENCE_CHARS``
       caracteres (filtra headers, codigos curtos etc.).
    3. Selecionar no maximo ``MAX_SENTENCES`` (3) sentencas seguindo
       duas prioridades:
        a. Sempre incluir a primeira sentenca substantiva (header
           info / objetivo).
        b. Incluir as subsequentes mais longas ate completar o espaco.
    4. Truncar em espaco (nunca mid-word).

Vantagens:
    - ~O(n) onde n=len(text).
    - Determinista: mesmo input produz mesmo output.
    - Sem dependencia de modelo / rede.
    - Tolerante a encoding irregular (lida com WinAnsi/Latin-1 do pypdf).
"""
from __future__ import annotations

import re

MIN_SENTENCE_CHARS: int = 30
MAX_SENTENCES: int = 3
DEFAULT_MAX_CHARS: int = 400

# Separadores de sentenca. A ordem NAO importa — usamos regex alternation.
_SENTENCE_SEPARATORS: re.Pattern[str] = re.compile(r"(?<=[.!?\n])\s+")


def _split_sentences(text: str) -> list[str]:
    """Divide ``text`` em sentencas (heuristica via pontuacao e quebras)."""
    # Normaliza multiplas quebras de linha em sentenca unica.
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    return _SENTENCE_SEPARATORS.split(text)


def _truncate_at_word_boundary(text: str, max_chars: int) -> str:
    """Trunca ``text`` em ate ``max_chars`` caracteres, no ultimo espaco.

    Garante que a saida NAO termina mid-word. Se nao houver espaco ate
    o limite, devolve o prefixo bruto.
    """
    if len(text) <= max_chars:
        return text
    truncated: str = text[:max_chars]
    last_space: int = truncated.rfind(" ")
    if last_space <= 0:
        return truncated
    return truncated[:last_space].strip()


def summarize(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Extrai um sumario deterministico de ``text``.

    Algoritmo:
        1. Divide em sentencas; descarta as muito curtas.
        2. Sempre inclui a primeira sentenca substantiva.
        3. Adiciona as proximas mais longas (por ``len``) ate
           ``max_chars`` ou ate ``MAX_SENTENCES`` (3).

    Args:
        text: Texto integral do documento (PDF/HTML ja normalizado).
        max_chars: Tamanho maximo do sumario. Deve ser positivo.
            Default 400 chars (cabe em modelo de embedding sem
            truncamento agressivo).

    Returns:
        String com o sumario. Vazia quando o texto nao produz
        sentencas substantivas. Nunca levanta.

    Raises:
        ValueError: Se ``max_chars <= 0``.
    """
    if max_chars <= 0:
        raise ValueError(f"max_chars deve ser > 0, recebeu {max_chars}")
    if not text or not text.strip():
        return ""

    raw_sentences: list[str] = _split_sentences(text)
    candidates: list[str] = [
        s.strip() for s in raw_sentences if len(s.strip()) >= MIN_SENTENCE_CHARS
    ]
    if not candidates:
        return ""

    # Caso degenerado: 1 unica sentenca; trunca sem cortar mid-word.
    if len(candidates) == 1:
        return _truncate_at_word_boundary(candidates[0], max_chars)

    selected: list[str] = [candidates[0]]
    remaining: int = max_chars - len(candidates[0])
    for sentence in sorted(candidates[1:], key=len, reverse=True):
        if len(selected) >= MAX_SENTENCES:
            break
        # Reserva 1 char para o separador " ".
        cost: int = len(sentence) + (1 if selected else 0)
        if cost > remaining:
            # Tenta incluir parcial se ainda ha espaco razoavel.
            if remaining > MIN_SENTENCE_CHARS:
                partial: str = _truncate_at_word_boundary(
                    sentence, remaining - 1
                )
                if partial:
                    selected.append(partial)
            break
        selected.append(sentence)
        remaining -= cost

    return " ".join(selected).strip()


__all__ = [
    "DEFAULT_MAX_CHARS",
    "MAX_SENTENCES",
    "MIN_SENTENCE_CHARS",
    "summarize",
]
