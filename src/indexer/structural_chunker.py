"""Chunker estrutural ciente de secoes NT (Sprint 2, Fase 10.1).

Diferencas em relacao a :mod:`src.indexer.chunker` (chunker plano):

    1. Detecta cabecalhos hierarquicos no formato NT (``1``, ``1.1``,
       ``1.1.1``) antes de quebrar o texto.
    2. Cada sub-chunk recebe ``section_path`` (``"1.1 OBJETIVO"``) e
       ``section_level`` (1, 2 ou 3) preservados mesmo apos subdivisao.
    3. Prefixa o texto de cada chunk com ``"§ {section_path}: "`` quando
       o caminho nao e vazio, dando ao embedder contexto explicito da
       secao.
    4. Quando o texto nao tem numeracao hierarquica reconhecivel,
       comporta-se como o chunker plano (todos os chunks com
       ``section_path=""`` e sem prefixo ``§ ...``).

Algoritmo (alto nivel):

    1. Validacao de parametros (mesmo contrato do chunker plano).
    2. Texto vazio / whitespace-only -> ``[]``.
    3. :func:`detect_sections` quebra o texto em regioes rotuladas.
    4. Para cada regiao, executa :func:`chunk_text` (chunker plano) para
       subdividir o corpo da secao respeitando ``chunk_size``.
    5. Cada sub-chunk gerado recebe o ``(section_path, section_level)``
       correspondente. Se o caminho nao for vazio, prepende ``"§ {path}: "``.
    6. Concatena todos os sub-chunks e devolve a lista final.

Observacao: delega a subdivisao a :func:`src.indexer.chunker.chunk_text`
para reaproveitar a logica de overlap entre chunks consecutivos e os
testes ja existentes daquele modulo (TDD sem duplicacao).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from src.indexer.chunker import chunk_text


# ---------------------------------------------------------------------------
# Tipos publicos
# ---------------------------------------------------------------------------


@dataclass
class StructuredChunk:
    """Resultado de :func:`chunk_structural`.

    Attributes:
        text: Texto do sub-chunk (com prefixo ``§ X: `` quando ha secao).
        section_path: Caminho da secao (ex: ``"1.1 OBJETIVO"``) ou ``""``
            quando o texto nao tem numeracao reconhecivel.
        section_level: Profundidade da secao (1, 2 ou 3); 0 quando vazio.
    """

    text: str
    section_path: str
    section_level: int


# ---------------------------------------------------------------------------
# Detector de secoes
# ---------------------------------------------------------------------------


# Cabecalho NT: ``1``, ``1.1`` ou ``1.1.1`` + espacos + titulo que comeca
# com letra maiuscula (acento-tolerant). Limita o titulo a 80 chars.
_SECTION_HEADER_RE: re.Pattern[str] = re.compile(
    r"^(?P<num>\d{1,2}(?:\.\d{1,2}){0,2})[\s\t]+(?P<title>[A-ZÁÉÍÓÚÂÊÔÃÕÇ][^\n]{2,80})$"
)


@dataclass
class _Section:
    section_path: str
    section_level: int
    body: str
    start_offset: int  # offset do cabecalho no texto original


def detect_sections(text: str) -> list[_Section]:
    """Detecta cabecalhos hierarquicos NT no texto.

    Args:
        text: Texto completo (PDF/HTML ja normalizado).

    Returns:
        Lista de :class:`_Section` ordenada por ``start_offset``. Cada
        item cobre do inicio do proprio cabecalho ate o inicio do
        proximo (ou ate o final do texto, no caso do ultimo).

    Comportamento:
        - Linhas que nao casam com ``_SECTION_HEADER_RE`` sao consideradas
          corpo da secao anterior (ou do preambulo, quando ainda nao
          houve cabecalho).
        - Se nenhuma cabecalho for detectado, retorna um unico
          :class:`_Section` com ``section_path=""`` cobrindo o texto
          inteiro.
    """
    if not text or not text.strip():
        return []

    lines: list[str] = text.split("\n")
    headers: list[tuple[int, str, int]] = []  # (line_idx, section_path, level)

    for idx, line in enumerate(lines):
        stripped: str = line.strip()
        match = _SECTION_HEADER_RE.match(stripped)
        if not match:
            continue
        num: str = match.group("num")
        title: str = match.group("title").strip()
        level: int = num.count(".") + 1
        path: str = f"{num} {title}"
        headers.append((idx, path, level))

    if not headers:
        return [
            _Section(section_path="", section_level=0, body=text, start_offset=0)
        ]

    sections: list[_Section] = []
    # Preambulo antes do primeiro cabecalho.
    pre_lines: list[str] = lines[: headers[0][0]]
    preamble: str = "\n".join(pre_lines).strip()
    if preamble:
        sections.append(
            _Section(
                section_path="",
                section_level=0,
                body=preamble,
                start_offset=0,
            )
        )

    for i, (line_idx, path, level) in enumerate(headers):
        next_line: int = (
            headers[i + 1][0] if i + 1 < len(headers) else len(lines)
        )
        body_lines: list[str] = lines[line_idx + 1 : next_line]
        body: str = "\n".join(body_lines).strip()
        sections.append(
            _Section(
                section_path=path,
                section_level=level,
                body=body,
                start_offset=line_idx,
            )
        )

    return sections


# ---------------------------------------------------------------------------
# Chunker estrutural
# ---------------------------------------------------------------------------


def chunk_structural(
    text: str,
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> list[StructuredChunk]:
    """Divide ``text`` em chunks preservando contexto de secao NT.

    Args:
        text: Texto de entrada (com ou sem numeracao hierarquica).
        chunk_size: Tamanho maximo por chunk em caracteres. Deve ser ``> 0``.
        chunk_overlap: Quantos caracteres do final do chunk N devem aparecer
            como inicio do chunk N+1. Deve ser ``>= 0`` e ``< chunk_size``.

    Returns:
        Lista de :class:`StructuredChunk` ordenada. Pode ser vazia para
        texto vazio.

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

    sections: list[_Section] = detect_sections(text)
    out: list[StructuredChunk] = []

    for sec in sections:
        if not sec.body:
            continue
        flat_chunks: list[str] = chunk_text(
            sec.body, chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )
        prefix: str = (
            f"§ {sec.section_path}: " if sec.section_path else ""
        )
        for piece in flat_chunks:
            new_text: str = f"{prefix}{piece}" if prefix else piece
            out.append(
                StructuredChunk(
                    text=new_text,
                    section_path=sec.section_path,
                    section_level=sec.section_level,
                )
            )

    return out


__all__ = ["StructuredChunk", "chunk_structural", "detect_sections"]
