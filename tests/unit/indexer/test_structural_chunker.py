"""Testes unitarios para ``src.indexer.structural_chunker`` (Sprint 2, Fase 10.1).

Cobre (PLAN_SPRINT2.md - Task 10.1):
    - Detector de secao: regex ``^\\d+(\\.\\d+){0,2}\\s+[A-Z]...`` reconhece
      cabecalhos NT.
    - Chunks preservam ``section_path`` mesmo quando o corpo da secao
      excede ``chunk_size`` (subdivisao balanceada).
    - Texto sem numeracao hierarquica: chunks com ``section_path=""``
      (fallback equivalente ao flat).
    - Tolerancia: tabs/espacos extras no cabecalho.
"""
from __future__ import annotations

import pytest

from src.indexer.structural_chunker import (
    StructuredChunk,
    chunk_structural,
    detect_sections,
)


# --- happy paths ----------------------------------------------------------


def test_detect_sections_reconhece_numeracao_decimal() -> None:
    text = (
        "1 OBJETIVO\n"
        "Texto da secao 1.\n"
        "\n"
        "1.1 Subsecao\n"
        "Texto da 1.1.\n"
        "\n"
        "2 FUNDAMENTACAO\n"
        "Texto da secao 2.\n"
    )
    sections = detect_sections(text)

    paths = [s.section_path for s in sections]
    assert "1 OBJETIVO" in paths
    assert "1.1 Subsecao" in paths
    assert "2 FUNDAMENTACAO" in paths

    levels = {s.section_path: s.section_level for s in sections}
    assert levels["1 OBJETIVO"] == 1
    assert levels["1.1 Subsecao"] == 2
    assert levels["2 FUNDAMENTACAO"] == 1


def test_detect_sections_suporta_tres_niveis() -> None:
    text = (
        "1 OBJ\n"
        "1.1 SUB\n"
        "1.1.1 ITEM\n"
        "1.1.2 ITEM2\n"
        "2 FUND\n"
    )
    sections = detect_sections(text)
    levels = {s.section_path: s.section_level for s in sections}

    assert levels["1 OBJ"] == 1
    assert levels["1.1 SUB"] == 2
    assert levels["1.1.1 ITEM"] == 3
    assert levels["1.1.2 ITEM2"] == 3
    assert levels["2 FUND"] == 1


def test_detect_sections_tolerancia_a_espacos_extras() -> None:
    """Tabs e espacos multiplos no cabecalho sao aceitos."""
    text = (
        "1   OBJETIVO\n"
        "1.1\tSub\n"
    )
    sections = detect_sections(text)
    paths = [s.section_path for s in sections]
    assert "1   OBJETIVO".replace("   ", " ") in paths or "1 OBJETIVO" in paths
    assert any("Sub" in p for p in paths)


# --- chunk_structural -----------------------------------------------------


def test_chunk_structural_atribui_section_path() -> None:
    text = (
        "1 OBJETIVO\n"
        "Esta NT visa alterar regras de cancelamento da NF-e.\n"
        "\n"
        "2 FUNDAMENTACAO\n"
        "Base legal: Lei XYZ.\n"
    )
    chunks = chunk_structural(text, chunk_size=400, chunk_overlap=50)

    assert len(chunks) == 2
    paths = [c.section_path for c in chunks]
    assert paths[0] == "1 OBJETIVO"
    assert paths[1] == "2 FUNDAMENTACAO"


def test_chunk_structural_preserva_section_path_em_secao_longa() -> None:
    """Subdivide uma secao grande mas mantem o mesmo ``section_path`` em
    todos os chunks resultantes (nao perde contexto).
    """
    body = ("detalhe importante sobre a regra. " * 80).strip()
    text = (
        "1 REGRA\n"
        f"{body}\n"
        "\n"
        "2 OUTRA\n"
        "conteudo curto.\n"
    )
    chunks = chunk_structural(text, chunk_size=400, chunk_overlap=50)

    section_1_chunks: list[StructuredChunk] = [
        c for c in chunks if c.section_path == "1 REGRA"
    ]
    assert len(section_1_chunks) >= 2, "secao longa deve subdividir"
    for c in section_1_chunks:
        assert c.section_level == 1


def test_chunk_structural_texto_sem_secoes_retorna_chunks_vazios_de_path() -> None:
    """Texto sem numeracao: comporta-se como chunker flat (path vazio)."""
    text = (
        "lorem ipsum dolor sit amet. " * 60
    )
    chunks = chunk_structural(text, chunk_size=200, chunk_overlap=20)

    assert len(chunks) >= 1
    assert all(c.section_path == "" for c in chunks)
    assert all(c.section_level == 0 for c in chunks)


def test_chunk_structural_prefixa_chunk_com_section_path() -> None:
    """Cada chunk textual recebe prefixo ``§ {section_path}: `` para que a
    representacao enviada ao embedder explicite o contexto.
    """
    text = (
        "1 OBJETIVO\n"
        "Conteudo claro sobre a regra nova introduzida pela NT 2024.001.\n"
    )
    chunks = chunk_structural(text, chunk_size=400, chunk_overlap=50)

    assert len(chunks) == 1
    assert chunks[0].text.startswith("§ 1 OBJETIVO:")
    assert "NT 2024.001" in chunks[0].text


def test_chunk_structural_path_vazio_nao_prefixa() -> None:
    """Quando ``section_path`` e vazio (modo flat implícito), NAO prepende prefixo."""
    text = "lorem ipsum " * 50
    chunks = chunk_structural(text, chunk_size=200, chunk_overlap=20)

    assert len(chunks) >= 1
    for c in chunks:
        assert not c.text.startswith("§")


def test_chunk_structural_texto_vazio_retorna_lista_vazia() -> None:
    assert chunk_structural("") == []
    assert chunk_structural("   \n\n  \t  ") == []


def test_chunk_structural_validacao_parametros() -> None:
    with pytest.raises(ValueError, match="chunk_size"):
        chunk_structural("texto", chunk_size=0)
    with pytest.raises(ValueError, match="chunk_overlap"):
        chunk_structural("texto", chunk_size=100, chunk_overlap=-1)
    with pytest.raises(ValueError, match="chunk_overlap"):
        chunk_structural("texto", chunk_size=100, chunk_overlap=100)
