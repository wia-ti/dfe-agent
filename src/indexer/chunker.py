"""Chunker por paragrafos com subdivisao por sentencas e overlap configuravel.

Divide texto em chunks de tamanho maximo ``chunk_size`` (caracteres) preservando
paragrafos (``\\n\\n``) e sentencas (``'. '``, ``'! '``, ``'? '``, ``'\\n'``) sempre
que possivel. Garante overlap de ``chunk_overlap`` caracteres entre chunks
consecutivos para nao perder contexto nas fronteiras.

Algoritmo (alto nivel):
    1. Validacao de parametros (chunk_size > 0, 0 <= overlap < chunk_size).
    2. Texto vazio / whitespace-only -> ``[]``.
    3. Split por paragrafos (``\\n\\n``); descarta vazios.
    4. Para cada paragrafo > ``chunk_size``:
       a. Subdivide por sentencas (``'. '``, ``'! '``, ``'? '``, ``'\\n'``).
       b. Agrupa sentencas ate ``chunk_size``.
       c. Sentenca > ``chunk_size`` -> slicing direto com overlap (fallback).
    5. Concatena unidades ate atingir ``chunk_size``; ao fechar um chunk,
       inicia o proximo com ate ``chunk_overlap`` chars do final do anterior
       (cortando no proximo espaco quando existir; truncado para garantir
       que ``len(tail) + 2 + len(unit) <= chunk_size``).
"""
from __future__ import annotations

from typing import Final

# Separadores de sentenca. A ordem nao importa - o algoritmo itera e quebra
# progressivamente, preservando o separador na peca anterior.
_SENTENCE_SEPARATORS: Final[tuple[str, ...]] = (". ", "! ", "? ", "\n")


def _split_preserve_separator(text: str, sep: str) -> list[str]:
    """Divide ``text`` por ``sep`` mantendo o separador na peca anterior.

    Args:
        text: String a dividir.
        sep: Separador a procurar (ex: ``". "``).

    Returns:
        Lista de partes; se ``sep`` nao ocorre, retorna ``[text]``. A ultima
        peca NAO recebe ``sep`` (preserva o final do texto original).
    """
    if sep not in text:
        return [text]
    parts: list[str] = text.split(sep)
    pieces: list[str] = []
    for i, part in enumerate(parts):
        if i < len(parts) - 1:
            pieces.append(part + sep)
        else:
            # Ultima peca: NAO anexa sep (preserva final do texto original).
            # Como text ja foi validado para nao terminar com sep (chamada
            # via _split_by_sentences comecando de texto ja strip-ado),
            # part sempre e nao-vazia aqui.
            pieces.append(part)
    return pieces


def _split_by_sentences(text: str) -> list[str]:
    """Divide ``text`` pelos separadores de sentenca, preservando cada um.

    Args:
        text: Texto a subdividir.

    Returns:
        Lista de sentencas nao-vazias. Se nenhum separador ocorre, retorna
        ``[text]``.
    """
    pieces: list[str] = [text]
    for sep in _SENTENCE_SEPARATORS:
        new_pieces: list[str] = []
        for piece in pieces:
            new_pieces.extend(_split_preserve_separator(piece, sep))
        pieces = new_pieces
    # Filtra strings vazias (caso degenerado: texto == "\n" gera "\n" sozinho,
    # que pode ser whitespace-only; mantemos aqui para tratamento no caller).
    return [p for p in pieces if p]


def _chunk_unit_by_size(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Quebra ``text`` em fatias de ate ``chunk_size`` chars com overlap.

    Usado como fallback quando uma sentenca excede ``chunk_size`` (texto sem
    separadores uteis). Assume ``len(text) > chunk_size``.

    Args:
        text: Texto a quebrar (deve ser ``> chunk_size``).
        chunk_size: Tamanho maximo de cada fatia.
        chunk_overlap: Sobreposicao entre fatias consecutivas.

    Returns:
        Lista de fatias. A ultima pode ser menor que ``chunk_size``. Fatias
        2..N compartilham os primeiros ``chunk_overlap`` chars com o final da
        fatia anterior.
    """
    chunks: list[str] = []
    start: int = 0
    n: int = len(text)
    while True:
        end: int = min(start + chunk_size, n)
        chunks.append(text[start:end])
        if end >= n:
            break
        start = end - chunk_overlap
    return chunks


def _split_long_paragraph(paragraph: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Subdivide um paragrafo > ``chunk_size`` em unidades <= ``chunk_size``.

    Estrategia:
        1. Quebra por sentencas.
        2. Agrupa sentencas ate ``chunk_size``.
        3. Sentenca isolada > ``chunk_size`` -> slicing direto com overlap.

    Args:
        paragraph: Paragrafo a subdividir (garantido ``> chunk_size``).
        chunk_size: Tamanho maximo por unidade.
        chunk_overlap: Overlap para slicing de sentencas longas.

    Returns:
        Lista de unidades (cada uma ``<= chunk_size``).
    """
    sentences: list[str] = _split_by_sentences(paragraph)
    units: list[str] = []
    current: list[str] = []
    for sentence in sentences:
        stripped: str = sentence.strip()
        if not stripped:
            # Sentenca whitespace-only (ex: "\n" sozinha): descarta.
            continue
        if len(sentence) > chunk_size:
            # Sentenca gigantesca: slicing direto. Antes, fecha grupo atual.
            if current:
                units.append(" ".join(current).strip())
                current = []
            units.extend(_chunk_unit_by_size(sentence, chunk_size, chunk_overlap))
            continue
        # Tenta agrupar sentenca no grupo atual.
        candidate: str = " ".join(current + [sentence]).strip()
        if len(candidate) <= chunk_size:
            current.append(sentence)
        else:
            # Estoura: fecha grupo atual e inicia novo.
            units.append(" ".join(current).strip())
            current = [sentence]
    if current:
        units.append(" ".join(current).strip())
    return [u for u in units if u.strip()]


def _expand_to_units(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Quebra ``text`` em unidades (cada uma ``<= chunk_size``).

    Etapas:
        1. Split por paragrafos (``\\n\\n``); descarta vazios.
        2. Para cada paragrafo > ``chunk_size``, subdivide via sentencas /
           slicing.

    Args:
        text: Texto original (nao-vazio, nao-whitespace).
        chunk_size: Limite de tamanho por unidade.
        chunk_overlap: Overlap para slicing de sentencas muito longas.

    Returns:
        Lista de unidades (strings nao-vazias, cada uma ``<= chunk_size``).
    """
    paragraphs: list[str] = [p.strip() for p in text.split("\n\n") if p.strip()]
    units: list[str] = []
    for para in paragraphs:
        if len(para) <= chunk_size:
            units.append(para)
        else:
            units.extend(_split_long_paragraph(para, chunk_size, chunk_overlap))
    return units


def _start_chunk_with_overlap(
    prev_chunk: str,
    unit: str,
    chunk_size: int,
    chunk_overlap: int,
) -> str:
    """Inicia novo chunk concatenando tail de ``prev_chunk`` com ``unit``.

    O tail tem ate ``chunk_overlap`` caracteres, respeitando ``chunk_size``.
    Se a unidade sozinha ja consome (ou excede) ``chunk_size``, retorna apenas
    a unidade. Caso contrario, alinha o tail no inicio de uma palavra (corta
    no primeiro espaco) para evitar quebra mid-word.

    Args:
        prev_chunk: Chunk anterior (ja fechado).
        unit: Proxima unidade a incluir.
        chunk_size: Tamanho maximo do chunk.
        chunk_overlap: Overlap desejado.

    Returns:
        String representando o novo chunk inicial.
    """
    if chunk_overlap <= 0:
        return unit
    # Reserva espaco para o separador "\n\n" entre tail e unit.
    budget: int = chunk_size - len(unit) - 2
    if budget <= 0:
        # Unidade sozinha ja consome (ou excede) chunk_size; sem overlap.
        return unit
    effective_overlap: int = min(chunk_overlap, budget)
    tail: str = prev_chunk[-effective_overlap:]
    # Alinha no inicio de uma palavra para evitar quebra mid-word.
    space_idx: int = tail.find(" ")
    if space_idx != -1:
        tail = tail[space_idx + 1:]
    return (tail + "\n\n" + unit).strip()


def chunk_text(
    text: str,
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> list[str]:
    """Divide ``text`` em chunks de ate ``chunk_size`` caracteres com overlap.

    Algoritmo:
        1. Validacao de parametros.
        2. Texto vazio / whitespace-only -> ``[]``.
        3. Divide por paragrafos (separador ``\\n\\n``); descarta vazios.
        4. Para cada paragrafo > ``chunk_size``, subdivide por sentencas
           (fallback: slicing direto com overlap).
        5. Concatena unidades ate atingir ``chunk_size``; ao fechar um chunk,
           inicia o proximo com ate ``chunk_overlap`` chars do final do
           anterior (alinhado no inicio de uma palavra quando possivel).
        6. Remove qualquer chunk que seja apenas whitespace.

    Args:
        text: Texto de entrada (pode conter paragrafos e sentencas).
        chunk_size: Tamanho maximo por chunk em caracteres. Deve ser ``> 0``.
        chunk_overlap: Quantos caracteres do final do chunk N devem aparecer
            como inicio do chunk N+1. Deve ser ``>= 0`` e ``< chunk_size``.

    Returns:
        Lista de chunks (strings nao-vazias). Pode ser vazia.

    Raises:
        ValueError: Se ``chunk_size <= 0``, ``chunk_overlap < 0`` ou
            ``chunk_overlap >= chunk_size``.
    """
    if chunk_size <= 0:
        raise ValueError(f"chunk_size deve ser > 0, recebeu {chunk_size}")
    if chunk_overlap < 0:
        raise ValueError(f"chunk_overlap deve ser >= 0, recebeu {chunk_overlap}")
    if chunk_overlap >= chunk_size:
        raise ValueError(
            f"chunk_overlap ({chunk_overlap}) deve ser < chunk_size ({chunk_size})"
        )
    if not text or not text.strip():
        return []

    units: list[str] = _expand_to_units(text, chunk_size, chunk_overlap)

    chunks: list[str] = []
    current_chunk: str = ""

    for unit in units:
        if not current_chunk:
            current_chunk = unit
            continue

        # Tenta adicionar a unidade ao chunk atual.
        candidate: str = (current_chunk + "\n\n" + unit).strip()
        if len(candidate) <= chunk_size:
            current_chunk = candidate
            continue

        # Fecha o chunk atual.
        chunks.append(current_chunk)
        # Inicia novo chunk com overlap do anterior.
        current_chunk = _start_chunk_with_overlap(
            chunks[-1], unit, chunk_size, chunk_overlap
        )

    chunks.append(current_chunk)

    return [c for c in chunks if c.strip()]
