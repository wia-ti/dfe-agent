"""Testes para src.parser.pdf_parser.

Cobre (PLAN.md linhas 129-131 - Task 4.1):
    - [x] extract_text_from_pdf preserva a string alvo e os acentos da fixture.
    - [x] extract_text_from_bytes(b"%PDF-corrompido") levanta PdfParseError.
    - [x] Saida de extract_text_from_pdf nao contem nenhum caractere '\\x00'.
    - [x] Normalizacao de 3+ '\\n' consecutivos em '\\n\\n' e strip final.
"""
from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pypdf.errors import PdfReadError

from src.parser.exceptions import PdfParseError
from src.parser.pdf_parser import extract_text_from_bytes, extract_text_from_pdf


# --- happy path: leitura da fixture real ---


def test_extract_text_from_pdf_returns_expected_substring(
    sample_pdf_path: Path,
) -> None:
    """A fixture contem 'Nota T\xe9cnica 2019.001 - NF-e'.

    O byte 0xE9 (Latin-1/WinAnsi) e a representacao canonica de 'e' sob o encoding
    da fixture, portanto o texto extraido por pypdf deve conter literalmente esses
    bytes - nao o caractere U+FFFD de substituicao Unicode.
    """
    result = extract_text_from_pdf(sample_pdf_path)

    assert isinstance(result, str)
    assert len(result) > 0
    assert "Nota T\xe9cnica 2019.001" in result
    assert "NF-e" in result
    # Nenhum byte de substituicao Unicode (U+FFFD).
    assert "\ufffd" not in result


def test_extract_text_from_pdf_strips_null_bytes(mocker) -> None:
    """Qualquer '\\x00' presente no texto extraido deve ser removido."""
    fake_page = MagicMock()
    fake_page.extract_text.return_value = "hello\x00world\x00more"
    fake_reader = MagicMock()
    fake_reader.pages = [fake_page]
    mocker.patch("src.parser.pdf_parser.PdfReader", return_value=fake_reader)

    result = extract_text_from_pdf(Path("dummy.pdf"))

    assert "\x00" not in result
    assert result == "helloworldmore"


def test_extract_text_from_pdf_normalizes_multiple_newlines(mocker) -> None:
    """Tres ou mais '\\n' consecutivos colapsam em no maximo '\\n\\n'."""
    fake_page = MagicMock()
    fake_page.extract_text.return_value = "linha1\n\n\n\nlinha2"
    fake_reader = MagicMock()
    fake_reader.pages = [fake_page]
    mocker.patch("src.parser.pdf_parser.PdfReader", return_value=fake_reader)

    result = extract_text_from_pdf(Path("dummy.pdf"))

    assert "\n\n\n" not in result
    assert result == "linha1\n\nlinha2"


def test_extract_text_from_pdf_strips_outer_whitespace(mocker) -> None:
    """A string retornada nao deve conter espacos/newlines nas extremidades."""
    fake_page = MagicMock()
    fake_page.extract_text.return_value = "   \n\nconteudo util\n\n   "
    fake_reader = MagicMock()
    fake_reader.pages = [fake_page]
    mocker.patch("src.parser.pdf_parser.PdfReader", return_value=fake_reader)

    result = extract_text_from_pdf(Path("dummy.pdf"))

    assert result == "conteudo util"


def test_extract_text_from_pdf_handles_page_extraction_failure(mocker) -> None:
    """Se uma pagina falhar ao extrair texto, as demais ainda sao processadas."""
    good_page = MagicMock()
    good_page.extract_text.return_value = "pagina OK"
    bad_page = MagicMock()
    bad_page.extract_text.side_effect = RuntimeError("falha esporadica")

    fake_reader = MagicMock()
    fake_reader.pages = [bad_page, good_page]
    mocker.patch("src.parser.pdf_parser.PdfReader", return_value=fake_reader)

    result = extract_text_from_pdf(Path("dummy.pdf"))

    assert "pagina OK" in result
    # A pagina que falhou contribuiu com string vazia, mas nao quebrou o loop.
    assert "falha esporadica" not in result


# --- error paths ---


def test_extract_text_from_bytes_with_corrupted_pdf_raises_pdf_parse_error() -> None:
    """Entrada claramente nao-PDF deve levantar PdfParseError."""
    with pytest.raises(PdfParseError):
        extract_text_from_bytes(b"%PDF-corrompido-12345")


def test_extract_text_from_bytes_with_empty_input_raises_pdf_parse_error() -> None:
    """Entrada vazia tambem deve levantar PdfParseError (PdfReadError)."""
    with pytest.raises(PdfParseError):
        extract_text_from_bytes(b"")


def test_extract_text_from_pdf_with_missing_file_raises_pdf_parse_error(
    tmp_path: Path,
) -> None:
    """Path inexistente deve ser tratado como PdfParseError (nao OSError cru)."""
    nonexistent = tmp_path / "nao_existe.pdf"
    with pytest.raises(PdfParseError):
        extract_text_from_pdf(nonexistent)


def test_extract_text_from_pdf_wraps_pdf_read_error(mocker) -> None:
    """PdfReadError levantado pelo PdfReader deve virar PdfParseError."""
    mocker.patch(
        "src.parser.pdf_parser.PdfReader",
        side_effect=PdfReadError("arquivo truncado"),
    )

    with pytest.raises(PdfParseError, match="arquivo truncado"):
        extract_text_from_pdf(Path("dummy.pdf"))


# --- extract_text_from_bytes happy path (via a fixture pequena) ---


def test_extract_text_from_bytes_reads_fixture(
    sample_pdf_bytes: bytes,
) -> None:
    """Wrapper sobre BytesIO deve retornar o mesmo texto do que o reader de path."""
    result = extract_text_from_bytes(sample_pdf_bytes)

    assert "Nota T\xe9cnica 2019.001" in result
    assert "NF-e" in result
    assert "\x00" not in result


# --- guard: PdfParseError deve ser Exception (nao BaseException generica) ---


def test_pdf_parse_error_is_an_exception() -> None:
    """PdfParseError precisa ser capturavel via `except Exception`."""
    assert issubclass(PdfParseError, Exception)
    # Deve poder ser levantada e capturada como Exception.
    try:
        raise PdfParseError("boom")
    except Exception as exc:
        assert isinstance(exc, PdfParseError)
        assert str(exc) == "boom"
