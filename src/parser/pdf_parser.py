"""Extrator de texto de PDFs usando pypdf.

Foco: preservar o encoding original (WinAnsi/Latin-1) sem corromper a acentuacao
e tolerar PDFs com paginas problematicas (uma pagina ruim nao aborta o lote).

Contrato:
    - `extract_text_from_pdf(Path) -> str`
    - `extract_text_from_bytes(bytes) -> str`

Ambas as funcoes levantam `PdfParseError` quando o conteudo nao e um PDF
viavel. O texto retornado e normalizado: quebras triplas colapsam para duplas
e o caractere NUL e removido - ambos padroes observados em PDFs gerados por
ferramentas semi-robustas (scanners, conversores online).
"""
from __future__ import annotations

import io
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from src.parser.exceptions import PdfParseError
from src.utils.logger import get_logger


_logger = get_logger(__name__)


def _normalize(raw: str) -> str:
    """Colapsa 3+ '\\n' em '\\n\\n', remove '\\x00' e faz strip nas extremidades."""
    while "\n\n\n" in raw:
        raw = raw.replace("\n\n\n", "\n\n")
    return raw.replace("\x00", "").strip()


def _read_pages(reader: PdfReader) -> list[str]:
    """Extrai texto pagina-a-pagina, retornando string vazia quando uma pagina falha."""
    pages_text: list[str] = []
    for page in reader.pages:
        try:
            pages_text.append(page.extract_text() or "")
        except Exception as exc:  # noqa: BLE001 - defensivo: pagina ruim nao aborta lote
            _logger.warning("pdf_parser pagina com falha: %s", exc)
            pages_text.append("")
    return pages_text


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extrai texto de todas as paginas de um PDF apontado por `pdf_path`.

    Args:
        pdf_path: Caminho do arquivo PDF no disco.

    Returns:
        Texto concatenado de todas as paginas, com quebras normalizadas.

    Raises:
        PdfParseError: Se o arquivo nao existir, estiver inacessivel ou for
            invalido como PDF (inclui `pypdf.errors.PdfReadError`).
    """
    try:
        reader = PdfReader(str(pdf_path))
    except PdfReadError as exc:
        raise PdfParseError(f"Falha ao abrir PDF {pdf_path}: {exc}") from exc
    except OSError as exc:
        raise PdfParseError(f"Arquivo inacessivel {pdf_path}: {exc}") from exc

    pages_text = _read_pages(reader)
    return _normalize("\n".join(pages_text))


def extract_text_from_bytes(data: bytes) -> str:
    """Wrapper sobre `PdfReader` aplicado a um buffer em memoria.

    Args:
        data: Conteudo bruto de um PDF.

    Returns:
        Texto concatenado de todas as paginas, com quebras normalizadas.

    Raises:
        PdfParseError: Se os bytes nao constituirem um PDF viavel.
    """
    try:
        reader = PdfReader(io.BytesIO(data))
    except PdfReadError as exc:
        raise PdfParseError(f"Falha ao ler PDF de bytes: {exc}") from exc

    pages_text = _read_pages(reader)
    return _normalize("\n".join(pages_text))
