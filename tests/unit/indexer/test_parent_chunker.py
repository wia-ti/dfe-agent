"""Testes para ``src.indexer.parent_chunker`` (Sprint 2, Fase 14.1)."""
from __future__ import annotations

from src.indexer.parent_chunker import chunk_with_parents


def test_paragrafo_longo_gera_parent_e_detalhes() -> None:
    text = (
        "A NT 2024.001 altera regras de cancelamento da NF-e. "
        "Empresas devem se adequar em 90 dias. "
        + ("Detalhes operacionais adicionais sobre prazos e "
           "procedimentos podem ser encontrados na secao 3. ") * 40
    )
    parents, details = chunk_with_parents(text, chunk_size=200, chunk_overlap=30)

    assert len(parents) == 1
    assert parents[0].kind == "parent"
    assert len(details) >= 2
    for d in details:
        assert d.parent_chunk_id == parents[0].chunk_index


def test_paragrafo_curto_vira_detail_sem_parent() -> None:
    text = "Frase unica sem dupla sentenca."
    parents, details = chunk_with_parents(text)
    assert len(parents) == 0
    assert len(details) == 1
    assert details[0].parent_chunk_id is None


def test_multiplos_paragrafos_longos_cada_um_com_seu_parent() -> None:
    text = (
        "Primeiro paragrafo. Com duas sentences aqui.\n\n"
        "Segundo paragrafo tambem. Com duas sentences igualmente.\n\n"
        "Terceiro paragrafo. E mais duas sentences.\n"
    )
    parents, details = chunk_with_parents(text, chunk_size=300, chunk_overlap=30)
    assert len(parents) == 3
    parent_ids = {p.chunk_index for p in parents}
    detail_parent_ids = {d.parent_chunk_id for d in details}
    assert detail_parent_ids.issubset(parent_ids)
    assert detail_parent_ids == parent_ids  # cada detail aponta para seu parent


def test_texto_vazio() -> None:
    assert chunk_with_parents("") == ([], [])
    assert chunk_with_parents("   \n\n  ") == ([], [])
