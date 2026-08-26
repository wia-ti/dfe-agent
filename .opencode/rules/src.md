---
paths: src/**/*.py
---

# Backend (`src/**/*.py`) — DFe-Agent

- **Sem API HTTP**: toda interação é via CLI (`python -m src.<modulo>`). Não criar
  Flask/FastAPI/Starlette — fora de escopo do SPEC.md.
- **`__init__.py` expõe só a interface pública**: lógica de I/O e domínio fica
  no arquivo do módulo; imports passam pelo `__init__.py` do destino, nunca por
  caminho relativo `..modulo`.
- **Todo path HTTP passa pelo `Throttler`** (`src/utils/throttler.py`): novo
  portal, nova rota, novo coletor — sempre. Sem `requests.get` solto nem
  `urllib.request` fora do Throttler.
- **Schema de `documents` é obrigatório**: URL, `content_hash`, status, datas,
  `nt_number`, `version`, `replaces_doc_id`, `language`. Metadado faltando =
  falha de contrato (`src/db/migrations.py:0002`).
- **Substituição = `replaces_doc_id`**: nunca `DELETE FROM documents` nem
  `DROP TABLE vec_chunks`. Para re-ingest: `python -m src.ragctl reindex`.
- **Índices vêm das migrations**: FTS5 (0004) e `doc_summaries` (0005). Nunca
  recriar `vec_chunks`/`fts_chunks` à mão; `apply_pending` é quem aplica.
- **Modo hierárquico depende de `doc_summaries`**: `Summarizer` em
  `src/indexer/summarizer.py` é determinístico (sem LLM). Não invocar LLM dentro
  do sumarizador.
- **Embedding via env**: `DFE_EMBEDDING_MODEL` (default
  `paraphrase-multilingual-MiniLM-L12-v2`, dim 384). Cache de query em
  `storage/query_cache.db` é HIT obrigatório na 2a chamada idêntica.
- **CLI é a interface**: cada submódulo com entrada de usuário expõe
  `__main__.py` + `argparse`. Flags Sprint 2 ficam em
  `src/query/__main__.py` e `src/query/constants.py` — não duplicar.