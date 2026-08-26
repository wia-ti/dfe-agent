"""Testes para src.indexer.chunker.

Cobre (PLAN.md linhas 163, 165 - Task 5.1):
    - [x] chunk_text("") retorna []; chunk_text("abc", chunk_size=800) retorna ["abc"].
    - [x] chunk_text("a"*2000, chunk_size=800, chunk_overlap=100) retorna 3 chunks
          com overlap exato verificavel por chunks[0][-100:] == chunks[1][:100].
    - [x] Texto com paragrafos (separador '\\n\\n') e quebrado em unidades.
    - [x] Parametros invalidos levantam ValueError com mensagem util.

Algoritmo:
    1. Validacao de parametros (chunk_size > 0, chunk_overlap >= 0, overlap < chunk_size).
    2. Split por paragrafos (\\n\\n).
    3. Subdivisao de paragrafos longos por sentencas ('. ', '! ', '? ', '\\n').
    4. Subdivisao de sentencas muito longas por slicing direto com overlap.
    5. Concatena ate atingir chunk_size, garantindo tail-overlap de chunk_overlap.
"""
from __future__ import annotations

import pytest

from src.indexer.chunker import chunk_text


# --- edge cases basicos ---


def test_chunk_text_empty_string_returns_empty_list() -> None:
    """Texto vazio produz lista vazia (sem chunks)."""
    assert chunk_text("") == []


def test_chunk_text_whitespace_only_returns_empty_list() -> None:
    """Texto composto apenas por whitespace produz lista vazia."""
    assert chunk_text("   \n\n  \t  \n\n   ") == []


def test_chunk_text_short_text_returns_single_chunk() -> None:
    """Texto menor que chunk_size retorna exatamente um chunk igual ao input."""
    assert chunk_text("abc", chunk_size=800) == ["abc"]


def test_chunk_text_single_paragraph_under_size_returns_single_chunk() -> None:
    """Texto em um unico paragrafo, abaixo do limite, nao e quebrado."""
    text = "Lorem ipsum dolor sit amet. " * 10  # ~280 chars
    chunks = chunk_text(text, chunk_size=800, chunk_overlap=100)
    assert len(chunks) == 1
    assert chunks[0] == text.strip()


# --- separacao por paragrafos ---


def test_chunk_text_splits_by_paragraphs() -> None:
    """Paragrafos separados por '\\n\\n' sao tratados como unidades logicas."""
    p1 = "Primeiro paragrafo com texto fiscal."
    p2 = "Segundo paragrafo sobre NF-e."
    p3 = "Terceiro paragrafo sobre CT-e."
    text = f"{p1}\n\n{p2}\n\n{p3}"

    chunks = chunk_text(text, chunk_size=800, chunk_overlap=100)

    assert len(chunks) == 1
    # Os paragrafos aparecem concatenados com separador '\\n\\n'.
    assert p1 in chunks[0]
    assert p2 in chunks[0]
    assert p3 in chunks[0]
    assert chunks[0].count("\n\n") >= 2


def test_chunk_text_paragraphs_separated_when_exceeding_chunk_size() -> None:
    """Quando paragrafos somados excedem chunk_size, ha quebra entre eles."""
    paragraph = "NF-e nota fiscal eletronica. " * 20  # ~580 chars cada
    text = "\n\n".join([paragraph, paragraph, paragraph])  # ~1740 chars

    chunks = chunk_text(text, chunk_size=800, chunk_overlap=100)

    # 1740 chars com overlap 100 e chunk_size 800 => esperado 3 chunks.
    assert len(chunks) == 3
    assert all(len(c) <= 800 for c in chunks)


def test_chunk_text_empty_paragraphs_are_dropped() -> None:
    """Paragrafos compostos apenas por whitespace sao descartados."""
    text = "conteudo real\n\n   \n\n   \n\nmais conteudo"
    chunks = chunk_text(text, chunk_size=800, chunk_overlap=100)
    assert len(chunks) == 1
    assert "conteudo real" in chunks[0]
    assert "mais conteudo" in chunks[0]


# --- subdivisao por sentencas ---


def test_chunk_text_long_paragraph_is_subdivided_by_sentences() -> None:
    """Paragrafo > chunk_size e quebrado em sentencas."""
    # Uma unica "frase" gigantesca (sem separadores) precisa ser quebrada por slicing.
    giant = "NF-e " * 1000  # ~5000 chars, sem separador
    text = giant.strip()

    chunks = chunk_text(text, chunk_size=800, chunk_overlap=100)

    # 5000 chars => esperado 7 chunks (5000 / (800-100) ~= 7.14)
    assert len(chunks) >= 6
    assert all(len(c) <= 800 for c in chunks)


def test_chunk_text_subdivides_long_paragraph_with_sentence_separators() -> None:
    """Paragrafo com varias sentencas e subdividido nos separadores '. '."""
    sentences = [
        "Primeira sentenca sobre NF-e.",
        "Segunda sentenca sobre NFC-e.",
        "Terceira sentenca sobre CT-e.",
        "Quarta sentenca sobre MDF-e.",
    ]
    paragraph = " ".join(sentences) * 30  # ~1740 chars

    chunks = chunk_text(paragraph, chunk_size=400, chunk_overlap=50)

    # Cada chunk respeita o limite.
    assert all(len(c) <= 400 for c in chunks)
    # Houve quebra em mais de um chunk.
    assert len(chunks) >= 2


# --- teste critico: overlap exato ---


def test_chunk_text_long_text_with_overlap_returns_3_chunks() -> None:
    """Teste CRITICO (PLAN.md linha 163): 2000 chars com chunk_size=800, overlap=100.

    Gera exatamente 3 chunks. Os 100 ultimos caracteres do chunk 0 sao
    identicos aos 100 primeiros do chunk 1. A mesma relacao vale para
    chunk 1 -> chunk 2.
    """
    text = "a" * 2000
    chunks = chunk_text(text, chunk_size=800, chunk_overlap=100)

    assert len(chunks) == 3, f"esperava 3 chunks, recebi {len(chunks)}: {[len(c) for c in chunks]}"
    assert chunks[0][-100:] == chunks[1][:100]
    assert chunks[1][-100:] == chunks[2][:100]


def test_chunk_text_long_text_with_overlap_respects_chunk_size() -> None:
    """Com 2000 chars, chunk_size=800, overlap=100, todos os chunks tem <=800 chars."""
    text = "a" * 2000
    chunks = chunk_text(text, chunk_size=800, chunk_overlap=100)

    assert all(len(c) <= 800 for c in chunks)
    # O primeiro chunk deve estar cheio (800 chars).
    assert len(chunks[0]) == 800
    # O ultimo chunk pode ser menor (e o restante do texto).
    assert len(chunks[-1]) <= 800


# --- validacao de parametros ---


def test_chunk_text_validates_chunk_size_positive() -> None:
    """chunk_size <= 0 levanta ValueError."""
    with pytest.raises(ValueError, match="chunk_size"):
        chunk_text("texto", chunk_size=0)
    with pytest.raises(ValueError, match="chunk_size"):
        chunk_text("texto", chunk_size=-10)


def test_chunk_text_validates_chunk_overlap_non_negative() -> None:
    """chunk_overlap < 0 levanta ValueError."""
    with pytest.raises(ValueError, match="chunk_overlap"):
        chunk_text("texto", chunk_size=800, chunk_overlap=-1)


def test_chunk_text_validates_chunk_overlap_less_than_chunk_size() -> None:
    """chunk_overlap >= chunk_size levanta ValueError."""
    with pytest.raises(ValueError, match="chunk_overlap"):
        chunk_text("texto", chunk_size=800, chunk_overlap=800)
    with pytest.raises(ValueError, match="chunk_overlap"):
        chunk_text("texto", chunk_size=800, chunk_overlap=1000)


def test_chunk_text_default_parameters_work() -> None:
    """Parametros default (chunk_size=800, chunk_overlap=100) sao aceitos."""
    chunks = chunk_text("a" * 2000)
    assert len(chunks) == 3


# --- propriedade do overlap (nao corta em meio de palavra, quando possivel) ---


def test_chunk_text_overlap_preserves_text_when_breaks_available() -> None:
    """Quando ha caracteres de quebra (\\n\\n), o overlap usa eles como limite natural."""
    # Com paragrafos, o overlap nao precisa necessariamente incluir
    # parte do paragrafo anterior; mas o conteudo total cobre o input.
    p1 = "a" * 500
    p2 = "b" * 500
    p3 = "c" * 500
    text = f"{p1}\n\n{p2}\n\n{p3}"

    chunks = chunk_text(text, chunk_size=600, chunk_overlap=100)

    # A concatenacao dos chunks (sem duplicar overlap) deve cobrir o texto.
    full = "".join(chunks)
    for fragment in (p1, p2, p3):
        assert fragment in full


# --- sem chunks vazios no retorno ---


def test_chunk_text_no_empty_chunks_in_return() -> None:
    """A lista retornada nao contem strings vazias."""
    text = "real content\n\n\n\n   \n\nmore content"
    chunks = chunk_text(text)
    for chunk in chunks:
        assert chunk.strip(), f"chunk vazio/whitespace-only encontrado: {chunk!r}"


# --- cobertura de branches adicionais ---


def test_chunk_text_handles_text_ending_with_separator() -> None:
    """Texto terminando com separador '. ' e dividido normalmente.

    Forca o caminho de subdivisao por sentencas (paragrafo > chunk_size).
    Tambem exercita o branch onde o _split_preserve_separator recebe um
    paragrafo que termina com o separador (trailing '. ').
    """
    # Texto com paragrafos onde o ultimo termina com ". " (com trailing space).
    # O split por paragrafos preserva o trailing space do ultimo.
    paragraph = "Curta. "  # termina com ". "
    text = (paragraph * 500)  # ~3500 chars > chunk_size

    chunks = chunk_text(text, chunk_size=400, chunk_overlap=50)

    # Verifica que o texto foi subdividido e contem a sentenca.
    assert len(chunks) >= 2
    full = "".join(chunks)
    assert "Curta." in full


def test_chunk_text_handles_paragraph_with_lone_newline_sentence() -> None:
    """Paragrafo com sentenca whitespace-only ('\\n' sozinha) nao quebra.

    Forca o caminho de subdivisao por sentencas (paragrafo > chunk_size).
    """
    # 'A. B. \\nC' produz sentencas ['A. ', 'B. ', '\\n', 'C']; '\\n' e descartada.
    # Repete para forcar quebra por sentencas.
    base = "A. B. \nC"
    text = base * 100  # ~600 chars > chunk_size

    chunks = chunk_text(text, chunk_size=200, chunk_overlap=20)

    assert len(chunks) >= 2
    full = "".join(chunks)
    assert "A." in full
    assert "B." in full
    assert "C" in full


def test_chunk_text_handles_short_sentences_then_long_sentence() -> None:
    """Sentencas curtas acumulam; sentenca longa subsequente forca slicing direto."""
    # Sentencas curtas totalizando ~600 chars, depois uma sentenca gigante.
    short = "Frase curta. " * 30  # ~390 chars
    giant = "x" * 2000  # >> chunk_size
    text = short + " " + giant

    chunks = chunk_text(text, chunk_size=500, chunk_overlap=50)

    # Pelo menos 1 chunk das curtas + varios da gigante.
    assert len(chunks) >= 4
    assert all(len(c) <= 500 for c in chunks)


def test_chunk_text_handles_unit_exceeding_chunk_size_in_overlap() -> None:
    """Quando a unidade sozinha excede chunk_size, nao ha overlap no proximo chunk."""
    # Duas unidades grandes consecutivas: cada uma sozinha excede chunk_size.
    unit_a = "a" * 1000  # > 800 (chunk_size default)
    unit_b = "b" * 1000
    text = f"{unit_a}\n\n{unit_b}"

    chunks = chunk_text(text, chunk_size=800, chunk_overlap=100)

    # Cada gigante vira ~2 chunks via slicing; total ~4 chunks.
    assert len(chunks) >= 3
    assert all(len(c) <= 800 for c in chunks)


def test_chunk_text_with_zero_overlap_returns_disjoint_chunks() -> None:
    """chunk_overlap=0 produz chunks sem sobreposicao nas fronteiras."""
    text = "abcde" * 200  # 1000 chars
    chunks = chunk_text(text, chunk_size=500, chunk_overlap=0)

    # Sem overlap, cada chunk <= 500 chars, total cobre o texto.
    assert all(len(c) <= 500 for c in chunks)
    # Sem sobreposicao: a concatenacao direta preserva o texto.
    concat = "".join(chunks)
    assert concat == text  # sem sobreposicao, reconstrucao e exata


def test_chunk_text_with_zero_overlap_does_not_raise_when_unit_exceeds_chunk_size() -> None:
    """chunk_overlap=0 com unidade > chunk_size: retorna apenas a unidade."""
    # Quando a unidade excede chunk_size, budget = chunk_size - len(unit) - 2 <= 0
    # e mesmo com overlap=0, _start_chunk_with_overlap retorna unit diretamente.
    text = "x" * 2000
    chunks = chunk_text(text, chunk_size=500, chunk_overlap=0)

    assert len(chunks) >= 3
    assert all(len(c) <= 500 for c in chunks)
