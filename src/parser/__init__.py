"""Parser/Extrator: converte PDFs e HTML em texto limpo."""
from __future__ import annotations

import sys
from pathlib import Path

# Adiciona `.opencode/` ao sys.path para que `from hooks.allowed_domains import
# ALLOWED_DOMAINS` funcione em qualquer modulo deste pacote. `.opencode/hooks/`
# ja tem `__init__.py` (criado na Task 3.1), entao trata-se como pacote Python
# valido a partir do momento que `.opencode/` esta no sys.path.
_PARSER_ROOT_PARENT = Path(__file__).resolve().parents[2]
_OPENCODE_DIR = _PARSER_ROOT_PARENT / ".opencode"
if str(_OPENCODE_DIR) not in sys.path:
    sys.path.insert(0, str(_OPENCODE_DIR))

# Re-exports publicos. Usa try/except para conviver com o paralelismo da
# Task 4.1: se `pdf_parser.py` ainda nao foi escrito pelo sub-agent paralelo,
# `extract_text_from_pdf` fica None ao inves de quebrar a importacao deste
# modulo. Quando ambos os arquivos existirem, o nome estara normalmente
# disponivel em `from src.parser import extract_text_from_pdf`.
try:
    from src.parser.pdf_parser import extract_text_from_pdf
except ImportError:
    extract_text_from_pdf = None  # type: ignore[assignment]

from src.parser.html_parser import extract_links, extract_text_from_html
from src.parser.metadata_extractor import (
    DocumentMetadata,
    extract_document_metadata,
)

__all__ = [
    "DocumentMetadata",
    "extract_document_metadata",
    "extract_links",
    "extract_text_from_html",
    "extract_text_from_pdf",
]
