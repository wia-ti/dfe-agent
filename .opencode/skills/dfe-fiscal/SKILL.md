---
name: dfe-fiscal
description: "Use ONLY when the user asks about Brazilian Electronic Fiscal Documents (DF-e) — NF-e, NFC-e, CT-e, MDF-e, SPED, CONFAZ — or about Nota Técnica (NT), schemas XML da NF-e (tags UB/IBSCBS/cMunFGIBS/pIBSUF/etc.), Reforma Tributária do Consumo (RTC, LC 214/2025, IBS/CBS/Imposto Seletivo), IBPT, regras de validação, cClassTrib, CST, cCredPres, contributors exclusivos do IBS/CBS, eIBPT, ou when the request maps to the RAG pipeline of the DFe-Agent project (python -m src.collector, python -m src.indexer.ingest, python -m src.query, python -m src.ragctl). Triggers: NT 2025.002, tag UB, BSCBS, vIBSUF, grupo W03, cBenef, LC 214, monofasia, RAG fiscal."
license: MIT
---

# Skill: dfe-fiscal

Esta skill encapsula a logica do dominio fiscal eletronico do DFe-Agent: coleta, ingestao e consulta RAG de documentacao oficial (NF-e, NFC-e, CT-e, MDF-e, SPED, CONFAZ).

## Contexto de uso (Sprint 14+)

Esta skill tem **2 modos de invocacao** dependendo do contexto de execucao:

### Em DFe-Agent root (desenvolvimento local)

```bash
python -m src.query "<pergunta em linguagem natural>" --mode=hybrid
```

Fonte canonica dos dados: `python -m src.ragctl migrate && python -m src.collector --once && python -m src.indexer.ingest`.

### Em consumidor npm (`@dfe-agent/dfe-agent`)

```bash
npx dfe-agent query "<pergunta em linguagem natural>" --mode=hybrid
```

Fonte dos dados: `npx dfe-agent update` (baixa `dfe.db.gz` do GitHub Releases do DFe-Agent).

O **contrato de saida e identico**: `{answer, sources[]}` em ambos os modos. A escolha do comando depende apenas do `cwd` (root DFe-Agent vs projeto consumidor).

Quando o agente `dfe-agent` estiver ativo no opencode TUI, **usar o comando `npx dfe-agent query`** se o `.opencode/agent/dfe-agent.md` foi instalado via `npx dfe-agent install`; usar `python -m src.query` se estiver no proprio DFe-Agent root.

## Comandos invocaveis

### 1. Varredura completa dos portais oficiais

```bash
python -m src.collector --once
```

Executa `DocumentCollector.discover_and_register()` + `DocumentCollector.download_pending()`. Acessa os portais oficiais (apenas dominios em `ALLOWED_DOMAINS`), identifica novos documentos, baixa PDFs/HTML com throttling.

Flags opcionais:
- `--once`: executa uma varredura unica
- `--dry-run`: descobre URLs sem inserir no banco nem baixar

### 2. Ingestao de documentos pendentes no RAG

```bash
python -m src.indexer.ingest
```

Executa `RagIndexer.ingest_pending()` — para cada documento com status `nao_ingerido`:
- Extrai texto via parser (PDF ou HTML)
- Calcula hash SHA-256 do texto (idempotencia)
- Extrai metadados estruturados (NT number, data, versao) via `metadata_extractor.extract_document_metadata`
- Chunkifica (flat ou `structural`) + gera embeddings multilingues
- Persiste na base vetorial SQLite (`sqlite-vec`)
- Persiste summary deterministico via `summarizer.summarize` em `doc_summaries`
- Marca documento como `ingerido`

Flags opcionais:
- `--chunker={flat,structural}`: flat (default, pre-Sprint-2) ou structural (preserva contexto de secao NT via `structural_chunker`).

Documentos ja ingeridos (mesmo hash) sao pulados automaticamente.

### 3. Consulta RAG

```bash
python -m src.query "<pergunta em linguagem natural>"
```

Executa `QueryEngine.search(pergunta)` com cache de embedding (default ON). Modos opt-in via flag:

| Flag | Algoritmo | Uso |
|---|---|---|
| (nenhuma) | cosseno no vec_chunks + dedup + boost temporal | Default pre-Sprint-2 |
| `--hybrid` | RRF (k=60) entre semantico e FTS5 (BM25) | Termos literais (numero NT, codigo) |
| `--hierarchical` | two-stage: embedding -> top-10 summaries -> vec_chunks filtrado | Bases grandes (>1000 docs) |
| `--rerank` | cross-encoder opt-in (top-5*5 candidatos) | Quando benchmark Fase 16 mostra ganho de MRR |
| `--no-cache` | Desativa cache de embedding de query | Debug/teste |

Quando a busca tem chunks relevantes: monta contexto via `context_builder.build_context` e imprime JSON com `answer` + `sources`. Sem chunks: `"Nao encontrei base para responder"`.

### 4. CLI administrativo

```bash
python -m src.ragctl migrate                  # aplica migrations pendentes
python -m src.ragctl benchmark                # roda eval_set + grava benchmark_report.json
python -m src.ragctl reindex --chunker=flat  # dropa chunks e reingerir
python -m src.ragctl stats                    # contadores da base
```

## Diagnostico de `NO_EVIDENCE_MESSAGE` espurio

Se `python -m src.query "<pergunta>"` retornar
`"answer": "Nao encontrei base para responder"` MAS o corpus possui
documentos indexados (verificar com `python -m src.ragctl stats`),
investigar nesta ordem:

1. `python main.py --health` — confere se todos os modulos importam.
2. `python -c "from src.indexer.embeddings import EmbeddingProvider; e = EmbeddingProvider(); print(e.dim)"` — dispara o load; se levantar `RuntimeError` com substring `DFE_EMBEDDING_DTYPE`, ver Task F.1.
3. Workaround de ultimo recurso: `DFE_EMBEDDING_MODEL=all-MiniLM-L6-v2` (~80 MB, ingles-only — perde semantica em PT-BR).
4. Hardening completo do ambiente: `pwsh scripts/check_env.ps1`.

NUNCA escrever SQL raw em `scripts/` para "contornar" o RAG — isso viola o guardrail de veracidade. Usar sempre o CLI documentado.

Origem deste guardrail (PLAN_SPRINT5 F.2): 4 scripts ad-hoc
(`scripts/answer_nf_e_10_2026.py`, `scripts/buscar_dfereferenciado.py`,
`scripts/demo_query.py`, `scripts/demo_query_2026.py`) foram gerados
pelo proprio agente LLM apos `python -m src.query` retornar
`NO_EVIDENCE_MESSAGE` em razao de `OSError 1455` (page file do
Windows insuficiente) no load do
`paraphrase-multilingual-MiniLM-L12-v2`. O agente interpretou
"sem evidencia" como "CLI quebrado" e escreveu SQL raw no DB,
contornando o guardrail de veracidade.

## Classes principais referenciadas

- **`DocumentCollector`** (`src.collector.downloader`): orquestra descoberta + download com throttling
- **`RagIndexer`** (`src.indexer.rag_indexer`): ingere documentos com idempotencia por hash
- **`StructuralChunker`** (`src.indexer.structural_chunker`): chunker ciente de secoes NT (opcional via `--chunker=structural`)
- **`Summarizer`** (`src.indexer.summarizer`): extracao deterministica de sumario (sem LLM)
- **`MetadataExtractor`** (`src.parser.metadata_extractor`): regex para NT/convenio/data/versao no cabecalho
- **`QueryEngine`** (`src.query.query_engine`): busca semantica + boost temporal + dedup
- **`FtsStore`** (`src.db.fts_store`): indice FTS5/BM25 (criado pela migration 0004)
- **`DocSummaryStore`** (`src.db.doc_summaries`): summaries persistidos (criado pela migration 0005) — alimenta `--hierarchical`
- **`CrossEncoderReranker`** (`src.query.reranker`): reranker opt-in via `--rerank`
- **`QueryEmbeddingCache`** (`src.query.embedding_cache`): cache SQLite de embeddings (Fase 13)

## Guardrails

- Apenas dominios em `ALLOWED_DOMAINS` (enforced por hook `domain_guard`)
- Respeitar intervalo entre requisicoes (Throttler) — nao "metralhar" portais
- Documento ja ingerido (mesmo hash) NAO e reprocessado (idempotencia)
- Sem chunks relevantes: retornar `"Nao encontrei base para responder"`
- Toda resposta cita a fonte (URL + nome do documento) presente na base
- Migration framework garante upgrade v1->v6 sem perda de dados via `PRAGMA user_version`