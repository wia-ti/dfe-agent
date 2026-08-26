"""Extrator de metadados estruturados a partir de texto (Sprint 2, Fase 9.2).

Heuristicas deterministicas em PT-BR para identificar, sem LLM:
    - Numero de NT (nota tecnica) no formato ``AAAA.NNN``.
    - Numero de Convenio ICMS no formato ``NNNN/AAAA``.
    - Versao explicita (``Versao X.Y`` ou ``Versão X.Y``).
    - Data de publicacao no formato ``DD/MM/AAAA`` (apenas no cabecalho).

Tolerante: nunca levanta excecao. Quando nenhum padrao bate, retorna
``DocumentMetadata`` com todos os campos ``None``.

Limitacao: a busca e restrita aos primeiros ``HEADER_MAX_CHARS`` caracteres
do texto (cabecalho/capa) para evitar matches espurios em meio do corpo
(ex: referencias a "NT 2099.999" dentro de exemplos).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

# Limite da regiao do cabecalho onde a busca e realizada. Documentos
# fiscais costumam colocar NT/convenio/data nos primeiros ~1 KB; usamos
# 2 KB para margem de seguranca.
HEADER_MAX_CHARS: int = 2048

# Regex compiladas no module-load (uma unica vez). Toleram variacoes
# comuns de acentuacao: ``tecnica``/``técnica``, ``convenio``/``convênio``,
# ``versao``/``versão``.
_NT_NUMBER_RE: re.Pattern[str] = re.compile(
    r"(?i)nota[\s\xa0]+t[ée]cn[íi]ca[\s\xa0]+(?P<nt>\d{4}\.\d{3})"
)
_CONV_NUMBER_RE: re.Pattern[str] = re.compile(
    r"(?i)conv[êe]nio[\s\xa0]+icms[\s\xa0]+(?P<conv>\d+/\d{4})"
)
_VERSION_RE: re.Pattern[str] = re.compile(
    r"(?i)vers[ãa]o[\s\xa0]+(?P<v>\d+(?:\.\d+){0,2})"
)
_DATE_RE: re.Pattern[str] = re.compile(r"(?P<day>\d{2})/(?P<month>\d{2})/(?P<year>\d{4})")


@dataclass
class DocumentMetadata:
    """Snapshot de metadados estruturados extraidos do texto.

    Todos os campos sao opcionais: ausencias ficam representadas como
    ``None`` em vez de levantarem excecao.
    """

    nt_number: str | None = None
    conv_number: str | None = None
    published_at: datetime | None = None
    version: str | None = None
    language: str | None = None


def _safe_date(day: str, month: str, year: str) -> datetime | None:
    """Constroi ``datetime`` a partir de strings ``DD/MM/AAAA`` se validas.

    Retorna ``None`` quando o dia/mes e invalido (ex: ``32/13``).
    """
    try:
        return datetime(int(year), int(month), int(day))
    except ValueError:
        return None


def extract_document_metadata(
    text: str,
    doc_type: str | None = None,
) -> DocumentMetadata:
    """Extrai metadados estruturados do cabecalho de um documento.

    Args:
        text: Conteudo textual integral do documento (PDF/HTML normalizado).
        doc_type: Tipo do documento (``"nota_tecnica"``, ``"convenio"`` etc.)
            para orientar heuristicas adicionais no futuro. Hoje e apenas
            preservado; o extrator funciona sem essa informacao.

    Returns:
        ``DocumentMetadata`` preenchido com os campos identificados
        via regex. Campos nao encontrados ficam como ``None``.

    Raises:
        Nenhuma. Texto vazio / invalido produz ``DocumentMetadata()``.
    """
    del doc_type  # reservado para heuristicas orientadas por tipo

    if not text or not text.strip():
        return DocumentMetadata()

    header: str = text[:HEADER_MAX_CHARS]
    meta: DocumentMetadata = DocumentMetadata()

    if (m := _NT_NUMBER_RE.search(header)) is not None:
        meta.nt_number = m.group("nt")
    elif (m := re.search(r"\b(\d{4}\.\d{3})\b", header)) is not None:
        # Fallback: ``AAAA.NNN`` solto (sem prefixo "nota tecnica").
        # Util quando o titulo vem sem o rotulo formal mas o numero
        # ainda esta no cabecalho.
        meta.nt_number = m.group(1)

    if (m := _CONV_NUMBER_RE.search(header)) is not None:
        meta.conv_number = m.group("conv")

    if (m := _VERSION_RE.search(header)) is not None:
        meta.version = m.group("v")

    if (m := _DATE_RE.search(header)) is not None:
        meta.published_at = _safe_date(
            m.group("day"), m.group("month"), m.group("year")
        )

    return meta


__all__ = ["HEADER_MAX_CHARS", "DocumentMetadata", "extract_document_metadata"]
