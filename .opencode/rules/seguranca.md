---
name: seguranca
description: Guardrails inviolaveis de seguranca aplicaveis a qualquer agent (segredos fora do repo, anti-bot, guardrails de dominio, proveniencia do RAG, substituicao por replaces_doc_id).
---

# Segurança — DFe-Agent

Restrições que valem para qualquer agent (code-reviewer, dfe-agent e futuros).

- **Segredos fora do repo**: nunca commitar `.env`, chaves de API, dumps de
  `storage/dfe.db` ou `storage/query_cache.db`; confira `.gitignore` antes de
  qualquer `git add` que toque nesses paths.
- **Anti-bot é política**: nenhum proxy rotativo, CAPTCHA solving, UA spoofing ou
  contorno de rate-limit. A estratégia oficial é `Throttler` com jitter + recuo
  (`src/utils/throttler.py`). Não burlar.
- **Guardrails invioláveis**: `src/utils/http_guard.py` (guard HTTP in-process)
  bloqueia URL fora de `ALLOWED_DOMAINS` via `validate_url()` importado de
  `hooks.domain_guard`. O modulo `.opencode/hooks/domain_guard.py` eh o
  guardrail canonico; nunca desative `install_http_guard()` no coletor.
  > **Sprint 11 B11.2**: `.opencode/hooks/manifest.json` foi REMOVIDO
  > (era "letra morta" desde Sprint 5 C.1; opencode nao suporta nativamente
  > o tipo `pre_request`). A defesa em profundidade contra URL maliciosa
  > vive agora apenas no guard HTTP in-process (`src/utils/http_guard.py`)
  > + hook `code-reviewer/pre_tool_use_bash.py` (bloqueia `curl`/`wget`).
- **Proveniência do RAG**: todo chunk ingressado vem de `ALLOWED_DOMAINS` (via
  coletor) ou de `tests/fixtures/`. Nunca indexar corpus externo baixado por
  outros meios.
- **Escrita na base passa por portões explícitos**: só `apply_pending`
  (migrations), `RagIndexer.ingest_pending` e `python -m src.ragctl reindex`
  escrevem em `documents`/`vec_chunks`. Scripts ad-hoc com `INSERT`/`UPDATE`
  direto são proibidos.
- **Sem exfiltração**: nunca envie conteúdo de `storage/dfe.db`, transcripts do
  RAG meta (`.opencode/rag/knowledge/`) ou logs com texto fiscal via WebFetch/curl.
- **Substituição de documento**: superseded notes usam `replaces_doc_id`
  (migration 0002). Nunca `DELETE FROM documents` para "limpar versão antiga".
- **Code-reviewer**: se um comando de escrita passar pelo hook por bug, ABORTE
  a revisão e reporte como BLOQUEANTE — não tente corrigir.
