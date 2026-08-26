"""Teste E2E: pipeline completo (coleta -> ingestao -> consulta)."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import sqlite_vec

from src.collector.downloader import DocumentCollector
from src.collector.portal_index import PORTAL_URLS
from src.db.sqlite_storage import SqliteStorage
from src.db.vector_store import VectorStore
from src.indexer.embeddings import EmbeddingProvider
from src.indexer.rag_indexer import RagIndexer
from src.parser.pdf_parser import extract_text_from_pdf
from src.query.query_engine import QueryEngine


# Modelo menor para os subprocessos CLI: 91MB vs 470MB do padrao.
# pytest + modelo + subprocess CLI excedem memoria em ambientes com
# 16GB; usar o modelo menor mantem o suite estavel. Lido por
# ``src/indexer/embeddings.py`` no module-load via env var.
_E2E_MODEL_NAME: str = "all-MiniLM-L6-v2"


@pytest.mark.integration
def test_e2e_collect_index_answer(
    fake_portal_url: str,
    temp_storage: dict[str, Path],
    tmp_path: Path,
) -> None:
    """E2E: descobre docs no portal fake, baixa, indexa, consulta."""
    db_path: Path = temp_storage["db_path"]
    data_dir: Path = temp_storage["data_dir"]

    storage = SqliteStorage(db_path)
    storage.init_schema()
    vector_store = VectorStore(db_path, dim=384)
    vector_store.init_schema()

    custom_urls: dict[str, str] = {
        "nfe": f"{fake_portal_url}/nfe/",
        "confaz": f"{fake_portal_url}/confaz/",
    }

    fake_allowed_domains: list[str] = [
        "nfe.fazenda.gov.br",
        "nfce.fazenda.gov.br",
        "cte.fazenda.gov.br",
        "mdfe.fazenda.gov.br",
        "sped.rfb.gov.br",
        "confaz.fazenda.gov.br",
        "127.0.0.1",
    ]

    with patch.dict(PORTAL_URLS, custom_urls, clear=True), \
         patch("src.collector.portal_index.ALLOWED_DOMAINS", fake_allowed_domains):
        from src.utils.throttler import Throttler

        throttler = Throttler(request_interval_ms=0, jitter_ms=0)
        collector = DocumentCollector(
            storage, throttler, data_dir, allowed_domains=fake_allowed_domains
        )

        n_registered: int = collector.discover_and_register()
        assert n_registered >= 2, f"Esperado >= 2 docs, registrou {n_registered}"

        n_downloaded: int = collector.download_pending()
        assert n_downloaded >= 1, f"Esperado >= 1 download, baixou {n_downloaded}"

    pending = storage.list_pending()
    assert len(pending) >= 1, "Pelo menos 1 doc deveria estar pendente de ingestao"

    embedder = EmbeddingProvider(_E2E_MODEL_NAME)
    indexer = RagIndexer(storage, vector_store, embedder, parser=extract_text_from_pdf)
    n_indexed: int = indexer.ingest_pending()
    assert n_indexed >= 1, f"Esperado >= 1 indexado, indexou {n_indexed}"

    conn = sqlite3.connect(str(db_path))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    cursor = conn.execute("SELECT COUNT(*) FROM documents WHERE status='ingerido'")
    n_ingerido: int = cursor.fetchone()[0]
    assert n_ingerido >= 1, f"Esperado >= 1 documento com status='ingerido', encontrou {n_ingerido}"

    cursor = conn.execute("SELECT COUNT(*) FROM vec_chunks")
    n_chunks: int = cursor.fetchone()[0]
    assert n_chunks >= 1, f"Esperado >= 1 chunk, encontrou {n_chunks}"
    conn.close()

    engine = QueryEngine(vector_store, embedder, min_score=0.3)
    results = engine.search("Nota Tecnica NF-e")
    assert len(results) >= 1, f"Esperado >= 1 chunk relevante, encontrou {len(results)}"
    assert any(
        "127.0.0.1" in r.source_url or "nfe" in r.source_url.lower()
        for r in results
    )


@pytest.mark.integration
def test_e2e_query_no_evidence(tmp_path: Path) -> None:
    """E2E: python -m src.query contra base vazia retorna NO_EVIDENCE_MESSAGE."""
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    db_path = storage_dir / "dfe.db"
    assert not db_path.exists()

    project_root = Path(__file__).resolve().parents[2]
    opencode_path = project_root / ".opencode"
    env = os.environ.copy()
    existing_pp = env.get("PYTHONPATH", "")
    pp_parts: list[str] = [str(project_root), str(opencode_path)]
    if existing_pp:
        pp_parts.append(existing_pp)
    env["PYTHONPATH"] = os.pathsep.join(pp_parts)
    # Mesmo modelo da pipeline in-process para garantir subprocesso usa o
    # modelo menor (91MB), evitando OOM em ambiente com pouca RAM.
    env["DFE_EMBEDDING_MODEL"] = _E2E_MODEL_NAME
    # Mitiga OpenBLAS "Memory allocation still failed" em Windows.
    env.setdefault("OPENBLAS_NUM_THREADS", "1")
    env.setdefault("OMP_NUM_THREADS", "1")

    result = subprocess.run(
        [sys.executable, "-m", "src.query", "pergunta aleatoria xyz"],
        capture_output=True, text=True, cwd=str(tmp_path), check=False, env=env,
    )

    assert result.returncode == 0, f"CLI falhou: stderr={result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["answer"] == "Nao encontrei base para responder"
    assert payload["sources"] == []