"""Excecoes customizadas do subsistema de parser/extrator.

Concentra erros especificos do dominio para que camadas superiores (indexer,
CLI) possam capturar de forma granular sem depender de tipos de excecao de
bibliotecas externas (pypdf, beautifulsoup4).
"""
from __future__ import annotations


class PdfParseError(Exception):
    """Levantada quando pypdf nao consegue ler ou interpretar um PDF.

    Encapsula tanto `pypdf.errors.PdfReadError` (estrutura invalida, EOF
    inesperado, header corrompido) quanto `OSError` (arquivo inexistente,
    inacessivel). Use-a como ponto unico de captura nas camadas acima da
    biblioteca de parsing.
    """
