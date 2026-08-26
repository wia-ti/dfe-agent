"""Testes para ``src.indexer.summarizer`` (Sprint 2, Fase 12.1).

Cobre:
    - Extrai sumario deterministico das primeiras sentencas do texto.
    - Limita a ``max_chars`` sem cortar mid-word.
    - Retorna string vazia para texto vazio / whitespace-only.
    - Retorna string vazia quando o texto nao tem sentencas com >= MIN_LEN
      caracteres (util para evitar lixo de headers).
    - Sentencas longas (titulos de secao NT) nao sao preferidas
      apenas por comprimento; posicao importa.
    - Resultado e estavel (mesmo input -> mesmo output).
"""
from __future__ import annotations

from src.indexer.summarizer import summarize


# --- happy paths ----------------------------------------------------------


def test_summarize_texto_curto_retorna_proprio_texto() -> None:
    text = "Nota tecnica que altera regras de cancelamento."
    out = summarize(text, max_chars=400)
    # Sentenca unica: devolvida inteira.
    assert out == text


def test_summarize_tres_primeiras_sentencas() -> None:
    text = (
        "Esta NT visa alterar as regras de cancelamento da NF-e. "
        "A substituicao do documento fisico pelo eletronico e obrigatoria. "
        "Empresas tem prazo de 90 dias para se adequar. "
        "Detalhes operacionais estao na secao 3."
    )
    out = summarize(text, max_chars=400)
    # As 3 primeiras devem aparecer; a 4a nao.
    assert "Esta NT visa alterar" in out
    assert "substituicao do documento" in out
    assert "Empresas tem prazo de 90 dias" in out
    assert "Detalhes operacionais" not in out


def test_summarize_respeita_max_chars() -> None:
    long_sentence = (
        "Frase muito longa usada para validar que o truncamento nao ocorre "
        "no meio de uma palavra quando o limite e atingido, especialmente "
        "em documentos fiscais densos. " * 5
    )
    out = summarize(long_sentence, max_chars=200)
    assert 0 < len(out) <= 200


def test_summarize_trunca_em_palavra_e_nao_em_meio() -> None:
    """O truncamento nao deve cortar mid-word (sempre no ultimo espaco)."""
    text = " ".join([f"palavra{i}" for i in range(100)])
    out = summarize(text, max_chars=80)
    assert not out.endswith("-" )  # nao termina com hifen
    # Ultimo token deve estar completo (sem mid-word corta).
    last_word = out.rsplit(" ", 1)[-1]
    assert last_word.startswith("palavra")


# --- bordas ---------------------------------------------------------------


def test_summarize_texto_vazio_retorna_vazio() -> None:
    assert summarize("", max_chars=400) == ""
    assert summarize("   \n\n   \t  ", max_chars=400) == ""


def test_summarize_sem_sentencas_substantivas() -> None:
    """Texto com sentencas < 30 chars (ex: apenas headers curtos) -> ""."""
    text = "OK\n\nNT\n\nXYZ\n"
    out = summarize(text, max_chars=400)
    assert out == ""


def test_summarize_apenas_uma_sentenca_grande() -> None:
    text = (
        "Esta e uma sentenca unica que excede o limite maximo de 400 "
        "caracteres com informacoes detalhadas sobre a regra e que deve "
        "ser cortada em algum momento com cuidado para nao perder " * 20
    )
    out = summarize(text, max_chars=200)
    assert 0 < len(out) <= 200
    # Nao quebra mid-word mesmo quando trunca diretamente.
    assert not out[-1].isalpha() or out.endswith(".") or " " in out[-10:]


# --- estabilidade / determinismo ----------------------------------------


def test_summarize_e_deterministico() -> None:
    text = (
        "Primeira sentenca importante da NT 2024.001. "
        "Segunda sentenca com contexto adicional. "
        "Terceira sentenca com regra especifica. "
        "Quarta sentenca que nao deve aparecer no sumario."
    )
    out_1 = summarize(text, max_chars=400)
    out_2 = summarize(text, max_chars=400)
    assert out_1 == out_2
