"""Testes para src.parser.metadata_extractor (Sprint 2, Fase 9.2).

Cobre (PLAN_SPRINT2.md - Task 9.2):
    - [x] Texto ``"NOTA TECNICA 2019.001 — Assinada em 15/03/2019"`` extrai
          ``nt_number="2019.001"``, ``published_at=datetime(2019, 3, 15)``.
    - [x] Texto ``"CONVENIO ICMS 123/2024"`` extrai ``conv_number="123/2024"``.
    - [x] Texto ``"Versao 3.2 — NT 2020.001"`` extrai ``version="3.2"``
          e ``nt_number="2020.001"``.
    - [x] Texto sem cabeçalho retorna todos campos ``None`` (sem raise).
    - [x] Texto vazio / whitespace-only retorna todos campos ``None``.
    - [x] Data depois do cabeçalho (apos HEADER_MAX_CHARS) e ignorada.
"""
from __future__ import annotations

from datetime import datetime

from src.parser.metadata_extractor import DocumentMetadata, extract_document_metadata


# --- happy paths ----------------------------------------------------------


def test_extrai_nt_number_e_data_em_cabecalho() -> None:
    text = (
        "NOTA TÉCNICA 2019.001 — NF-e\n"
        "Assinada em 15/03/2019 em Brasilia.\n"
        "Sumario: ...\n"
    )
    meta = extract_document_metadata(text)

    assert meta.nt_number == "2019.001"
    assert meta.published_at == datetime(2019, 3, 15)
    assert meta.conv_number is None
    assert meta.version is None


def test_extrai_conv_number_em_cabecalho() -> None:
    text = "CONVÊNIO ICMS 123/2024 - Altera aliquotas"
    meta = extract_document_metadata(text)

    assert meta.conv_number == "123/2024"
    assert meta.nt_number is None


def test_extrai_versao_e_nt_number_em_cabecalho() -> None:
    text = (
        "MANUAL DE INTEGRACAO NF-e 4.00\n"
        "Versao 3.2 - Marco/2019\n"
        "Atualizacoes da NT 2020.001 estao refletidas aqui.\n"
    )
    meta = extract_document_metadata(text)

    assert meta.version == "3.2"
    assert meta.nt_number == "2020.001"


def test_reconhece_variacoes_de_acentuacao() -> None:
    """Heuristicas toleram ``tecnica``/``técnica``, ``versao``/``versão`` etc."""
    cases: list[tuple[str, dict[str, str]]] = [
        ("Nota tecnica 2019.001 - Assinada em 15/03/2019",
         {"nt_number": "2019.001", "year": "2019", "month": "03", "day": "15"}),
        ("Convenio ICMS 9/2020", {"conv_number": "9/2020"}),
        ("Versão 2.0", {"version": "2.0"}),
    ]
    for text, expected in cases:
        meta = extract_document_metadata(text)
        for field_name, expected_value in expected.items():
            if field_name in {"nt_number", "conv_number", "version"}:
                actual = getattr(meta, field_name)
                assert actual == expected_value, (
                    f"{field_name!r}: esperado {expected_value!r}, recebi {actual!r} "
                    f"em {text!r}"
                )
            elif field_name == "year":
                assert meta.published_at is not None
                assert str(meta.published_at.year) == expected_value


# --- bordas / ausencia de metadados ---------------------------------------


def test_texto_sem_padroes_retorna_metadata_vazio() -> None:
    text = "Lorem ipsum dolor sit amet. Sem NT, sem convenio, sem data."
    meta = extract_document_metadata(text)

    assert meta.nt_number is None
    assert meta.conv_number is None
    assert meta.published_at is None
    assert meta.version is None


def test_texto_vazio_retorna_metadata_vazio() -> None:
    assert extract_document_metadata("") == DocumentMetadata()
    assert extract_document_metadata("   \n\n  \t  ") == DocumentMetadata()


def test_data_invalida_e_descartada() -> None:
    """``32/13/2019`` (mes > 12) e ignorada — nao levanta."""
    text = "Nota tecnica 2019.001 - Data inscrita em 32/13/2019."
    meta = extract_document_metadata(text)

    assert meta.nt_number == "2019.001"
    assert meta.published_at is None


# --- restricao por regiao do cabecalho ------------------------------------


def test_data_apos_header_max_chars_e_ignorada() -> None:
    """Data fora do cabecalho (primeiros ~2 KB) nao e capturada como
    ``published_at``.
    """
    padding = "linha qualquer sem nt_number e sem data valida no cabecalho.\n" * 80
    text = padding + "Data bem distante do inicio: 01/01/2099.\n"

    meta = extract_document_metadata(text)
    assert meta.published_at is None
    assert meta.nt_number is None


def test_nt_number_completa_no_header_retorna_apenas_uma() -> None:
    """Quando ha NT no header e outra referencia no corpo, mantem a do header."""
    text = (
        "Cabecalho: NOTA TÉCNICA 2019.001\n"
        + ("texto qualquer sem nt valido. " * 200)
        + "\nReferencia no corpo: cite a NT 2099.999 para detalhes.\n"
    )
    meta = extract_document_metadata(text)
    assert meta.nt_number == "2019.001"
