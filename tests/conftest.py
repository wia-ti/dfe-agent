"""Conftest raiz: env vars anti-OpenBLAS + fixtures compartilhadas.

Forcado ANTES de qualquer import que carregue OpenBLAS para mitigar
"Memory allocation still failed" em subprocessos Windows.
"""
from __future__ import annotations

import os

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
SRC_PATH: Path = PROJECT_ROOT / "src"
HOOKS_PKG_PARENT: Path = PROJECT_ROOT / ".opencode"

from src.utils.syspath_bootstrap import ensure_sys_path

ensure_sys_path()


@pytest.fixture(autouse=True)
def _ensure_hooks_on_path() -> None:
    """Garante que ``.opencode/`` esteja em ``sys.path`` durante toda a suite.

    Necessario para que ``src.collector.{downloader,portal_index}`` consiga
    importar ``hooks.domain_guard`` sem precisar de stub fail-open.
    Tests que NEGAM explicitamente o guardrail (ex.: fail-closed) devem
    limpar sys.modules/sys.path manualmente; este fixture delega ao helper
    canonico compartilhado em ``src.utils.syspath_bootstrap``.
    """
    ensure_sys_path()


# ---------------------------------------------------------------------------
# Fixture PDF (Task 4.1)
#
# pypdf e somente leitor e o projeto nao tem dependencia de writer PDF
# (reportlab/fpdf2 nao estao em requirements.txt). Para gerar o fixture
# `tests/fixtures/sample_nt.pdf` e construir um PDF minimo valido via bytes
# puros, usando Helvetica + WinAnsiEncoding (Latin-1 compat) - encoding no qual
# 'e' (0xE9) esta entre os glifos baseline do Type1, e portanto e recuperado de
# volta pelo pypdf sem substituicao Unicode.
# ---------------------------------------------------------------------------


def _build_sample_pdf_bytes(text: str = "Nota T\xe9cnica 2019.001 - NF-e") -> bytes:
    """Constroi um PDF minimo valido com um unico texto em Helvetica.

    Args:
        text: String a ser desenhada na pagina. Caracteres devem cair dentro do
            encoding WinAnsi (Latin-1) - e (0xE9), a (0xE1), o (0xF3), c (0xE7)
            etc. sao suportados; caracteres fora do encoding podem virar U+FFFD.

    Returns:
        Bytes de um PDF completo, com uma unica pagina 612x792 (Letter), fonte
        Helvetica + WinAnsiEncoding, e o `text` desenhado em (50, 750) a 14pt.
    """
    content = f"BT /F1 14 Tf 50 750 Td ({text}) Tj ET".encode("latin-1")
    obj_bodies: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        (
            b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n"
            + content + b"\nendstream"
        ),
        (
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
            b"/Encoding /WinAnsiEncoding >>"
        ),
    ]
    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []
    for i, body in enumerate(obj_bodies, start=1):
        offsets.append(len(pdf))
        pdf += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_offset = len(pdf)
    pdf += f"xref\n0 {len(obj_bodies) + 1}\n".encode()
    pdf += b"0000000000 65535 f \n"
    for off in offsets:
        pdf += f"{off:010d} 00000 n \n".encode()
    pdf += (
        f"trailer\n<< /Size {len(obj_bodies) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode()
    return bytes(pdf)


@pytest.fixture(scope="session")
def sample_pdf_bytes() -> bytes:
    """Conteudo bruto do PDF fixture - util para testes via BytesIO."""
    return _build_sample_pdf_bytes()


@pytest.fixture(scope="session")
def sample_pdf_path() -> Path:
    """Path para o PDF fixture; gera e cacheia em tests/fixtures/.

    O arquivo e materializado uma unica vez por sessao de testes; se ja existir
    no disco (commitado), e reusado como cache para nao regerar a cada run.
    """
    fixture_dir: Path = Path(__file__).parent / "fixtures"
    fixture_dir.mkdir(exist_ok=True)
    pdf_path: Path = fixture_dir / "sample_nt.pdf"
    if not pdf_path.exists():
        pdf_path.write_bytes(_build_sample_pdf_bytes())
    return pdf_path