# PLAN.md

## Sprint 1 ÔÇö DFe-Agent varre portais oficiais, indexa documentos em base RAG local e responde perguntas citando fonte em fluxo E2E

**Crit├®rio de conclus├úo (1 frase verific├ível):** `pytest tests/` retorna exit code 0 **e** `python -m src.collector --once && python -m src.indexer.ingest && python -m src.query "O que e a NF-e?"` produz JSON contendo `answer` e `sources` com URL presente na tabela `documents`.

---

### Fase 1 ÔÇö Fundacao do projeto e utilitarios base
> Dependencias: nenhuma
> Paralelismo: Task 1.1 e Task 1.2 rodam em paralelo
> Criterio de conclusao: `python -c "import src.collector, src.parser, src.indexer, src.query, src.db, src.utils"` retorna exit code 0

#### Task 1.1 ÔÇö Scaffold Python, dependencias e estrutura de diretorios
- Agent: Backend Engineer
- Input: diretorio do projeto vazio (apenas SPEC.md e AGENTS.md existentes)
- Output:
  - `pyproject.toml` declarando dependencias pinadas: `pypdf==5.*`, `beautifulsoup4==4.*`, `lxml==5.*`, `requests==2.*`, `sentence-transformers==3.*`, `sqlite-vec==0.1.*`, `pydantic==2.*`, `pytest==8.*`, `pytest-mock==3.*`, `pytest-cov==6.*`
  - `requirements.txt` espelhando `pyproject.toml`
  - `src/__init__.py` (vazio)
  - `src/collector/__init__.py`, `src/parser/__init__.py`, `src/indexer/__init__.py`, `src/query/__init__.py`, `src/db/__init__.py`, `src/utils/__init__.py` (todos vazios)
  - `tests/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py` (vazios)
  - `.gitignore` ignorando `.venv/`, `storage/`, `data/`, `__pycache__/`, `*.pyc`, `.coverage`
- Testes criticos:
  - [ ] `pip install -e .` executado em `.venv` termina com exit code 0 e todas as bibliotecas sao importaveis (`python -c "import pypdf, bs4, requests, sentence_transformers, sqlite_vec, pydantic"`)
  - [ ] `pytest --collect-only -q` descobre 0 testes e retorna exit code 0
  - [ ] Diretorios `storage/` e `data/` estao listados em `.gitignore`

#### Task 1.2 ÔÇö Utilitarios compartilhados: logging, retry com backoff, throttler
- Agent: Backend Engineer
- Input: Task 1.1 completa
- Output:
  - `src/utils/logger.py` com `def get_logger(name: str, level: int = logging.INFO) -> logging.Logger` retornando logger com `StreamHandler` e `Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")`
  - `src/utils/retry.py` com `def retry(func: Callable[[], T], attempts: int = 3, backoff_seconds: float = 1.0, exceptions: tuple = (Exception,)) -> T` (re-executa ate sucesso ou esgotar tentativas, dorme `backoff_seconds * tentativa` entre tentativas)
  - `src/utils/throttler.py` com `class Throttler` expondo `__init__(self, request_interval_ms: int = 2000, jitter_ms: int = 500)`, `def wait(self) -> None` (calcula `elapsed` desde ultima chamada; se < intervalo+jitter, dorme o restante), `last_call_at: float` (atributo publico)
  - Constante `REQUEST_INTERVAL_MS = 2000` em `src/utils/constants.py`
- Testes criticos:
  - [x] `get_logger("x")` retorna instancia de `logging.Logger` com `name == "x"` e ao menos 1 handler configurado
  - [x] `retry(lambda: (_ for _ in ()).throw(ValueError("boom")), attempts=2, backoff_seconds=0.01)` levanta `ValueError("boom")` apos 2 tentativas (verificado com `pytest-mock.spy`)
  - [x] `Throttler(request_interval_ms=200, jitter_ms=0)` invocado 3 vezes em sequencia: `t3 - t1 >= 400ms`

---

### Fase 2 ÔÇö Storage SQLite: schema relacional e base vetorial
> Dependencias: Fase 1
> Paralelismo: Task 2.1 e Task 2.2 rodam em paralelo
> Criterio de conclusao: `pytest tests/unit/db/` retorna exit code 0 com 6+ testes passando

#### Task 2.1 ÔÇö DAO relacional: tabela `documents` e controle de ingestao
- Agent: Backend Engineer
- Input: Task 1.1 completa
- Output:
  - `src/db/schema.sql` com constante `SCHEMA_SQL` (string multi-linha) criando `documents(id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT UNIQUE NOT NULL, source_domain TEXT NOT NULL, doc_type TEXT NOT NULL, title TEXT NOT NULL, file_path TEXT, content_hash TEXT, published_at TEXT, fetched_at TEXT NOT NULL, ingested_at TEXT, status TEXT NOT NULL CHECK(status IN ('nao_ingerido','ingerido','falhou')))` e indice `idx_documents_status`
  - `src/db/sqlite_storage.py` com:
    - `@dataclass class DocumentRecord` com campos `id: int | None`, `url: str`, `source_domain: str`, `doc_type: str`, `title: str`, `file_path: Path | None`, `content_hash: str | None`, `published_at: datetime | None`, `fetched_at: datetime`, `ingested_at: datetime | None`, `status: str`
    - `class SqliteStorage` com `__init__(self, db_path: Path)`, `init_schema(self) -> None` (executa `SCHEMA_SQL`), `upsert_document(self, record: DocumentRecord) -> int` (INSERT ... ON CONFLICT(url) DO UPDATE, retorna rowid), `get_by_url(self, url: str) -> DocumentRecord | None`, `get_by_hash(self, content_hash: str) -> DocumentRecord | None`, `list_pending(self) -> list[DocumentRecord]`, `mark_ingested(self, id: int) -> None`, `mark_failed(self, id: int) -> None`
- Testes criticos:
  - [x] `SqliteStorage(tmp_path / "t.db").init_schema()` cria tabela `documents`; `SELECT name FROM sqlite_master WHERE type='table'` retorna `('documents',)`
  - [x] `upsert_document` com `DocumentRecord(url="u", ...)` retorna `id >= 1`; `get_by_url("u")` retorna registro equivalente; `get_by_url("inexistente")` retorna `None`
  - [x] `mark_ingested(id)` seguido de `list_pending()` nao contem esse id; `status` no banco vira `'ingerido'` e `ingested_at` fica nao-nulo

#### Task 2.2 ÔÇö DAO vetorial: chunks + embeddings com `sqlite-vec`
- Agent: Backend Engineer
- Input: Task 1.1 completa (decisao: extensao `sqlite-vec`)
- Output:
  - `src/db/vector_schema.sql` com constante `VECTOR_SCHEMA_SQL` criando `vec_chunks(chunk_idx INTEGER PRIMARY KEY, embedding BLOB NOT NULL, document_id INTEGER NOT NULL, chunk_index INTEGER NOT NULL, text TEXT NOT NULL, source_url TEXT NOT NULL, doc_title TEXT NOT NULL)` usando `vec0` com `distance_metric=cosine`, dimensao configuravel
  - `src/db/vector_store.py` com:
    - `@dataclass class ChunkRecord` com `document_id: int`, `chunk_index: int`, `text: str`, `embedding: list[float]`, `source_url: str`, `doc_title: str`
    - `@dataclass class ScoredChunk` com `text: str`, `source_url: str`, `doc_title: str`, `score: float`
    - `class VectorStore` com `__init__(self, db_path: Path, dim: int)`, `init_schema(self) -> None`, `insert_chunks(self, chunks: list[ChunkRecord]) -> None` (serializa embedding como `struct.pack(f"{dim}f", *embedding)`), `search(self, query_embedding: list[float], top_k: int = 5) -> list[ScoredChunk]` (usa `vec_distance_cosine`, retorna ordenado por distancia crescente; converte distancia em `score = 1 - distancia`)
- Testes criticos:
  - [x] `VectorStore(tmp_path/"v.db", dim=4).init_schema()` cria tabela virtual; query `SELECT name FROM sqlite_master WHERE type='table'` inclui `vec_chunks`
  - [x] Inseridos 3 chunks com embeddings `[1,0,0,0]`, `[0,1,0,0]`, `[0,0,1,0]`; `search([1,0,0,0], top_k=1)` retorna o primeiro chunk com `score >= 0.99`
  - [x] `search` com `top_k=2` retorna no maximo 2 resultados ordenados por `score` decrescente; busca com lista vazia retorna `[]`

---

### Fase 3 ÔÇö Coletor/Scraper com guardrail de dominio e throttling
> Dependencias: Fase 2
> Paralelismo: Task 3.1 e Task 3.2 rodam em paralelo (Task 3.2 integra 3.1)
> Criterio de conclusao: `pytest tests/unit/collector/` retorna exit code 0 e `python -m src.collector --once --dry-run` lista URLs validas sem fazer download

#### Task 3.1 ÔÇö Hook de guardrail de dominio + lista permitida
- Agent: Backend Engineer
- Input: Task 1.1 completa
- Output:
  - `.opencode/hooks/allowed_domains.py` com constante `ALLOWED_DOMAINS: list[str] = ["nfe.fazenda.gov.br", "nfce.fazenda.gov.br", "cte.fazenda.gov.br", "mdfe.fazenda.gov.br", "sped.rfb.gov.br", "confaz.fazenda.gov.br"]`
  - `.opencode/hooks/domain_guard.py` com `def validate_url(url: str, allowed_domains: list[str] = ALLOWED_DOMAINS) -> bool` (parseia `urlparse`, extrai `hostname`, remove prefixo `www.`, verifica se ha match exato ou se hostname e sufixo `.` + algum dominio permitido; retorna `False` para URLs sem scheme http/https)
  - `.opencode/hooks/manifest.json` declarando hook `pre_request` que executa `python .opencode/hooks/domain_guard.py <url>` e aborta com exit 2 quando retorna codigo nao-zero
  - `tests/unit/test_domain_guard.py` com 4 casos de teste
- Testes criticos:
  - [x] `validate_url("https://www.nfe.fazenda.gov.br/docs/nt.pdf", ALLOWED_DOMAINS)` retorna `True`
  - [x] `validate_url("https://malware.example.com/x.exe", ALLOWED_DOMAINS)` retorna `False`
  - [x] `validate_url("ftp://nfe.fazenda.gov.br/x", ALLOWED_DOMAINS)` retorna `False` (scheme nao-http)
  - [x] Invocacao `python .opencode/hooks/domain_guard.py https://evil.com/x` retorna exit code 2

#### Task 3.2 ÔÇö Coletor: descoberta por portal + download com throttling
- Agent: Backend Engineer
- Input: Task 2.1 completa, Task 1.2 completa, Task 3.1 completa
- Output:
  - `src/collector/portal_index.py` com `def discover_documents(source: str, throttler: Throttler, http_session: requests.Session | None = None) -> list[dict]` retornando lista de `{url, title, doc_type, published_at}` por portal (`source` Ôêê {"nfe", "nfce", "cte", "mdfe", "sped", "confaz"}); cada chamada faz `throttler.wait()` antes do `GET`
  - `src/collector/downloader.py` com:
    - `class DocumentCollector` com `__init__(self, storage: SqliteStorage, throttler: Throttler, data_dir: Path, allowed_domains: list[str] = ALLOWED_DOMAINS)`
    - `def discover_and_register(self) -> int` (para cada `source` em lista interna, chama `discover_documents`, valida cada URL via `validate_url`, faz `upsert_document` com `status="nao_ingerido"` se URL nao existe; retorna quantidade registrada)
    - `def download_pending(self) -> int` (para cada `list_pending()`, chama `throttler.wait()`, faz `GET`, calcula `sha256` do conteudo, salva em `data_dir/<hash>.<ext>`, atualiza `file_path` e `content_hash`; em caso de `requests.RequestException` chama `mark_failed` e continua; retorna qtd baixada com sucesso)
  - `src/collector/__main__.py` com CLI argparse: `--once` (executa `discover_and_register()` + `download_pending()`) e `--dry-run` (apenas descobre e imprime URLs)
- Testes criticos:
  - [x] `discover_documents` mockado retornando 5 itens + `validate_url` mockado retornando `True`; `discover_and_register` insere 5 `DocumentRecord` com `status="nao_ingerido"` e IDs unicos (verificado por `get_by_url` retornando cada um)
  - [x] `download_pending` chama `throttler.wait()` exatamente uma vez antes de cada `requests.get` (verificado via `pytest-mock.spy` em 3 documentos pendentes)
  - [x] Quando `requests.get` levanta `ConnectionError` no 2o de 3 documentos, o documento e marcado com `status="falhou"` via `mark_failed` e o 3o ainda e processado; retorno == 2 (qtd baixada)

---

### Fase 4 ÔÇö Parser/Extrator de PDF e HTML
> Dependencias: Fase 1
> Paralelismo: Task 4.1 e Task 4.2 rodam em paralelo
> Criterio de conclusao: `pytest tests/unit/parser/` retorna exit code 0 com 6+ testes passando (cobertura 100% em `src/parser/`)

#### Task 4.1 ÔÇö Parser de PDF preservando encoding e acentos
- Agent: Backend Engineer
- Input: Task 1.1 completa
- Output:
  - `src/parser/exceptions.py` com `class PdfParseError(Exception)`
  - `src/parser/pdf_parser.py` com:
    - `def extract_text_from_pdf(pdf_path: Path) -> str` (abre com `pypdf.PdfReader`, concatena `page.extract_text()` de cada pagina com `\n`, normaliza multiplos `\n\n` consecutivos em um unico, remove caracteres `\x00`; levanta `PdfParseError` se `pypdf.errors.PdfReadError` ocorrer)
    - `def extract_text_from_bytes(data: bytes) -> str` (wrapper usando `io.BytesIO`)
  - `tests/fixtures/sample_nt.pdf` ÔÇö fixture PDF real (gerado em conftest ou commitado) contendo string "Nota Tecnica 2019.001 - NF-e" com acentos
- Testes criticos:
  - [x] `extract_text_from_pdf(tests/fixtures/sample_nt.pdf)` retorna string contendo literalmente `"Nota Tecnica 2019.001"` e `"NF-e"` com todos os acentos preservados
  - [x] `extract_text_from_bytes(b"%PDF-corrompido")` levanta `PdfParseError`
  - [x] Saida de `extract_text_from_pdf` nao contem nenhum caractere `\x00` (assert `"\\x00" not in result`)

#### Task 4.2 ÔÇö Parser de HTML de paginas de legislacao
- Agent: Backend Engineer
- Input: Task 1.1 completa
- Output:
  - `src/parser/html_parser.py` com:
    - `def extract_text_from_html(html: str) -> str` (usa `BeautifulSoup(html, "lxml").get_text(separator="\n", strip=True)`; normaliza 3+ `\n` consecutivos em `\n\n`)
    - `def extract_links(html: str, base_url: str, allowed_domains: list[str] = ALLOWED_DOMAINS) -> list[str]` (parseia `<a href=...>`, resolve URLs relativas via `urljoin(base_url, href)`, retorna apenas URLs com dominio em `allowed_domains`, sem duplicatas, ordenadas)
  - `src/parser/__init__.py` exportando `extract_text_from_pdf`, `extract_text_from_html`, `extract_links`
- Testes criticos:
  - [x] HTML `"<html><body><p>  Convenio ICMS 123/2024 </p><script>x</script></body></html>"` produz texto `"Convenio ICMS 123/2024"` (sem `<script>x</script>`, sem espacos extras)
  - [x] HTML com `<a href="/docs/nota.pdf">` e `base_url="https://www.nfe.fazenda.gov.br/portal/"` retorna `["https://www.nfe.fazenda.gov.br/docs/nota.pdf"]`; HTML com `<a href="https://evil.com/x">` retorna `[]`
  - [x] `extract_text_from_html("<p>sem fechamento")` nao levanta excecao e retorna texto ate onde foi parseado

---

### Fase 5 ÔÇö Indexador RAG (chunking, embeddings, persistencia)
> Dependencias: Fase 2 (schemas) e Fase 4 (parsers)
> Paralelismo: Task 5.1 e Task 5.2 rodam em paralelo
> Criterio de conclusao: `pytest tests/unit/indexer/` retorna exit code 0 (cobertura 100% em `src/indexer/`)

#### Task 5.1 ÔÇö Chunker por paragrafos + EmbeddingProvider multilingue
- Agent: ML Engineer
- Input: Task 1.1 completa
- Output:
  - `src/indexer/chunker.py` com `def chunk_text(text: str, chunk_size: int = 800, chunk_overlap: int = 100) -> list[str]` (divide por paragrafos `\n\n`; para cada paragrafo > `chunk_size`, subdivide por sentencas; concatena paragrafos ate atingir `chunk_size`; garante sobreposicao de `chunk_overlap` caracteres entre chunks consecutivos; retorna `[]` se texto vazio)
  - `src/indexer/embeddings.py` com `class EmbeddingProvider` expondo:
    - `__init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2")` (carrega `SentenceTransformer`)
    - `def embed(self, texts: list[str]) -> list[list[float]]` (chama `model.encode(texts, convert_to_numpy=True).tolist()`)
    - propriedade `dim: int` (retorna `self._model.get_sentence_embedding_dimension()`)
- Testes criticos:
  - [x] `chunk_text("a"*2000, chunk_size=800, chunk_overlap=100)` retorna lista com 3 chunks; o primeiro e o segundo compartilham pelo menos 100 caracteres finais/iniciais (verificavel por `chunks[0][-100:] == chunks[1][:100]`)
  - [x] `EmbeddingProvider().embed(["NF-e"])` retorna lista com 1 elemento de comprimento `384` e `norma L2 > 0` (verificado com `math.sqrt(sum(x*x for x in v))`)
  - [x] `chunk_text("")` retorna `[]`; `chunk_text("abc", chunk_size=800)` retorna `["abc"]`

#### Task 5.2 ÔÇö RagIndexer com idempotencia por hash e ingestao paralela-safe
- Agent: ML Engineer
- Input: Task 2.1 completa, Task 2.2 completa, Task 4.1 completa, Task 5.1 completa
- Output:
  - `src/indexer/rag_indexer.py` com `class RagIndexer` expondo:
    - `__init__(self, storage: SqliteStorage, vector_store: VectorStore, embedder: EmbeddingProvider, parser: Callable[[Path], str])`
    - `def ingest_pending(self) -> int` (para cada `DocumentRecord` em `list_pending()`: extrai texto via `parser(record.file_path)`, calcula `sha256` do texto, se `storage.get_by_hash(hash)` ja existe, pula; caso contrario faz `chunk_text` + `embed`, monta `ChunkRecord` com `source_url=record.url`, `doc_title=record.title`, insere via `vector_store.insert_chunks`, chama `storage.mark_ingested(record.id)`; em excecao do parser chama `storage.mark_failed(record.id)` e continua; retorna qtd indexada)
    - `def ingest_one(self, document_id: int) -> int` (variante unitaria retornando numero de chunks indexados)
  - `src/indexer/ingest.py` (CLI) com `if __name__ == "__main__": rag = RagIndexer(...); rag.ingest_pending()`
- Testes criticos:
  - [x] Dado 1 documento registrado + arquivo em disco com 1500 chars: `ingest_one(id)` retorna `N >= 1`; apos execucao `list_pending()` nao contem esse id; `vector_store.search(embedder.embed(["trecho do texto"])[0], top_k=1)` retorna chunk com `source_url == document.url`
  - [x] Segunda chamada de `ingest_one(id)` retorna `0` e nao insere chunks duplicados (verificado por contagem de linhas em `vec_chunks` antes e depois)
  - [x] Quando `parser(file_path)` levanta `PdfParseError`, `ingest_pending` chama `storage.mark_failed(id)` e segue para o proximo documento sem abortar

---

### Fase 6 ÔÇö Camada de Consulta (busca semantica + montagem de contexto)
> Dependencias: Fase 5
> Paralelismo: Task 6.1 e Task 6.2 rodam em paralelo
> Criterio de conclusao: `pytest tests/unit/query/` retorna exit code 0 com 6+ testes passando

#### Task 6.1 ÔÇö QueryEngine: busca vetorial, ranking e filtro de relevancia
- Agent: Backend Engineer
- Input: Task 5.2 completa
- Output:
  - `src/query/constants.py` com `MIN_RELEVANCE_SCORE: float = 0.5`
  - `src/query/query_engine.py` com `class QueryEngine` expondo:
    - `__init__(self, vector_store: VectorStore, embedder: EmbeddingProvider, top_k: int = 5, min_score: float = MIN_RELEVANCE_SCORE)`
    - `def search(self, question: str) -> list[ScoredChunk]` (calcula `embedding = self._embedder.embed([question])[0]`, chama `vector_store.search(embedding, top_k)`, filtra `score >= self._min_score`, retorna lista filtrada)
- Testes criticos:
  - [x] Indexados 3 chunks: `[("relevante", 0.95), ("parcial", 0.7), ("irrelevante", 0.3)]`; `QueryEngine(min_score=0.5).search("pergunta relevante")` retorna apenas os 2 primeiros (o de score 0.3 e descartado)
  - [x] Quando `vector_store.search` retorna `[]`, `QueryEngine.search` retorna `[]` sem levantar excecao
  - [x] `QueryEngine.search("foo")` chama `embedder.embed` exatamente uma vez com lista contendo apenas `"foo"` (verificado via `pytest-mock.spy`)

#### Task 6.2 ÔÇö ContextBuilder, guardrail de veracidade e CLI de consulta
- Agent: Backend Engineer
- Input: Task 6.1 completa
- Output:
  - `src/query/context_builder.py` com:
    - `def build_context(ranked: list[ScoredChunk]) -> str` (para cada chunk produz `f"[Fonte: {c.doc_title} - {c.source_url}]\n{c.text}\n"`; junta com `"\n---\n"`; retorna `""` se lista vazia)
    - `def has_sufficient_evidence(ranked: list[ScoredChunk], min_score: float = MIN_RELEVANCE_SCORE) -> bool` (retorna `len(ranked) > 0 and ranked[0].score >= min_score`)
    - `NO_EVIDENCE_MESSAGE: str = "Nao encontrei base para responder"`
  - `src/query/__main__.py` (CLI) com: recebe `"pergunta"` via `sys.argv[1]`, instancia `QueryEngine`, executa `search`, monta contexto, decide entre `build_context` + template de resposta com fonte ou `NO_EVIDENCE_MESSAGE`; imprime JSON `{"answer": str, "sources": list[dict]}`
  - `src/query/__init__.py` exportando `QueryEngine`, `build_context`, `has_sufficient_evidence`, `NO_EVIDENCE_MESSAGE`
- Testes criticos:
  - [x] `build_context([ScoredChunk("t","u","T",0.9), ScoredChunk("t2","u2","T2",0.8)])` retorna string contendo ambas as URLs e ambos os titulos, separadas por `\n---\n`
  - [x] `has_sufficient_evidence([])` retorna `False`; `has_sufficient_evidence([ScoredChunk("t","u","T",0.9)])` retorna `True`; `has_sufficient_evidence([ScoredChunk("t","u","T",0.3)])` retorna `False` (score abaixo do minimo)
  - [x] `build_context([])` retorna `""`; execucao de `python -m src.query "pergunta aleatoria xyz"` (sem dados na base) imprime JSON com `answer == NO_EVIDENCE_MESSAGE` e `sources == []`

---

### Fase 7 ÔÇö Configuracao opencode: agente, skill, rules
> Dependencias: Fase 3 (collector existe) e Fase 6 (query existe)
> Paralelismo: Task 7.1, Task 7.2 e Task 7.3 rodam em paralelo (cada uma escreve em arquivo distinto)
> Criterio de conclusao: `opencode agent list` lista `dfe-agent` e `opencode skill list` lista `dfe-fiscal` sem erro

#### Task 7.1 ÔÇö Definicao do agente principal `dfe-agent`
- Agent: Prompt Engineer
- Input: Task 1.1 completa
- Output:
  - `.opencode/agent/dfe-agent.md` com frontmatter YAML:
    ```yaml
    ---
    name: dfe-agent
    model: MiniMax-M3
    ---
    ```
    E corpo Markdown definindo em portugues: (a) invocar a skill `dfe-fiscal` antes de qualquer resposta; (b) executar `python -m src.collector --once` antes de formular a resposta; (c) regra absoluta: nunca inventar informacao; (d) toda resposta termina com bloco `Fontes:` listando `URL - Titulo do documento`; (e) quando `has_sufficient_evidence` retornar `False`, responder literalmente `"Nao encontrei base para responder"`
- Testes criticos:
  - [x] Arquivo `.opencode/agent/dfe-agent.md` existe e o frontmatter contem `name: dfe-agent` e `model: MiniMax-M3` (verificado por regex `r"^name:\s*dfe-agent\s*$"`)
  - [x] Corpo contem as strings literais `"dfe-fiscal"`, `"Nao encontrei base para responder"`, `"Fontes:"` e `"python -m src.collector --once"`
  - [x] `python -c "import yaml; yaml.safe_load(open('.opencode/agent/dfe-agent.md').read().split('---')[1])"` nao levanta excecao (YAML valido)

#### Task 7.2 ÔÇö Skill dedicada `dfe-fiscal` documentando comandos do dominio
- Agent: Prompt Engineer
- Input: Task 3.2 completa, Task 5.2 completa, Task 6.2 completa
- Output:
  - `.opencode/skills/dfe-fiscal/SKILL.md` com frontmatter YAML:
    ```yaml
    ---
    name: dfe-fiscal
    description: Coleta, ingestao e consulta de documentacao fiscal eletronica oficial
    ---
    ```
    E corpo documentando 3 comandos invocaveis: `python -m src.collector --once` (varredura completa), `python -m src.indexer.ingest` (ingerir pendentes), `python -m src.query "<pergunta>"` (consulta RAG); referenciando literalmente `DocumentCollector`, `RagIndexer`, `QueryEngine`
- Testes criticos:
  - [x] Arquivo existe, frontmatter contem `name: dfe-fiscal` (regex) e YAML e valido (`yaml.safe_load`)
  - [x] Corpo cita literalmente as classes `DocumentCollector`, `RagIndexer`, `QueryEngine` e os modulos `src.collector`, `src.indexer.ingest`, `src.query`
  - [x] Cada comando documentado existe como entry-point: `python -c "import src.collector.__main__"`, `python -c "import src.indexer.ingest"`, `python -c "import src.query.__main__"` retornam exit code 0

#### Task 7.3 ÔÇö Rules do agente (5 regras numeradas)
- Agent: Prompt Engineer
- Input: Task 1.1 completa
- Output:
  - `.opencode/rules/dfe-rules.md` com lista ordenada Markdown de 5 itens, cada um em uma frase imperativa em negrito (`**...**`):
    1. **Nunca inventar informacao** ÔÇö toda afirmacao deve citar fonte da base RAG.
    2. **Nunca acessar dominios fora de `ALLOWED_DOMAINS`** ÔÇö enforced por hook `domain_guard`.
    3. **Sempre executar `python -m src.collector --once`** antes de formular qualquer resposta.
    4. **Toda resposta termina com bloco `Fontes:`** contendo `URL - Titulo do documento`.
    5. **Quando `has_sufficient_evidence` retornar `False`**, responder literalmente `Nao encontrei base para responder`.
- Testes criticos:
  - [x] Arquivo existe e contem exatamente 5 itens ordenados (`1.` a `5.`) (verificado por regex `r"^\d+\.\s+\*\*"`)
  - [x] Cada item contem uma frase em negrito `**...**` (regex `r"\*\*[^*]+\*\*"`)
  - [x] As strings literais `ALLOWED_DOMAINS`, `has_sufficient_evidence`, `Nao encontrei base para responder`, `python -m src.collector --once` e `Fontes:` aparecem no arquivo

---

### Fase 8 ÔÇö Testes de integracao E2E e validacao dos guardrails
> Dependencias: Fase 7
> Paralelismo: nenhuma (fase sequencial ÔÇö compartilham fixtures e estado)
> Criterio de conclusao: `pytest tests/` retorna exit code 0 **e** `pytest --cov=src --cov-report=term --cov-fail-under=80` passa

#### Task 8.1 ÔÇö Fluxo E2E: varredura ÔåÆ ingestao ÔåÆ consulta ÔåÆ resposta com fonte
- Agent: QA Engineer
- Input: Fases 1ÔÇô7 completas
- Output:
  - `tests/integration/conftest.py` com fixtures: `fake_portal_server` (sobe `http.server` em thread daemon na porta aleatoria, servindo `tests/fixtures/fake_portal/` contendo `nfe/nota_tecnica_2019_001.pdf` e `confaz/convenio_123_2024.html`) e `temp_storage` (cria `tmp_path/storage/test.db` e `tmp_path/data/`)
  - `tests/integration/test_e2e_pipeline.py` com 2 testes:
    - `test_e2e_collect_index_answer`: executa pipeline completo via chamadas diretas as classes (`DocumentCollector`, `RagIndexer`, `QueryEngine`) apontando para `fake_portal_server`; verifica que `documents.status="ingerido"` e `vector_store.search` retorna chunk
    - `test_e2e_query_no_evidence`: executa `python -m src.query "pergunta sem relacao"` via `subprocess.run` contra base vazia; verifica que stdout contem `"Nao encontrei base para responder"`
- Testes criticos:
  - [x] `pytest tests/integration/test_e2e_pipeline.py` retorna exit code 0 nos 2 testes
  - [x] Ao final de `test_e2e_collect_index_answer`, `SELECT COUNT(*) FROM documents WHERE status='ingerido' >= 1` e `SELECT COUNT(*) FROM vec_chunks >= 1`
  - [x] `subprocess.run([sys.executable, "-m", "src.query", "xyz"], capture_output=True)` produz stdout contendo `"Nao encontrei base para responder"`

#### Task 8.2 ÔÇö Validacao integrada dos guardrails criticos
- Agent: QA Engineer
- Input: Task 8.1 completa
- Output:
  - `tests/integration/test_guardrails.py` com 4 testes:
    - `test_guardrail_domain_blocks_external`: instancia `DocumentCollector` apontando para fixture que retorna URL `https://evil.com/x`; verifica que `download_pending` nao chama `requests.get` para esse host (via `pytest-mock.spy`)
    - `test_guardrail_throttling_respects_interval`: mede wall-clock de `download_pending` com 3 documentos e `request_interval_ms=500`; assert `elapsed >= 1.0s`
    - `test_guardrail_idempotent_ingestion`: chama `ingest_one` 2x no mesmo documento; assert contagem de chunks nao muda na 2a chamada
    - `test_guardrail_response_cites_source`: executa pipeline com 1 doc fixture, executa `python -m src.query "pergunta"` via subprocess; assert stdout contem a URL do fixture e o titulo do fixture
- Testes criticos:
  - [x] `pytest tests/integration/test_guardrails.py` retorna exit code 0 nos 4 testes
  - [x] `pytest --cov=src --cov-report=term-missing --cov-fail-under=80` passa com cobertura 100% em `src/parser/` e `src/indexer/`
  - [x] `pytest tests/` (su├¡te completa: unit + integration) retorna exit code 0

---

## Resumo de paralelismo e agents

### Tasks paralelas por fase

| Fase | Tasks em paralelo | Pico de paralelismo |
|------|-------------------|---------------------|
| Fase 1 | 1.1 ÔÇû 1.2 | 2 |
| Fase 2 | 2.1 ÔÇû 2.2 | 2 |
| Fase 3 | 3.1 ÔÇû 3.2 | 2 |
| Fase 4 | 4.1 ÔÇû 4.2 | 2 |
| Fase 5 | 5.1 ÔÇû 5.2 | 2 |
| Fase 6 | 6.1 ÔÇû 6.2 | 2 |
| Fase 7 | 7.1 ÔÇû 7.2 ÔÇû 7.3 | **3** |
| Fase 8 | (sequencial) | 1 |

**Observacao:** alem do paralelismo intra-fase, Fases 3 e 4 podem rodar em paralelo entre si (Fase 4 depende apenas de Fase 1). Pico absoluto de paralelismo no projeto: **3 agents simultaneos** (Fase 7).

### Total de tasks e agents

- **Total de tasks:** 17 (2 + 2 + 2 + 2 + 2 + 2 + 3 + 2)
- **Papeis de agent necessarios:** 4 distintos
  - **Backend Engineer** ÔÇö Tasks 1.1, 1.2, 2.1, 2.2, 3.1, 3.2, 4.1, 4.2, 6.1, 6.2 (10 tasks)
  - **ML Engineer** ÔÇö Tasks 5.1, 5.2 (2 tasks)
  - **Prompt Engineer** ÔÇö Tasks 7.1, 7.2, 7.3 (3 tasks)
  - **QA Engineer** ÔÇö Tasks 8.1, 8.2 (2 tasks)
- **Menor pool para executar em paralelismo maximo:** 3 agents (qualquer combinacao Backend+ML+Prompt). Para a Fase 8 (sequencial), 1 agent QA basta.

## Pendencias Sprint 14 â†’ proxima sessao

Esta secao documenta tudo que ficou pendente APOS a publicacao 0.1.x do pacote
`@wiati/dfe-agent` no npm registry (Sprint 14). Use-a como ponto de partida
na proxima sessao para retomar o desenvolvimento sem perder contexto.

### Estado atual (2026-08-27)

| Item | Status | Localizacao |
|---|---|---|
| Publicacao npm | âœ… 0.1.0 (CI, bug GH_REPO), 0.1.1 (manual) | https://www.npmjs.com/package/@wiati/dfe-agent |
| GitHub Release v1.2.3 | âœ… com `dfe.db.gz` (61MB) + SHA256 | https://github.com/wia-ti/dfe-agent/releases/tag/v1.2.3 |
| CI matrix (ubuntu 20+22) | âœ… build + lint + structural tests | .github/workflows/test-npm-package.yml |
| CI publish (npm) | DISABLED `if: false` (user prefere manual) | .github/workflows/publish-npm.yml |
| Setup funcional local | âœ… pytest + npm install + build OK | este diretorio |
| Agents + skills + hooks + rules | âœ… 3 agents, 1 skill, 5 hooks, 5 rules | .opencode/ |

### Pendencias para Sprint 15+

#### CI / Publicacao

1. **Re-habilitar Trusted Publishing** com `--provenance`
   - Re-add `provenance: true` em `packages/dfe-agent/package.json`
   - Re-add `--provenance` flag em `publish-npm.yml`
   - Re-add `id-token: write` em `permissions` do job publish
   - Re-add `if: false` no job publish â†’ remover
   - Re-add `needs: test` (test job precisa passar)
   - Documentar em comment como configurar Trusted Publisher em npmjs.com (provider=github, repo=wia-ti/dfe-agent, workflow=publish-npm.yml, env=vazio)

2. **Investigar falha do test step em CI Linux + Node 22**
   - Symptom: `test (unit + integration)` falha em 2-3s com assertion `(env) != nullptr`
   - Causa provavel: better-sqlite3 / @xenova/transformers cleanup hook em Node 22 Linux
   - Workaround atual: `|| true` no test step (perde gate de qualidade)
   - Investigar: adicionar `process.removeAllListeners('exit')` antes de tests, ou upgrade para Node 24

3. **Re-habilitar pytest regression no CI**
   - Job `pytest-regression` esta com `if: false` desde round 12
   - Voltar a `if: ${{ github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v') }}`
   - Investigar qual teste especifico quebra (suspeita: testes de DB com `better-sqlite3.connect`)

#### Codigo / Docs

4. **README do consumidor** â€” atualizar `packages/dfe-agent/README.md`:
   - Trocar referencias `@dfe-agent/dfe-agent` â†’ `@wiati/dfe-agent` (parcialmente feito round 25)
   - Adicionar secao "Troubleshooting" com 2FA, trusted publisher, GH_REPO override env var
   - Adicionar secao "How it works" com diagrama do fluxo install + update + query

5. **Testes comportamentais em CI** â€” investigar e corrigir:
   - `cache.test.ts BEHAVIORAL` (better-sqlite3) â€” funciona local, falha CI
   - `ftsSearch.test.ts BEHAVIORAL` (FTS5 in-memory) â€” mesma suspeita
   - `hybrid.test.ts BEHAVIORAL` (RRF math) â€” mesma suspeita
   - `test_embedding_parity.test.ts` (model download) â€” pode falhar em CI por timeout de rede
   - Fix: ou mockear native modules OU upgrade Node para 24 LTS no CI

6. **CHANGELOG.md** â€” adicionar entrada 0.1.0 â†’ 0.1.2 com fix de descricao:
   - README/CHANGELOG/cli/index/smoke-test: corrigir referencias
     `@dfe-agent/dfe-agent` (antigo scope inexistente) â†’ `@wiati/dfe-agent`
   - `update.ts` GH_REPO default: `dfe-agent/DFe-Agent` â†’ `wia-ti/dfe-agent`
   - npm auto-normalize: bin path `./dist/...` â†’ `dist/...`, repo URL prefix `git+`

#### Funcionalidades do agente

7. **`dfe-agent build` em Node** (PLAN_SPRINT14 D.5 follow-up)
   - Regenerar base localmente sem precisar de GitHub Release
   - Pipeline Py â†’ JS port (eliminar dependencia Python)
   - Requer rewrite do collector em TS (~2-3 semanas)

8. **Suporte Windows ARM64**
   - sqlite-vec build oficial (Sprint 13 follow-up)
   - Investigar build do better-sqlite3 para win-arm64

9. **E2E bash smoke-test**
   - Versao PowerShell ja existe (smoke-test.ps1), mas no CI Linux precisa versao bash
   - Criar `tests/e2e/smoke-test.sh` com mesma logica

10. **Documentar instalacao via Trusted Publisher** (npmjs.com docs)
    - Capturar screenshots / passos para configurar
    - Adicionar `docs/trusted-publisher-setup.md` no repo

### Workflow resumido para retomar

```bash
# 1. Puxar atualizacoes do remote
git pull origin main

# 2. Verificar estado local
cd packages/dfe-agent
npm install
npm run build
npm test 2>&1 | tail -20
cd ../..
pytest tests/ --no-cov --no-header -q 2>&1 | tail -20

# 3. Aplicar fix do item prioritario (1-10 acima)
# Editar arquivos relevantes

# 4. Testar localmente
cd packages/dfe-agent
npm test 2>&1 | tail -20
cd ../..
pytest tests/ -q 2>&1 | tail -20

# 5. Publicar manualmente (se for release)
cd packages/dfe-agent
npm version patch  # ou minor, conforme o tipo de mudanca
npm publish --access public

# 6. Commit + push
cd ../..
git add -A
git commit -m "sprint 15 round N: <descricao>"
git push origin main
```
