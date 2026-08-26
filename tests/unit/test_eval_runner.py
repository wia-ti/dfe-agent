"""Testes unitarios para ``src.eval.runner`` (Sprint 2, Fase 16).

Cobre:
    - ``load_eval_set`` parseia JSON e mapeia para ``EvalSample``.
    - ``evaluate_question`` calcula ``recall_at_5``, ``MRR`` e
      ``citation_rate`` corretamente.
    - Doc nao encontrado -> todas as metricas 0.
    - Doc encontrado em rank > 5 -> recall 0, MRR = 1/rank, citation = 1.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.eval.runner import (
    EvalSample,
    evaluate_question,
    load_eval_set,
)


def test_load_eval_set(tmp_path: Path) -> None:
    payload: list[dict] = [
        {"question": "Q1", "expected_doc_url": "u1", "expected_keywords": ["k1"]},
        {"question": "Q2", "expected_doc_url": "u2"},
    ]
    path = tmp_path / "eval.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = load_eval_set(path)
    assert len(loaded) == 2
    assert loaded[0].question == "Q1"
    assert loaded[0].expected_doc_url == "u1"
    assert loaded[0].expected_keywords == ["k1"]
    assert loaded[1].expected_keywords == []


def test_evaluate_question_doc_em_rank_1() -> None:
    sources = [
        {
            "url": "https://www.nfe.fazenda.gov.br/portal/x?token=abc",
            "title": "T",
            "score": 0.9,
        },
        {
            "url": "https://www.cte.fazenda.gov.br/y",
            "title": "T2",
            "score": 0.7,
        },
    ]

    result = evaluate_question(
        question="q",
        expected_doc_url="https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx",
        expected_keywords=["portal"],
        sources=sources,
        rank_for=lambda url: 1,
    )
    assert result.rank == 1
    assert result.recall_at_5 == 1.0
    assert result.mrr == 1.0
    assert result.cited_in_answer == 1.0


def test_evaluate_question_doc_em_rank_3_recall_1_mrr_1_terco() -> None:
    """Doc correto em rank 3 com fontes de outros dominios nos ranks 1 e 2.

    Sob a politica D.3 (match por dominio), sources de outros dominios
    nao devem bater para o ``expected_doc_url`` da NF-e, deixando o doc
    correto em rank 3.
    """
    sources = [
        {"url": "https://www.cte.fazenda.gov.br/u1", "title": "t", "score": 0.9},
        {"url": "https://www.mdfe.fazenda.gov.br/u2", "title": "t", "score": 0.7},
        {
            "url": "https://www.nfe.fazenda.gov.br/correct",
            "title": "t",
            "score": 0.5,
        },
    ]
    result = evaluate_question(
        question="q",
        expected_doc_url="https://www.nfe.fazenda.gov.br/correct",
        expected_keywords=[],
        sources=sources,
        rank_for=lambda url: 99,
    )
    assert result.rank == 3
    assert result.recall_at_5 == 1.0
    assert abs(result.mrr - 1.0 / 3.0) < 1e-9
    assert result.cited_in_answer == 1.0


def test_evaluate_question_rank_acima_de_5() -> None:
    sources: list[dict] = []
    for i in range(8):
        if i == 7:
            url = "https://www.nfe.fazenda.gov.br/correct"
        else:
            url = f"https://www.cte.fazenda.gov.br/u{i}"
        sources.append({"url": url, "title": "t", "score": 0.5})
    result = evaluate_question(
        question="q",
        expected_doc_url="https://www.nfe.fazenda.gov.br/correct",
        expected_keywords=[],
        sources=sources,
        rank_for=lambda url: 99,
    )
    assert result.rank == 8
    assert result.recall_at_5 == 0.0
    assert abs(result.mrr - 1.0 / 8.0) < 1e-9
    assert result.cited_in_answer == 1.0


def test_evaluate_question_doc_ausente() -> None:
    sources = [{"url": "https://www.cte.fazenda.gov.br/other", "title": "t", "score": 0.5}]
    result = evaluate_question(
        question="q",
        expected_doc_url="https://www.nfe.fazenda.gov.br/correct",
        expected_keywords=[],
        sources=sources,
        rank_for=lambda url: None,
    )
    assert result.rank is None
    assert result.recall_at_5 == 0.0
    assert result.mrr == 0.0
    assert result.cited_in_answer == 0.0


def test_evaluate_question_sources_vazias() -> None:
    result = evaluate_question(
        question="q",
        expected_doc_url="https://www.nfe.fazenda.gov.br/x",
        expected_keywords=[],
        sources=[],
        rank_for=lambda url: None,
    )
    assert result.rank is None
    assert result.recall_at_5 == 0.0
    assert result.mrr == 0.0


def test_evaluate_question_match_por_dominio_e_keyword() -> None:
    """PLAN_SPRINT4 D.3: match por dominio + keyword compartilhada, NAO URL exata.

    ``expected_doc_url`` aponta para uma URL base (lista de NT), mas o
    source real tem URL completa com ID dinamico + token de sessao.
    O match deve ocorrer porque (a) hostname bate e (b) keyword "portal"
    aparece no source URL.
    """
    sources = [
        {
            "url": "https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=abc123=",
            "title": "Nota Tecnica 2019.001",
            "score": 0.92,
        },
        {
            "url": "https://www.cte.fazenda.gov.br/outro",
            "title": "Outra coisa",
            "score": 0.5,
        },
    ]
    result = evaluate_question(
        question="O que a NT 2019.001 altera?",
        expected_doc_url="https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx",
        expected_keywords=["portal"],
        sources=sources,
        rank_for=lambda url: 42,
    )
    assert result.rank == 1
    assert result.found_doc_id == 42
    assert result.recall_at_5 == 1.0


def test_evaluate_question_rejeita_dominio_diferente_mesmo_com_keyword() -> None:
    """Match NAO cruza dominios: keyword em URL de outro host NAO basta."""
    sources = [
        {
            "url": "https://www.cte.fazenda.gov.br/portal/exibirArquivo.aspx",
            "title": "CT-e NT",
            "score": 0.92,
        },
    ]
    result = evaluate_question(
        question="NF-e NT",
        expected_doc_url="https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx",
        expected_keywords=["portal"],
        sources=sources,
        rank_for=lambda url: None,
    )
    assert result.rank is None
    assert result.recall_at_5 == 0.0
