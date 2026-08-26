"""Conftest do test_rag_indexer: injeta stub de ``src.indexer.chunker`` em
``sys.modules`` apenas quando o modulo real NAO esta disponivel.

Se ``src/indexer/chunker.py`` existir no disco (Task 5.1 completa), o modulo
real sera carregado e o stub NAO sera injetado. O stub existe apenas como
rede de seguranca para builds paralelos onde o modulo real ainda nao foi
commitado.

Quando ativo, o stub implementa a mesma API observada pelos testes de
``rag_indexer``:
    - texto vazio / whitespace-only -> ``[]``
    - texto curto -> ``[texto]``
    - texto longo -> subdivide em fatias de ``chunk_size`` (800) com
      ``chunk_overlap`` (100) preservado nas fronteiras.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from typing import List


def _stub_chunk_text(
    text: str,
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> List[str]:
    """Stub minimo de chunk_text para uso em testes enquanto Task 5.1 converge."""
    if chunk_size <= 0:
        raise ValueError(f"chunk_size deve ser > 0, recebeu {chunk_size}")
    if chunk_overlap < 0:
        raise ValueError(f"chunk_overlap deve ser >= 0, recebeu {chunk_overlap}")
    if chunk_overlap >= chunk_size:
        raise ValueError(
            f"chunk_overlap ({chunk_overlap}) deve ser < chunk_size ({chunk_size})"
        )
    if not text or not text.strip():
        return []
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    units: List[str] = []
    for p in paragraphs:
        if len(p) <= chunk_size:
            units.append(p)
        else:
            start = 0
            while start < len(p):
                end = min(start + chunk_size, len(p))
                units.append(p[start:end])
                if end >= len(p):
                    break
                start = end - chunk_overlap
    if not units:
        return []
    chunks: List[str] = []
    current = ""
    for unit in units:
        if not current:
            current = unit
            continue
        candidate = (current + "\n\n" + unit).strip()
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            chunks.append(current)
            if chunk_overlap > 0 and chunks:
                tail = chunks[-1][-chunk_overlap:]
                idx = tail.find(" ")
                if idx != -1 and idx + 1 < len(tail):
                    tail = tail[idx + 1 :]
                current = (tail + "\n\n" + unit).strip()
            else:
                current = unit
    if current:
        chunks.append(current)
    return [c for c in chunks if c.strip()]


def _ensure_chunker_stub() -> None:
    """Garante que ``src.indexer.chunker`` resolva para algo que tem ``chunk_text``.

    Se o modulo real existe em disco (Task 5.1 concluida), faz import real
    e NAO instala o stub. Caso contrario, instala stub em sys.modules para
    que o teste de Task 5.2 (rag_indexer) funcione durante build paralelo.
    """
    full_name = "src.indexer.chunker"
    # Se ja foi importado (caso normal), confia no modulo em cache.
    if full_name in sys.modules:
        mod = sys.modules[full_name]
        if hasattr(mod, "chunk_text"):
            return
    # Verifica se o modulo real existe no disco.
    spec = importlib.util.find_spec(full_name)
    if spec is not None:
        # Modulo real disponivel: importa via importlib para evitar aliasing
        # com o stub em sys.modules antes do import efetivo.
        try:
            importlib.import_module(full_name)
            return
        except Exception:
            # Se o import falhar, cai no stub como fallback.
            pass
    # Modulo real ausente ou falhou ao importar: instala stub.
    mod = types.ModuleType(full_name)
    mod.chunk_text = _stub_chunk_text  # type: ignore[attr-defined]
    sys.modules[full_name] = mod


_ensure_chunker_stub()