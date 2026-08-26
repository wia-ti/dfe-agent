# PLAN_SPRINT2.md

> Sprint 2 — RAG profundo para DFe-Agent. Construído sobre Fases 1–8 já concluídas.
> Princípios: TDD (pytest, 100% em `parser/` e `indexer/`, ≥80% global), zero mudanças no contrato CLI, compatibilidade retroativa via migration framework baseado em `PRAGMA user_version`.

```
Fase 9  ──► Fase 10 ──► Fase 11 ──► Fase 12 ──► Fase 13 ──► Fase 14 ──► Fase 15 ──► Fase 16 ──► Fase 17
metadados   chunking     híbrida    hierárquico   cache+      parent       rerank       benchmark    skill+docs
estruturados  estrutural  FTS5+vec   sumário       modelo      retrieval    cross-enc    recall/MRR   CLI/docs
```

---

## Fase 9 — Metadados estruturados indexados
**Dependências:** Fase 2 completa. **Paralelismo:** nenhuma. **Critério:** `pytest tests/unit/db/ tests/unit/parser/ tests/unit/indexer/` exit 0; `get_by_nt_number("2019.001")` retorna 1 doc; `extract_document_metadata` extrai `nt_number` e `published_at`.

### Task 9.1 — Migração aditiva do schema relacional
**Output:**
- `src/db/migrations/__init__.py` (público: `MIGRATIONS_DIR`, `CURRENT_VERSION`).
- `src/db/migrations/0002_doc_metadata.sql` aplicando `ALTER TABLE documents ADD COLUMN IF NOT EXISTS` para `nt_number`, `version`, `replaces_doc_id`, `language` + 3 novos índices (`idx_documents_nt_number`, `idx_documents_doc_type`, `idx_documents_published_at`).
- `src/db/schema.sql` atualizado para v2 (fresh installs ganham schema v2 direto).
- `src/db/schema_sql.py` ganhando `SCHEMA_VERSION: int = 2`.
- `src/db/migrations.py` com `class SchemaMigrations`:
  - `__init__(db_path: Path)`.
  - `current_version() -> int` (lê `PRAGMA user_version`).
  - `apply_pending() -> int` (aplica migrations com versão > current; idempotente via `IF NOT EXISTS`).
- Novas colunas em `DocumentRecord`: `nt_number: str | None`, `version: str | None`, `replaces_doc_id: int | None`, `language: str | None`.
- `_row_to_record` e `upsert_document` estendidos para os novos campos (default `None`).
- `SqliteStorage.init_schema()` agora também chama `SchemaMigrations.apply_pending()` ao final — DBs v1 legados (como o atual `storage/dfe.db`) são migrados transparentemente.
- Novos métodos em `SqliteStorage`:
  - `get_by_nt_number(nt: str) -> DocumentRecord | None`
  - `list_by_doc_type(doc_type: str) -> list[DocumentRecord]`
  - `list_replaced_by(doc_id: int) -> list[DocumentRecord]`

**Testes críticos (`tests/unit/db/test_sqlite_storage_v2.py`, novo, idempotente a Fase 2):**
- Migração v1 → v2 em DB pré-existente adiciona colunas e índices sem perder dados.
- `migrate()` em DB já em v2 é no-op (não duplica índices).
- `migrate()` em DB fresh aplica schema.sql v2 + migrations pendentes.
- `get_by_nt_number("2019.001")` retorna 1 doc; `list_by_doc_type("nota_tecnica")` filtra corretamente; `list_replaced_by(doc_id)` retorna lista.
- `upsert_document` round-trip preservando `nt_number`, `version`, `replaces_doc_id`.

### Task 9.2 — Extrator de metadados a partir do texto
**Output:**
- Novo módulo `src/parser/metadata_extractor.py` com `@dataclass class DocumentMetadata` (campos `nt_number`, `conv_number`, `published_at`, `version`, `language`) e `def extract_document_metadata(text: str, doc_type: str | None = None) -> DocumentMetadata`.
- Heurísticas em PT-BR (regex com tolerância a variações):
  - `r"(?i)nota\s+t[ée]cn[íi]ca\s+(?P<nt>\d{4}\.\d{3})"` → `nt_number`.
  - `r"(?i)conv[êe]nio\s+icms\s+(?P<conv>\d+/\d{4})"` → `conv_number`.
  - `r"(?i)vers[ãa]o\s+(?P<v>\d+(?:\.\d+){0,2})"` → `version`.
  - `r"(?P<day>\d{2})/(?P<month>\d{2})/(?P<year>\d{4})"` → `published_at` (primeira ocorrência nos primeiros 2 KB do texto).
- Sempre retorna `DocumentMetadata` válido — nunca levanta (campos `None` quando ausentes).
- Integração em `RagIndexer._ingest_record`: após extrair texto mas antes de `chunk_text`, chama `extract_document_metadata(text, record.doc_type)`, atribui campos em `record` e chama `storage.upsert_document(record)` ANTES de `mark_ingested` (para persistir metadados em DB).

**Testes críticos (`tests/unit/parser/test_metadata_extractor.py`, novo):**
- `"NOTA TÉCNICA 2019.001 — Assinada em 15/03/2019"` extrai `nt_number="2019.001"`, `published_at=datetime(2019, 3, 15)`.
- `"CONVÊNIO ICMS 123/2024"` extrai `conv_number="123/2024"`.
- `"Versão 3.2 — NT 2020.001"` extrai `version="3.2"`, `nt_number="2020.001"`.
- Texto sem cabeçalho retorna todos campos `None` (sem raise).
- Texto vazio / whitespace-only retorna todos campos `None`.
- Data em posição não-cabeçalho (após 2 KB) é ignorada.

**Testes de integração no RagIndexer (`tests/unit/indexer/test_rag_indexer_metadata.py`):**
- Após `ingest_one` em texto com `"NOTA TÉCNICA 2019.001"`, `get_by_nt_number("2019.001")` retorna o doc com `status="ingerido"`.

---

## Fase 10 — Chunking ciente de estrutura
**Dependências:** Fase 9 (`doc_type`, `nt_number` agora estruturados; útil para logging e métricas; coluna `section_path` introduzida em `vec_chunks`). **Paralelismo:** 10.1 ‖ 10.2. **Critério:** chunk contém prefixo `"§ 1.1 OBJETIVO: ..."` e `section_path` persistido em `vec_chunks`.

### Task 10.1 — Detector de seções + chunker estrutural
**Output:**
- Novo módulo `src/indexer/structural_chunker.py` com `@dataclass class StructuredChunk` (`text: str`, `section_path: str`, `section_level: int`) e `def chunk_structural(text: str, chunk_size: int = 800, chunk_overlap: int = 100) -> list[StructuredChunk]`.
- Heurística regex em PT-BR por linha: `r"^(?P<num>\d+(?:\.\d+){0,2})\s{1,3}(?P<title>[A-ZÁÉÍÓÚÂÊÔÃÕÇ][^\n]{2,80})$"` (cabeçalhos).
- Estratégia: 1) detecta quebras de seção; 2) divide cada bloco em sub-chunks via `chunker.chunk_text` existente; 3) prefixa cada sub-chunk com `f"§ {section_path}: "` se ainda não contiver; 4) `section_level` = profundidade numérica (`1`, `1.1` → 2, `1.1.1` → 3).
- `vector_schema.sql` ganha coluna `section_path TEXT` em `vec_chunks` (idempotente via migration `0003_chunks_section_path.sql`).

**Testes (`tests/unit/indexer/test_structural_chunker.py`):**
- Texto com 3 seções cabeçalho produz chunks com `section_path="1 OBJETIVO"`, `"1.1 Sub"`, `"2 FUNDAMENTAÇÃO"` respectivamente.
- Sub-seção com corpo longo subdivide mantendo `section_path` em todos os chunks.
- Texto sem numeração hierárquica retorna chunks com `section_path=""` (fallback equivalente ao flat).

### Task 10.2 — Adapter no `RagIndexer`
**Output:**
- `RagIndexer.__init__` aceita novo parâmetro `chunker_mode: Literal["flat", "structural"] = "flat"` (default = compat Fase 5).
- Quando `structural`, chama `chunk_structural`; persiste `section_path` em `vec_chunks` (caminho do DDL atualizado para incluir a nova coluna).
- CLI `python -m src.indexer.ingest` ganha flag `--chunker={flat,structural}` (default `flat`).

**Testes (estender `tests/unit/indexer/test_rag_indexer.py`):**
- Rodar com `chunker_mode="structural"` insere `section_path` em `vec_chunks` para a fixture de teste.
- Modo `flat` continua produzindo chunks sem `section_path` (idempotente com Fase 5).

---

## Fase 11 — Busca híbrida FTS5 + sqlite-vec + RRF
**Dependências:** Fase 10. **Paralelismo:** 11.1 ‖ 11.2. **Critério:** query por termo exato ("Convênio ICMS 123/2024") encontra o doc mesmo com embedding de baixa similaridade.

### Task 11.1 — Índice FTS5 espelhado
**Output:**
- Novo módulo `src/db/fts_store.py` com `class FtsStore`:
  - Tabela `fts_chunks(rowid INTEGER PRIMARY KEY, document_id INTEGER, chunk_index INTEGER, text TEXT, source_url TEXT, doc_title TEXT, section_path TEXT)` (sem embedding; espelha metadados de `vec_chunks`).
  - Triggers `fts_chunks_ai`/`ad`/`au` que mantêm `fts_chunks` em sincronia com `vec_chunks` (garante consistência sob deletes futuros da Fase 14).
  - API: `insert_chunks_from_vec()` (carga inicial), `search_fts(query: str, top_k: int = 30) -> list[FtsHit]` usando BM25 (`ORDER BY rank`).
- `@dataclass class FtsHit` (`document_id`, `chunk_index`, `text`, `source_url`, `doc_title`, `bm25_score: float`).

**Testes (`tests/unit/db/test_fts_store.py`):**
- Inserção de N chunks em `vec_chunks` propaga para `fts_chunks` (via trigger `INSERT`).
- `search_fts("Convenio 123/2024")` retorna hits contendo literal "123/2024" mesmo sem embedding próximo.
- `search_fts` com query inexistente retorna `[]`.

### Task 11.2 — Reciprocal Rank Fusion no `QueryEngine`
**Output:**
- `QueryEngine.__init__` aceita `fts_store: FtsStore | None = None` e `rrf_k: int = 60`.
- Novo método `search_hybrid(question: str) -> list[ScoredChunk]` combinando ranking semântico + BM25 via RRF (`score = sum(1/(k+rank))` por fonte).
- `search()` legado delega para `search_hybrid` quando `fts_store` é fornecido; quando ausente, mantém comportamento original.
- `constants.py`: `HYBRID_RRF_K: int = 60`.

**Testes (estender `tests/unit/query/test_query_engine.py`):**
- Mesmo corpus: `search()` vs `search_hybrid()` retornam ordens distintas para pergunta com termo exato presente só em BM25.
- `search_hybrid` com `fts_store` retornando vazio degrada para só-vetorial sem erro.
- Score RRF é bounded (`max ≈ 2 * 1/(1+rrf_k)`).

---

## Fase 12 — Retrieval hierárquico (sumário + detalhe)
**Dependências:** Fase 11. **Paralelismo:** 12.1 ‖ 12.2. **Critério:** para base sintética de 100 chunks, `search_hierarchical` retorna top-K docs em <50ms (filtro sumário), depois puxa detalhes.

### Task 12.1 — Sumarização determinística (sem LLM)
**Output:**
- Novo módulo `src/indexer/summarizer.py` com `def summarize(text: str, max_chars: int = 400) -> str`.
- Estratégia: cabeçalho (`title`) + 3 sentenças mais "densas" (ranking por `len(words)/n_sentences`, filtro de stop-words curtas, senteças de ≤1 palavra descartadas).
- Migration `0004_doc_summaries.sql`: tabela `doc_summaries(document_id INTEGER PRIMARY KEY REFERENCES documents(id), summary TEXT NOT NULL, embedding BLOB, created_at TEXT)` + flag `kind` em vec_chunks.
- `RagIndexer.ingest_*` enriquece `doc_summaries` por doc ingerido (idempotente: `INSERT OR REPLACE`).

**Testes (`tests/unit/indexer/test_summarizer.py`):**
- `summarize` em texto de 5 000 chars devolve ≤400 chars e ≥1 sentença legível.
- Re-ingerir doc com mesmo conteúdo não duplica linha em `doc_summaries`.

### Task 12.2 — Two-stage retrieval no `QueryEngine`
**Output:**
- Novo método `search_hierarchical(question: str) -> list[ScoredChunk]`:
  1. Embedding da pergunta (passa por cache se disponível — Fase 13).
  2. Top-N (default 10) documentos por similaridade ao `doc_summaries.embedding`.
  3. ANN em `vec_chunks` restrito a esses `document_id`.
- Constante `HIERARCHICAL_TOP_DOCS: int = 10`.

**Testes (estender `tests/unit/query/test_query_engine.py`):**
- Corpus misto; query aponta para tema em apenas 1 doc → ranking hierárquico põe esse doc no top-3 antes do flat.
- Corpus com 0 docs retorna `[]` (sem erro).

---

## Fase 13 — Cache de embeddings de query + troca de modelo
**Dependências:** Fase 11 (RAG híbrido pronto) + Fase 12 (reutiliza `embed`). **Paralelismo:** 13.1 ‖ 13.2. **Critério:** 2ª query idêntica tem latência de embedding = 0 (cache hit, sem invocar `embedder.embed`).

### Task 13.1 — `QueryEmbeddingCache` (sqlite)
**Output:**
- Novo módulo `src/query/embedding_cache.py` com `class QueryEmbeddingCache(db_path: Path, dim: int)`.
- Tabela `query_cache(query_hash TEXT PRIMARY KEY, query_text TEXT, embedding BLOB, hit_count INTEGER, last_used_at TEXT)`.
- Hash = `sha256(query_text.strip().lower().encode("utf-8"))`.
- API: `get(query: str) -> list[float] | None`, `put(query: str, embedding: list[float]) -> None`, `stats() -> dict[str, int]`.

**Testes (`tests/unit/query/test_embedding_cache.py`):**
- `put` + `get` round-trip em tmp DB preserva vetor (numpy L2 igual).
- Diferentes espaços/quebras (`"  NF-e  "` vs `"nf-e"`) geram mesmo hash (cache hit).
- `last_used_at` e `hit_count` atualizam em `get` quando há hit.

### Task 13.2 — Integração transparente
**Output:**
- `EmbeddingProvider` ganha método opcional `embed_cached(texts: list[str], cache: QueryEmbeddingCache | None = None) -> list[list[float]]` com batch que consulta/insere no cache.
- `QueryEngine.__init__` aceita `embedding_cache: QueryEmbeddingCache | None = None`; `search()` / `search_hybrid` / `search_hierarchical` passam a usar `embed_cached`.
- Cache corrompido (embedding dim errada): levanta `RuntimeError`; fallback gracioso para `embedder.embed()` direto.

**Testes:**
- 2ª chamada com mesma query: `cache.get` é chamado, `embedder.embed` **não** é chamado.
- Integração E2E: `tests/integration/test_e2e_pipeline.py` ganha caso verificando que 2ª query idêntica termina com latência da 2ª menor (tolerância 100ms).

---

## Fase 14 — Parent-document retrieval
**Dependências:** Fase 10 (chunking estrutural) + Fase 11 (híbrido). **Paralelismo:** 14.1 ‖ 14.2. **Critério:** parágrafo de 800 chars gera 1 parent + 2 detail, filhos com `parent_chunk_id` setado, retrieval devolve parent mesmo que só filho estivesse no top-K.

### Task 14.1 — Esquema parent + detail
**Output:**
- Migration `0003_parent_retrieval.sql`:
  - `vec_chunks.kind TEXT NOT NULL DEFAULT 'detail' CHECK(kind IN ('detail','parent','summary'))`.
  - `vec_chunks.parent_chunk_id INTEGER REFERENCES vec_chunks(rowid)` (apenas quando `kind='detail'`).
- Novo configurador no chunker: emite `parent_chunk` para cada bloco de parágrafo ≥ 2 sentences, e 1+ `detail_chunk` dentro dele (grafo direcionado 1→N).

**Testes (estender `tests/unit/indexer/test_structural_chunker.py`):**
- Parágrafo de 800 chars (2 sentences×400) gera `kind='parent'` (1) + `kind='detail'` (2).
- Filhos têm `parent_chunk_id` setado; pai tem NULL.

### Task 14.2 — Retrieval devolve parent
**Output:**
- `ScoredChunk` ganha `chunk_index: int` e `parent_text: str | None` (preenchido quando o hit é detail e pai não estava entre os top-K).
- `search_hybrid`/`search_hierarchical`: após selecionar top-K detail, expande para incluir pai (sem duplicar pais já retornados).

**Testes:**
- Hit em `detail` cujo pai não estava nos top-K: `parent_text` preenchido com o texto-pai.
- Hit em dois filhos do mesmo pai não duplica o pai (dedup por `parent_chunk_id`).

---

## Fase 15 — Re-rank cross-encoder (opt-in)
**Dependências:** Fases 11 (precisa do pool de candidatos) + 12 (pool hierárquico). **Paralelismo:** 15.1 ‖ 15.2. **Critério:** flag desativada por padrão; quando ativada, MRR aumenta ≥15% no benchmark (Fase 16).

### Task 15.1 — Wrapper do cross-encoder
**Output:**
- Novo módulo `src/query/reranker.py` com `class CrossEncoderReranker(model_name: str = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1")`.
- Método `rerank(question: str, chunks: list[ScoredChunk], top_k: int) -> list[ScoredChunk]`. Lazy-load, batch encode `(question, chunk.text)`, ordena por logit.

**Testes (`tests/unit/query/test_reranker.py`):**
- 2 chunks, um claramente mais relevante: rerank devolve o relevante em 1º.
- `model_name` inválido (rede off / modelo inexistente): levanta `RuntimeError` documentado; **não** derruba a query (fallback = ranking original).

### Task 15.2 — Integração em `QueryEngine` atrás de flag
**Output:**
- `QueryEngine(..., enable_rerank: bool = False)`. Quando True: `top_k_candidates = top_k * 5` → rerank → `top_k`.
- `constants.py`: `RERANK_DEFAULT = False`, `RERANK_CANDIDATES_MULTIPLIER = 5`.
- Flag exposta no CLI `python -m src.query` via `--rerank`.

**Testes:**
- `search` com `enable_rerank=False` **não** instancia `CrossEncoderReranker` (spy/monkeypatch).
- `search` com `enable_rerank=True` chama `reranker.rerank` exatamente 1×.

---

## Fase 16 — Benchmark de relevância e contrato de qualidade
**Dependências:** Fases 9–15. **Paralelismo:** 16.1 ‖ 16.2. **Critério:** `pytest tests/integration/test_quality.py` exit 0; relatório em `storage/benchmark_report.json`.

### Task 16.1 — Dataset de avaliação (curated)
**Output:**
- `tests/fixtures/eval_set.json` com ≥20 pares `{question, expected_doc_url, expected_keywords: list[str]}`.
- `tests/integration/conftest.py` ganha fixture `eval_set`.

### Task 16.2 — Runner e métricas
**Output:**
- Novo script `python -m src.eval` que computa **recall@5**, **MRR**, **citation_rate**.
- Saída em `storage/benchmark_report.json`.
- `tests/integration/test_quality.py`: roda baseline (Fase 8) vs otimizado (Fase 15), assert `recall_at_5_with_optimizations >= recall_at_5_baseline` (não regride).

**Testes críticos (do AGENTS.md):**
- Toda resposta cita a fonte presente na base (assert por regex no JSON).

---

## Fase 17 — Skill opencode, documentação e provisionamento
**Dependências:** Fases 9–16. **Paralelismo:** 17.1 ‖ 17.2 ‖ 17.3. **Critério:** `opencode run "Como a NT 2019.001 trata cancelamento?"` retorna resposta citando NT 2019.001 com URL do fixture.

### Task 17.1 — Atualização da skill `dfe-fiscal`
- `.opencode/skills/dfe-fiscal/SKILL.md`: documenta flags `--chunker`, `--rerank`, `--hybrid`, `--hierarchical`.
- Cita literalmente: `StructuralChunker`, `FtsStore`, `QueryEmbeddingCache`, `CrossEncoderReranker`.

### Task 17.2 — Atualização de `AGENTS.md` e `README.md`
- `AGENTS.md`: nova seção "Estratégia RAG (Sprint 2)" com diagrama.
- "Decisões em aberto" → marcadas resolvidas (modelo) ou redirecionadas (retenção de sumários).

### Task 17.3 — CLI: `python -m src.ragctl`
- Sub-comandos: `migrate` (aplica migrations), `benchmark` (Fase 16), `reindex --chunker=structural` (reindexa).

---

## Riscos e mitigações

| Risco | Impacto | Mitigação |
|---|---|---|
| Mudar `DIM` do embedding invalida `vec_chunks` | Reindexação total | Migration nunca altera `vec_chunks` in-place; troca = `ragctl reindex` |
| FTS5 em texto longo consome muito espaço | Crescimento 2× | FTS5 é `content='vec_chunks'`; não duplica texto |
| Sumários determinísticos ruins em NT longa | Recall piora vs flat | Benchmark Fase 16 detecta regressão |
| Cross-encoder adiciona latência em CPU lenta | UX pior com `--rerank` | Flag desativada por padrão |

---

## Checkpoints (gates)

1. **Após Fase 11**: comparar baseline vs híbrido em subset manual; se MRR não melhora ≥10%, abortar.
2. **Após Fase 13**: medir latência do embedding no cache miss; se > 300ms, fallback para `all-MiniLM-L6-v2`.
3. **Após Fase 15**: ativar rerank só se `citation_rate` ≥ 0.95 **e** latência < 1s.

---

## Estimativa consolidada (Sprint 2)

| Fase | Tasks | Pico paralelo | Cobertura crítica |
|---|---|---|---|
| 9 | 2 | 1 | 100% `parser/`, 100% `db/` migration |
| 10 | 2 | 2 | 100% `indexer/` |
| 11 | 2 | 2 | 100% `query/` |
| 12 | 2 | 2 | ≥80% global |
| 13 | 2 | 2 | 100% `query/` |
| 14 | 2 | 2 | 100% `indexer/` |
| 15 | 2 | 2 | ≥80% global |
| 16 | 2 | 2 (sequencial em 1) | nova suíte integration |
| 17 | 3 | **3** | — |
| **Total** | **17 tasks** | **3 paralelos** (Fase 17) | ≥80% global, 100% em parser + indexer |

**Critério global de conclusão do Sprint 2:**
```bash
pytest tests/ --cov=src --cov-fail-under=80                   # toda suíte
python -m src.ragctl migrate                                  # DB idempotente
python -m src.ragctl benchmark                                # recall@5 ≥ baseline
python -m src.query --hierarchical --rerank "pergunta"        # CLI funciona com flags
```
