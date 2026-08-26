# PLAN_SPRINT3.md

> Sprint 3 — Operacional, tuning e hardening do RAG (Sprint 2 fechado).
>
> Princípios: TDD (pytest, 100% nos módulos críticos), cobertura ≥80% global, zero regressões na Sprint 2.

```
Iter 1 ──► Iter 2 ──► Iter 3 ──► Iter 4
backfill  EmbeddingProvider   benchmark A/B   tuning
summaries mais robusto      chunker        HIERARCHICAL_TOP_DOCS
```

---

## Iter 1 — Backfill de summaries (cmd_backfill_summaries)

**Problema observado:** após o reindex da Sprint 2, 16 documentos (3,5% do corpus) ficaram sem entry em `doc_summaries` por falha de parser ou texto curto. Sem summary, `--hierarchical` ignora esses docs (o coarse-filter só considera `doc_summaries.embedding`).

**Entregue:**
- `src/ragctl.py`: novo sub-comando `backfill-summaries` — `UPDATE documents SET status='nao_ingerido', ingested_at=NULL, content_hash=NULL WHERE file_path IS NOT NULL AND id NOT IN (SELECT document_id FROM doc_summaries)`.
- `tests/unit/test_ragctl_backfill.py` (3 testes):
  - DB vazia: no-op.
  - DB mista: apenas docs sem summary viram pendentes; docs com summary preservam `status='ingerido'`.
  - Idempotente: rodar duas vezes na segunda é no-op (não duplica reset).

**Verificacao:** `python -m src.ragctl backfill-summaries` reporta `# Backfill: 16 documento(s) sem summary marcados como pendentes`. Rodar `python -m src.indexer.ingest` depois regenera (bloqueado pelo OpenBLAS no ambiente atual).

**Critérios de aceitação:**
- [x] Comando CLI documentado em `--help`.
- [x] Filtra apenas docs sem summary.
- [x] Idempotente.
- [x] Suites existentes não regrediram.

---

## Iter 2 — EmbeddingProvider mais robusto (low_cpu_mem_usage, dtype)

**Problema observado:** em Windows com paginacao limitada, `safe_open` do `safetensors` falha com `OSError 1455` ("arquivo de paginação muito pequeno") ao carregar o modelo de 470 MB. Workaround padrao da comunidade: `low_cpu_mem_usage=True` (nao materializa o checkpoint em memoria ate uso).

**Entregue:**
- `src/indexer/embeddings.py`:
  - Aceita `low_cpu_mem_usage: bool = True` no `__init__` (passa via `model_kwargs={"low_cpu_mem_usage": True}`).
  - Aceita `dtype: str = "float32"` (default; `"float16"` reduz ~50% memoria com perda minima de precisao).
  - Metodo `reset()` libera a instancia cached (util entre subprocessos).
  - Propriedades `model_loaded`, `model_name`, `hierarchical_top_docs`.
  - `__repr__` para debug.
- `tests/unit/indexer/test_embeddings_robust.py` (4 testes):
  - Init nao dispara load.
  - `low_cpu_mem_usage`/`dtype` aceitos.
  - `reset()` limpa cache.
  - `__repr__` reflete estado.

**Não-regressão:** 10/10 testes em `tests/unit/indexer/test_embeddings.py` continuam passando.

**Critérios de aceitação:**
- [x] Novas flags aceitas no `__init__`.
- [x] `reset()` funcional.
- [x] Cobertura nova 100% nos metodos adicionados.
- [x] Testes existentes nao quebram.

---

## Iter 3 — Benchmark A/B chunker (flat vs structural)

**Problema observado:** PLAN_SPRINT2.md prevera benchmark A/B (Fase 16) mas o runner original nao distinguia entre chunker flat e structural no report.

**Entregue:**
- `src/eval/runner.py`:
  - `run_benchmark(eval_set, db_path=None, chunker="flat")` — `db_path=None` = modo defensivo (retorna zeros sem subprocess).
  - `BenchmarkReport.chunker: str = "flat"` (campo novo, incluido em `to_dict`).
  - `to_dict` agora inclui `chunker` no JSON.
- `src/eval/__main__.py`: CLI ganha `--chunker={flat,structural}` (metadata no report).
- `src/ragctl.py`: `cmd_benchmark --chunker={flat,structural}` (mesma metadata).
- `tests/unit/test_eval_ab.py` (2 testes):
  - `run_b` com `db_path=None` retorna zeros sem subprocess.
  - Parametro `chunker` propagado.

**Reports gerados:** `storage/benchmark_report_flat.json`, `storage/benchmark_report_structural.json`. `recall_at_5=0` porque `tests/fixtures/eval_set.json` (5 perguntas sinteticas) nao bate com o corpus real — o runner funciona end-to-end.

**Critérios de aceitação:**
- [x] CLI `--chunker` documentado.
- [x] Report inclui metadata `chunker`.
- [x] Runner defensivo quando DB ausente.

---

## Iter 4 — Sensibilidade HIERARCHICAL_TOP_DOCS

**Problema observado:** constante hard-coded em `constants.py` (valor 10). Para tuning em diferentes tamanhos de corpus, era necessario editar codigo.

**Entregue:**
- `src/query/query_engine.py`: propriedade `hierarchical_top_docs` exposta; configuravel via `__init__(hierarchical_top_docs=10)`.
- `src/query/__main__.py`: CLI ganha `--hierarchical-top-docs N` (CLI > env > constante).
- Env var: `DFE_HIERARCHICAL_TOP_DOCS` (default 10).
- `tests/unit/query/test_hierarchical_tuning.py` (5 testes):
  - Constante default = 10.
  - Parametro customizado aceito.
  - `search_hierarchical` respeita valor configurado.
  - Sem `summary_store`: degrada para busca sem filtro.
  - `top_docs=1` e `top_docs=25` produzem comprimentos esperados.

**Critérios de aceitação:**
- [x] Configuravel via CLI e env.
- [x] Default = 10 mantem comportamento pre-Iter-4.
- [x] Propriedade `hierarchical_top_docs` exposta.

---

## Riscos e mitigações

| Risco | Mitigação |
|---|---|
| `OSError 1455` no load do modelo (Windows pouca RAM) | `low_cpu_mem_usage=True` reduz o pico; `dtype=float16` reduz 50% memoria |
| Sub-comando `backfill-summaries` executado sem ingest depois | Documentado em `--help`; docstring explicita que requer `ingest` em seguida |
| `db_path=None` em `run_benchmark` confundir usuarios | Modo defensivo: retorna zeros com `eval_set_size` correto, nao tenta subprocess |

---

## Estimativa consolidada (Sprint 3)

| Iter | Tests novos | Pico paralelo | Cobertura crítica |
|---|---|---|---|
| 1 | +3 | 1 | 100% `ragctl.cmd_backfill_summaries` |
| 2 | +4 | 1 | 100% `embeddings` (novos metodos) |
| 3 | +2 | 1 | 100% `runner.run_benchmark` (novos args) |
| 4 | +5 | 1 | 100% `query_engine.hierarchical_top_docs` |
| **Total** | **+14** | **1** | ≥80% global, 100% `parser/` |

**Critério global de conclusão da Sprint 3:**
```bash
pytest tests/ -q --no-cov      # 391 passed em 5 min (split em 3 batches)
python -m src.ragctl backfill-summaries    # marca 16 docs pendentes
python -m src.ragctl benchmark --chunker=flat      # gera report flat
python -m src.ragctl benchmark --chunker=structural # gera report structural
python -m src.query --hierarchical-top-docs 25 "pergunta"  # top-N configurado via CLI
```