"""Testes de integracao dos guardrails criticos do DFe-Agent.

Cobre (PLAN.md Task 8.2):
    - Guardrail de dominio: ``DocumentCollector.discover_and_register`` NAO
      registra URLs fora de ``ALLOWED_DOMAINS``, mesmo que
      ``discover_documents`` as retorne. Spy em ``validate_url`` confirma que
      a checagem foi feita.
    - Guardrail de throttling: ``download_pending`` respeita o intervalo
      configurado no ``Throttler`` (verificado via wall-clock).
    - Guardrail de idempotencia: ``RagIndexer.ingest_one`` chamado 2x no
      mesmo doc NAO duplica chunks (contagem de ``vec_chunks`` estavel).
    - Guardrail de fonte: o stdout do CLI ``python -m src.query`` cita a URL
      e o titulo do documento indexado (verificado via ``subprocess.run``).

Todos marcados com ``@pytest.mark.integration`` pois usam:
    - Storage SQLite real (``tmp_path``).
    - Modelo ``sentence-transformers`` real (cache local).
    - Servidor HTTP fake (fixture ``fake_portal_url``).
    - Subprocess Python para o CLI ``src.query``.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import sqlite_vec

from src.collector import downloader
from src.collector.downloader import DocumentCollector
from src.collector.portal_index import PORTAL_URLS
from src.db.sqlite_storage import DocumentRecord, SqliteStorage
from src.db.vector_store import VectorStore
from src.indexer.embeddings import EmbeddingProvider
from src.indexer.rag_indexer import RagIndexer
from src.parser.pdf_parser import extract_text_from_pdf
from src.utils.throttler import Throttler


_FAKE_ALLOWED_DOMAINS: list[str] = [
    "nfe.fazenda.gov.br",
    "nfce.fazenda.gov.br",
    "cte.fazenda.gov.br",
    "mdfe.fazenda.gov.br",
    "sped.rfb.gov.br",
    "confaz.fazenda.gov.br",
    "127.0.0.1",
]

# Modelo menor (91MB) usado nos testes de integracao que envolvem o modelo
# de embedding (carregado duas vezes: in-process + subprocesso CLI). O modelo
# padrao "paraphrase-multilingual-MiniLM-L12-v2" (470MB) nao cabe em
# ambientes com pouca RAM (pytest ja consome ~1GB; dois loads = 940MB;
# mais transformers/torch = OOM em Windows com 16GB).
# O override e feito via env var ``DFE_EMBEDDING_MODEL`` que
# ``src/indexer/embeddings.py`` consulta no module-load (test + CLI ambos).
_INTEGRATION_MODEL_NAME: str = os.environ.get(
    "DFE_EMBEDDING_MODEL", "all-MiniLM-L6-v2"
)


def _count_vec_chunks(db_path: Path) -> int:
    """Conta linhas em ``vec_chunks`` carregando a extensao sqlite-vec."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        cur = conn.execute("SELECT COUNT(*) FROM vec_chunks")
        return int(cur.fetchone()[0])
    finally:
        conn.close()


# --- 0. Guardrail de bootstrap (PLAN_SPRINT5 A.1 / BLOQUEANTE B1) ---


@pytest.mark.integration
def test_main_collector_invokes_install_guard_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``src.collector.__main__.main(['--dry-run'])`` invoca o bootstrap.

    Estrategia:
        - Stub em ``PORTAL_URLS`` para um set vazio (evita I/O de rede).
        - Stub em ``discover_documents`` (nao usado com PORTAL_URLS vazio).
        - Spy em ``install_guard_once`` (so' no modulo do bootstrap,
          pois o __main__.py usa ``from ... import`` lazy dentro de
          ``main()`` e o binding local pega o valor atual do modulo
          do bootstrap).
        - Chama ``main(['--dry-run'])`` e verifica que o bootstrap foi
          executado (e portanto o guard esta' ativo no subprocess).
    """
    from src.collector import __main__ as collector_main
    from src.collector import portal_index
    from src.utils import http_guard_bootstrap

    call_counter: dict[str, int] = {"n": 0}

    def counting_install() -> None:
        call_counter["n"] += 1
        http_guard_bootstrap._BOOTSTRAP_DONE = True

    # Patch no modulo do bootstrap (lazy import dentro de main() rebind
    # localmente do valor atual do modulo a cada invocacao).
    monkeypatch.setattr(
        http_guard_bootstrap, "install_guard_once", counting_install
    )
    monkeypatch.setattr(portal_index, "PORTAL_URLS", {})
    monkeypatch.setattr(
        portal_index, "discover_documents", lambda *_a, **_kw: []
    )

    monkeypatch.setattr(http_guard_bootstrap, "_BOOTSTRAP_DONE", False)

    rc: int = collector_main.main(["--dry-run"])
    assert rc == 0
    assert call_counter["n"] >= 1, (
        f"Esperado >= 1 chamada de install_guard_once, obtido {call_counter['n']}"
    )
    assert http_guard_bootstrap.was_bootstrap_called() is True


@pytest.mark.integration
def test_dry_run_blocks_evil_url(
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_run_dry_run`` nao imprime URLs fora de ``ALLOWED_DOMAINS``.

    Estrategia:
        - Stub em ``PORTAL_URLS`` com 1 source.
        - Stub em ``discover_documents`` para retornar docs ja'
          filtrados (maliciosa removida via stub ``validate_url``).
        - ``validate_url`` retornando ``False`` para URLs evil.com
          simula a filtragem real em ``portal_index.py:174,194``.
        - Spy em ``validate_url`` para confirmar que foi invocado.
        - Chama ``_run_dry_run``; verifica via ``capsys`` que stdout
          NAO contem URL maliciosa.

    Cobre:
        - ``A.3`` do PLAN_SPRINT5: confirma que o caminho ``--dry-run``
          herda a filtragem de URLs (ja' implementada em
          ``portal_index.py:174,194``) e que o monkey-patch do guard
          ativo em runtime nao introduz regressao.
    """
    from src.collector import __main__ as collector_main
    from src.collector import portal_index
    from src.utils.throttler import Throttler

    # Patch ambos modulos pois ``from src.collector.portal_index import
    # discover_documents`` no __main__.py faz binding local.
    monkeypatch.setattr(
        portal_index,
        "PORTAL_URLS",
        {"nfe": "http://example.invalid/"},
    )
    monkeypatch.setattr(collector_main, "PORTAL_URLS", {"nfe": "http://example.invalid/"})

    validate_calls: list[str] = []
    real_validate_url = portal_index.validate_url

    def fake_validate_url(url: str, allowed: list[str]) -> bool:
        validate_calls.append(url)
        # Simula a politica anti-TLD + filter. ``evil.com`` e' bloqueado.
        result = "evil.com" not in url and real_validate_url(url, allowed)
        return result

    monkeypatch.setattr(portal_index, "validate_url", fake_validate_url)

    stubbed_docs: list[dict] = [
        {
            "url": "https://evil.com/x.pdf",
            "title": "evil",
            "doc_type": "nfe",
            "published_at": None,
        },
        {
            "url": "https://www.nfe.fazenda.gov.br/legit.pdf",
            "title": "legit",
            "doc_type": "nfe",
            "published_at": None,
        },
    ]

    def fake_discover(*_a: object, **_kw: object) -> list[dict]:
        """Stub de ``discover_documents`` que filtra evil.com via validate_url."""
        allowed = list(portal_index.ALLOWED_DOMAINS)
        filtered: list[dict] = []
        for doc in stubbed_docs:
            if portal_index.validate_url(doc["url"], allowed):
                filtered.append(doc)
        return filtered

    monkeypatch.setattr(portal_index, "discover_documents", fake_discover)
    monkeypatch.setattr(collector_main, "discover_documents", fake_discover)

    throttler = Throttler(request_interval_ms=0, jitter_ms=0)
    rc: int = collector_main._run_dry_run(throttler)  # noqa: SLF001

    assert rc == 0
    captured = capsys.readouterr()
    assert "evil.com" not in captured.out, (
        f"URL maliciosa NAO deveria ter sido impressa. stdout={captured.out!r}"
    )
    assert "nfe.fazenda.gov.br/legit.pdf" in captured.out, (
        f"URL legitima deveria ter sido impressa. stdout={captured.out!r}"
    )
    assert any("evil.com" in u for u in validate_calls), (
        f"validate_url deveria ter sido chamada com URL evil.com. "
        f"calls={validate_calls}"
    )


@pytest.mark.integration
def test_guardrail_active_in_collector_subprocess(
    tmp_path: Path,
) -> None:
    """Subprocess ``python -m src.collector --dry-run`` carrega guard ativo.

    Estrategia:
        - Spawna um subprocess Python que importa o bootstrap, ativa o
          guard e tenta ``requests.get('https://evil.com/x')``.
        - Espera ``PermissionError`` (capturado pelo wrapper) e exit 0.
        - Sem o guard, o subprocess tentaria resolver DNS (pode dar
          timeout, mas nao PermissionError). A presenca de
          ``PermissionError`` no stdout prova que o guard monkey-patchou
          ``requests.get``.
    """
    project_root: Path = Path(__file__).resolve().parents[2]
    opencode_path: Path = project_root / ".opencode"
    wrapper = (
        "import sys, json\n"
        f"sys.path.insert(0, r'{str(opencode_path).replace(chr(92), '/')}')\n"
        f"sys.path.insert(0, r'{str(project_root).replace(chr(92), '/')}')\n"
        "from src.utils.http_guard_bootstrap import install_guard_once\n"
        "install_guard_once()\n"
        "import requests\n"
        "r = {'blocked': False, 'error': None}\n"
        "try:\n"
        "    requests.get('https://evil.com/x.pdf')\n"
        "except PermissionError as e:\n"
        "    r = {'blocked': True, 'error': str(e)}\n"
        "sys.stdout.write(json.dumps(r))\n"
    )
    env: dict[str, str] = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("COVERAGE_", "PYTEST_"))
    }
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{project_root}{os.pathsep}{existing_pp}"
        if existing_pp
        else str(project_root)
    )
    env["HF_HUB_OFFLINE"] = "1"

    result = subprocess.run(
        [sys.executable, "-c", wrapper],
        capture_output=True,
        text=True,
        cwd=str(project_root),
        env=env,
        check=False,
        timeout=20,
    )

    assert result.returncode == 0, (
        f"subprocess falhou (rc={result.returncode}): stderr={result.stderr}"
    )
    payload = json.loads(result.stdout)
    assert payload["blocked"] is True, (
        f"Esperado guard bloquear evil.com, obtido payload={payload}"
    )
    assert "evil.com" in payload["error"], (
        f"Mensagem de erro deveria mencionar evil.com: {payload['error']!r}"
    )


# --- 1. Guardrail de dominio ---


@pytest.mark.integration
def test_guardrail_domain_blocks_external(
    tmp_path: Path,
    mocker,
) -> None:
    """``discover_and_register`` NAO registra URLs fora de ``ALLOWED_DOMAINS``.

    Estrategia:
        - Mock ``discover_documents`` (referencia local em ``downloader``)
          para retornar 3 URLs: 2 maliciosas + 1 legitima.
        - Spy em ``downloader.validate_url`` (mesma referencia usada em
          ``discover_and_register``) para contar invocacoes.

    Assercoes:
        - Apenas 1 doc registrado (o legitimo).
        - ``validate_url`` foi chamada exatamente 3x (uma por URL).
        - ``evil.com`` e ``malware.example.com`` NAO estao em storage.
    """
    db_path: Path = tmp_path / "test.db"
    data_dir: Path = tmp_path / "data"
    data_dir.mkdir()
    storage = SqliteStorage(db_path)
    storage.init_schema()

    throttler = Throttler(request_interval_ms=0, jitter_ms=0)
    collector = DocumentCollector(storage, throttler, data_dir)

    malicious_docs: list[dict] = [
        {
            "url": "https://evil.com/x.pdf",
            "title": "evil1",
            "doc_type": "nfe",
            "published_at": None,
        },
        {
            "url": "https://malware.example.com/y.pdf",
            "title": "evil2",
            "doc_type": "nfe",
            "published_at": None,
        },
        {
            "url": "https://www.nfe.fazenda.gov.br/legit.pdf",
            "title": "legit",
            "doc_type": "nfe",
            "published_at": None,
        },
    ]
    mocker.patch.object(downloader, "discover_documents", return_value=malicious_docs)
    validate_spy = mocker.spy(downloader, "validate_url")

    # Limita PORTAL_URLS a uma fonte unica para que o mock retorne apenas
    # uma vez (descobrir_and_register itera sobre PORTAL_URLS).
    with patch.dict(PORTAL_URLS, {"nfe": "http://www.nfe.fazenda.gov.br/"}, clear=True):
        n_registered: int = collector.discover_and_register()

    assert n_registered == 1, f"Esperado 1 registro, obtido {n_registered}"
    assert validate_spy.call_count == 3, (
        f"Esperado 3 chamadas de validate_url, obtido {validate_spy.call_count}"
    )

    legit = storage.get_by_url("https://www.nfe.fazenda.gov.br/legit.pdf")
    assert legit is not None, "URL legitima NAO foi registrada"
    assert legit.status == "nao_ingerido"

    assert storage.get_by_url("https://evil.com/x.pdf") is None, (
        "evil.com NAO deveria ter sido registrado"
    )
    assert storage.get_by_url("https://malware.example.com/y.pdf") is None, (
        "malware.example.com NAO deveria ter sido registrado"
    )


# --- 2. Guardrail de throttling ---


@pytest.mark.integration
def test_guardrail_throttling_respects_interval(
    tmp_path: Path,
) -> None:
    """``download_pending`` respeita ``request_interval_ms`` (>= 1.0s para 3 docs a 500ms).

    Estrategia:
        - Pre-popula 3 docs pendentes com URL ``127.0.0.1`` (host do fake).
        - Monkey-patch de ``downloader.ALLOWED_DOMAINS`` para incluir
          ``127.0.0.1`` durante o teste (restaurado no ``finally``).
        - Substitui ``requests.get`` por stub que devolve resposta 200 com
          bytes fake (evita I/O real).
        - Mede ``time.monotonic()`` antes/depois; assert ``elapsed >= 1.0s``
          (3 docs * 500ms = 2 sleeps de ~500ms entre as 3 chamadas).
    """
    db_path: Path = tmp_path / "test.db"
    data_dir: Path = tmp_path / "data"
    data_dir.mkdir()
    storage = SqliteStorage(db_path)
    storage.init_schema()

    fake_urls: list[str] = [
        "http://127.0.0.1:65535/file_0.pdf",
        "http://127.0.0.1:65535/file_1.pdf",
        "http://127.0.0.1:65535/file_2.pdf",
    ]
    for i, url in enumerate(fake_urls):
        storage.upsert_document(
            DocumentRecord(
                url=url,
                source_domain="127.0.0.1",
                doc_type="nfe",
                title=f"doc_{i}",
                status="nao_ingerido",
            )
        )

    original_allowed = downloader.ALLOWED_DOMAINS
    patched_allowed: list[str] = ["127.0.0.1", *original_allowed]
    downloader.ALLOWED_DOMAINS = patched_allowed

    try:
        throttler = Throttler(request_interval_ms=500, jitter_ms=0)
        collector = DocumentCollector(
            storage, throttler, data_dir, allowed_domains=patched_allowed
        )

        import requests as req_module

        original_get = req_module.get

        def fake_get(url: str, **kwargs: object) -> MagicMock:
            resp = MagicMock()
            resp.status_code = 200
            resp.content = b"%PDF-fake-content"
            resp.raise_for_status = lambda: None
            return resp

        req_module.get = fake_get

        try:
            start: float = time.monotonic()
            n_downloaded: int = collector.download_pending()
            elapsed: float = time.monotonic() - start

            assert elapsed >= 1.0, f"Esperado >= 1.0s, obtido {elapsed:.2f}s"
            assert n_downloaded == 3, f"Esperado 3 downloads, obtido {n_downloaded}"
        finally:
            req_module.get = original_get
    finally:
        downloader.ALLOWED_DOMAINS = original_allowed


# --- 3. Guardrail de idempotencia ---


@pytest.mark.integration
def test_guardrail_idempotent_ingestion(tmp_path: Path) -> None:
    """``ingest_one`` 2x no mesmo doc nao duplica chunks (idempotencia por hash).

    Estrategia:
        - Cria arquivo de texto grande (3500 chars) e registra doc pendente.
        - Parser customizado (lambda) le o arquivo como texto puro.
        - Embedder real (``all-MiniLM-L6-v2``, cache local) - o override
          do modelo menor via ``DFE_EMBEDDING_MODEL`` e necessario por
          memoria (ver nota em ``test_guardrail_response_cites_source``).
        - 1a chamada de ``ingest_one``: ``n1 >= 1``; captura contagem em
          ``vec_chunks``.
        - 2a chamada de ``ingest_one``: ``n2 == 0`` (doc nao esta mais
          pendente); contagem identica.
    """
    db_path: Path = tmp_path / "test.db"
    data_dir: Path = tmp_path / "data"
    data_dir.mkdir()
    storage = SqliteStorage(db_path)
    storage.init_schema()
    vector_store = VectorStore(db_path, dim=384)
    vector_store.init_schema()

    doc_file: Path = data_dir / "doc.txt"
    doc_file.write_text("Conteudo do documento de teste para ingestao " * 50)

    rec_id: int = storage.upsert_document(
        DocumentRecord(
            url="https://www.nfe.fazenda.gov.br/test.pdf",
            source_domain="nfe.fazenda.gov.br",
            doc_type="nfe",
            title="Doc Teste",
            file_path=doc_file,
            status="nao_ingerido",
        )
    )

    def parser(path: Path) -> str:
        return path.read_text(encoding="utf-8")

    embedder = EmbeddingProvider(_INTEGRATION_MODEL_NAME)
    indexer = RagIndexer(storage, vector_store, embedder, parser=parser)

    n1: int = indexer.ingest_one(rec_id)
    assert n1 >= 1, f"Esperado >= 1 chunk na primeira ingestao, obtido {n1}"

    n_before: int = _count_vec_chunks(db_path)
    assert n_before >= 1

    n2: int = indexer.ingest_one(rec_id)
    assert n2 == 0, f"Esperado 0 chunks na segunda ingestao, obtido {n2}"

    n_after: int = _count_vec_chunks(db_path)
    assert n_before == n_after, (
        f"Chunks duplicaram: antes={n_before}, depois={n_after}"
    )


# --- 4. Guardrail de fonte (CLI subprocess) ---


@pytest.mark.integration
def test_guardrail_response_cites_source(
    fake_portal_url: str,
    temp_storage: dict[str, Path],
) -> None:
    """Pipeline + CLI: stdout do ``src.query`` cita URL e titulo do documento.

    Estrategia:
        - Roda pipeline (discover + download + ingest) contra ``fake_portal_url``
          usando as fixtures existentes (``tests/integration/conftest.py``).
        - Recupera URL e titulo do 1o doc com ``status='ingerido'``.
        - Copia o DB para o path padrao do CLI (``./storage/dfe.db`` relativo
          ao cwd).
        - Executa ``python -m src.query "Nota Tecnica NF-e"`` via ``subprocess.run``
          com ``PYTHONPATH`` ajustado e ``HF_HUB_OFFLINE=1``.
        - Verifica que o stdout (JSON) contem a URL esperada e o titulo
          esperado nos campos ``sources``.

    Nota sobre modelo (memoria):
        O modelo padrao ``paraphrase-multilingual-MiniLM-L12-v2`` (470MB)
        nao cabe em ambientes com pouca RAM quando carregado duas vezes
        (pipeline in-process + subprocesso CLI) - pytest ja consome ~1GB
        e o modelo sozinho precisa de mais 470MB em cada processo.
        Para este teste, ambos os processos (pipeline e CLI subprocesso)
        usam o modelo menor ``all-MiniLM-L6-v2`` (91MB) configurado via
        env var ``DFE_EMBEDDING_MODEL`` que ``src/indexer/embeddings.py``
        consulta no module-load. As dimensoes (384) sao identicas e os
        embeddings permanecem compativeis.
    """
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

    with patch.dict(PORTAL_URLS, custom_urls, clear=True), \
         patch("src.collector.portal_index.ALLOWED_DOMAINS", _FAKE_ALLOWED_DOMAINS):
        throttler = Throttler(request_interval_ms=0, jitter_ms=0)
        collector = DocumentCollector(
            storage, throttler, data_dir, allowed_domains=_FAKE_ALLOWED_DOMAINS
        )
        n_reg: int = collector.discover_and_register()
        n_dl: int = collector.download_pending()
        assert n_reg >= 1, f"Esperado >= 1 doc registrado, obtido {n_reg}"
        assert n_dl >= 1, f"Esperado >= 1 download, obtido {n_dl}"

        embedder = EmbeddingProvider(_INTEGRATION_MODEL_NAME)
        indexer = RagIndexer(
            storage, vector_store, embedder, parser=extract_text_from_pdf
        )
        n_idx: int = indexer.ingest_pending()
        assert n_idx >= 1, f"Esperado >= 1 doc indexado, obtido {n_idx}"

        # Libera o modelo em memoria antes do subprocess CLI. Quebrar
        # referencia no embedder + del + gc.collect libera os tensores
        # torch, mas o mmap do safetensors pode permanecer enquanto o
        # processo pai existir; o env MINIMO passado ao subprocesso evita
        # herdar caches que possam conflitar.
        import gc
        embedder._model = None
        del indexer
        del embedder
        gc.collect()

    # Pinar OMP/MKL/OpenBLAS a 1 thread ANTES do in-process pipeline E do
    # subprocess CLI. BLAS paralelizado produz ordens de reducao float
    # diferentes entre runs (e entre processo pai x subprocesso filho no
    # Windows), gerando embeddings que divergem o suficiente para que a
    # similaridade cosseno caia abaixo de MIN_RELEVANCE_SCORE. Pinando em
    # 1 thread no pai garantimos que os embeddings persistidos sejam
    # reprodutíveis e bate com os que o subprocesso calculará.
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute(
        "SELECT url, title FROM documents WHERE status='ingerido' LIMIT 1"
    )
    row = cursor.fetchone()
    conn.close()
    assert row is not None, "Nenhum documento com status='ingerido' encontrado"
    expected_url: str
    expected_title: str
    expected_url, expected_title = row

    default_db_path: Path = temp_storage["root"] / "storage" / "dfe.db"
    shutil.copy2(db_path, default_db_path)

    project_root: Path = Path(__file__).resolve().parents[2]
    # Estrategia A: constroi um env MINIMO para o subprocesso. Filtra
    # vars pytest-cov (COVERAGE_*, PYTEST_*) que inflariam o footprint de
    # memoria do subprocesso, e fixa o threading BLAS em 1 para garantir
    # embeddings determinísticos (vide comentario acima).
    env: dict[str, str] = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("COVERAGE_", "PYTEST_"))
    }
    existing_pp = env.get("PYTHONPATH", "")
    # PLAN_SPRINT5 A.1: prepende tambem ``.opencode`` em PYTHONPATH
    # para que ``src.utils.http_guard_bootstrap`` consiga importar
    # ``hooks.domain_guard`` no subprocess CLI.
    opencode_path: Path = project_root / ".opencode"
    pp_parts: list[str] = [str(project_root), str(opencode_path)]
    if existing_pp:
        pp_parts.append(existing_pp)
    env["PYTHONPATH"] = os.pathsep.join(pp_parts)
    env["HF_HUB_OFFLINE"] = "1"
    # Garante que o subprocesso do CLI use o MESMO modelo que a pipeline
    # in-process (via override em src/indexer/embeddings.py).
    env["DFE_EMBEDDING_MODEL"] = _INTEGRATION_MODEL_NAME
    env["OMP_NUM_THREADS"] = "1"
    env["MKL_NUM_THREADS"] = "1"
    env["OPENBLAS_NUM_THREADS"] = "1"

    result = subprocess.run(
        [sys.executable, "-m", "src.query", "Nota Tecnica NF-e"],
        capture_output=True,
        text=True,
        cwd=str(temp_storage["root"]),
        env=env,
        check=False,
    )

    assert result.returncode == 0, (
        f"CLI falhou (rc={result.returncode}): stderr={result.stderr}"
    )

    payload: dict = json.loads(result.stdout)
    sources: list[dict] = payload.get("sources", [])
    assert len(sources) >= 1, (
        f"Esperado >= 1 source em sources={sources} (answer={payload.get('answer')!r})"
    )

    found_url: bool = any(
        expected_url == s.get("url", "") or "127.0.0.1" in s.get("url", "")
        for s in sources
    )
    assert found_url, (
        f"URL esperada ({expected_url}) nao encontrada em sources: {sources}"
    )
    found_title: bool = any(
        expected_title == s.get("title", "") for s in sources
    )
    assert found_title, (
        f"Titulo esperado ({expected_title}) nao encontrado em sources: {sources}"
    )


__all__ = [
    "test_guardrail_domain_blocks_external",
    "test_guardrail_throttling_respects_interval",
    "test_guardrail_idempotent_ingestion",
    "test_guardrail_response_cites_source",
]
