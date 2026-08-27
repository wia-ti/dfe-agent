# PLAN_SPRINT17.md

> Sprint 17 — Bug D fix definitivo (Opção A: re-ingest com `normalize_embeddings=True`).
> Aprovado por Andrews em 2026-08-27 (mensagem: "usaremos a opcao A, porem gere uma sprint nova seguindo todo o procedimento padrao do projeto").
> Pipeline: `/bug` canonico (`/.opencode/command/bug.md`) com gate duplo (testes + code-review).

## Contexto

Bug D — drift entre dois caminhos de producao de embeddings Py:

| Caminho | Comando | `normalize_embeddings` | Norm resultante |
|---|---|---|---|
| `tests/integration/generate_py_embeddings.py:33` (gate D.7) | manual / CI | `True` | 1.0 |
| `src/indexer/embeddings.py:213` (producao real via `python -m src.indexer.ingest`) | runtime | **SEM** normalize | 2.6-3.3 |

A base `~/.dfe-agent/dfe.db` foi gerada pelo caminho 2 (sem normalize). O Node normaliza. Distance = sqrt(sum(diff^2)) > 1.0 sempre. Score = 1 - distance < 0.5. `hasSufficientEvidence` = false sempre. Sintoma: `NO_EVIDENCE_MESSAGE` para qualquer query.

Gate D.7 validou apenas o caminho 1 contra Node (parity 0.99+), nao a base real. Bug latente desde Sprint 14.

Probe direto (Node + sqlite-vec): embeddar o texto literal de um chunk retorna **outros docs** no top-1 (dist=1.20). "banana" retorna dist=1.59. Espacos diferentes.

## Decisao (Sprint 17)

**Opcao A**: editar `src/indexer/embeddings.py:213` para `normalize_embeddings=True` + re-ingerir 28.182 chunks (448 documentos; ~10-15 min) + republicar `dfe.db.gz` no GitHub Releases.

Alternativa B (re-criar `vec_chunks` com `distance_metric=cosine`) fica como FOLLOW-UP Sprint 18+.

## Decisoes arquiteturais (D17.1-D17.4)

- **D17.1**: Manter `vec_chunks` com `vec0(embedding float[384], ...)` (L2 default do sqlite-vec). Com norm = 1.0 em ambos os lados, L2 = sqrt(2 * (1 - cos)) e' monotonicamente relacionado a cosine similarity, portanto ranking fica correto. Opcao B (cosine distance nativo) fica para Sprint 18+ por ser mais invasivo.
- **D17.2**: Manter `packages/dfe-agent/src/query/embedder.ts:66` com `normalize: true` (ja' esta' correto desde v0.1.0; gate anti-regressao estrutural).
- **D17.3**: Adicionar gate de normalizacao em `test_embedding_parity.test.ts` BEHAVIORAL: norm de embedding fresh Node == 1.0 (gate anti-regressao Node) e norm medio dos embeddings da base == 1.0 +/- 0.01 (gate anti-regressao base, requer `dfe.db` instalado).
- **D17.4**: Bump PATCH (0.1.4 -> 0.1.5). API publica inalterada.

## Tasks

### Fase 0 — Briefing + RAG antes (completo)
- Briefing canonico: AGENTS.md, SPEC.md, PLAN.md, regras dfe-rules/convencoes-gerais/src/tests/seguranca.
- RAG antes: knowledge file `2026-08-26-dev-sprint14-npm-package.md` (Sprint 14 base), `2026-08-27-dev-bug-dfe-agent-runtime-path-and-cache.md` (Sprint 15 Bug A/B), `2026-08-27-dev-bug-dfe-agent-schema-drift.md` (Sprint 16 Bug C).

### Fase 1 — Investigacao read-only (completo no relatorio Bug D anterior)
- Probe Node: norm fresh vs norm base, L2 distance, ranking com queries literais.
- Conclusao: drift de magnitude (Node norm = 1.0, base norm = 2.6-3.3) — fix minimo nao resolve; precisa re-ingest.

### Fase 2 — Aprovacao humana (completo)
- Relatorio entregue.
- Resposta: "usaremos a opcao A, porem gere uma sprint nova seguindo todo o procedimento padrao do projeto. ao gerar o arquivo de sprint pode comecar a executa-lo. estou ciente das modificacoes, nao precisa confirmar comigo, pode fazer o processo ate' o final desde que os testes e code-review deem sinal verde."

### Fase 3 — Correcao TDD (gate duplo)

#### Task 3.1 — Edicao Py minima
- Editar `src/indexer/embeddings.py:213`:
  ```python
  # antes:
  vectors = model.encode(texts, convert_to_numpy=True).tolist()
  # depois:
  vectors = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True).tolist()
  ```
- Rodar `pytest tests/indexer/` para confirmar que o teste estrutural (se houver) continua passando.
- Rodar `pytest tests/` completo (anti-regressao Python).

#### Task 3.2 — Gate humano: re-ingerir a base
- Comando: `python -m src.indexer.ingest` (BLOQUEADO pelo `dev/pre_tool_use.py` para o agent; gate humano).
- Esperado: re-ingerir 28.182 chunks em ~10-15 min. Loga progresso.
- Pos-condicao: `storage/dfe.db` tem norm medio dos embeddings == 1.0.

#### Task 3.3 — Regenerar `dfe.db.gz`
- `src/db/storage.py` tem helper de compressao; ou usar `python -c "import gzip, shutil; ..."` manualmente.
- Pos-condicao: `data/dfe.db.gz` (~30-50 MB) presente.
- Decisao: tentar via workflow `publish-base.yml` ou instruir user a rodar manualmente.

#### Task 3.4 — Publicar `dfe.db.gz` no GitHub Releases
- Workflow `.github/workflows/publish-base.yml` dispara com tag `dfe.db-v*` ou manual.
- Tag do asset: `dfe.db-vYYYY.MM.DD-XX` (gate B.3 Sprint 14).
- Agent NAO pode fazer tag/push de base diretamente porque exige coordenacao com CI.

#### Task 3.5 — Publicar Node v0.1.5
- `packages/dfe-agent/package.json` 0.1.4 -> 0.1.5.
- `packages/dfe-agent/src/index.ts` VERSION hardcoded.
- `packages/dfe-agent/CHANGELOG.md` entrada 0.1.5.
- `AGENTS.md` bloco Sprint 17 + FOLLOW-UPS.
- `.opencode/rag/knowledge/2026-08-27-dev-bug-dfe-agent-embedding-normalization.md` (RAG depois).
- Bump gate de normalizacao no teste BEHAVIORAL de parity.
- Commit + tag `packages-v0.1.5` + push (gate humano manual `git push` + `npm publish`).

### Fase 4 — Code review (subagent `general`; code-reviewer nao inviavel por Sprint 9 follow-up)
- Review de `src/indexer/embeddings.py` (1 linha editada), `packages/dfe-agent/src/index.ts` (VERSION), `package.json`, `CHANGELOG.md`, `tests/integration/test_embedding_parity.test.ts` (gate norm).
- Categoria: BLOQUEANTE / IMPORTANTE / SUGESTAO (template code-reviewer.md).

### Fase 5 — Loop corretivo (max 3 iteracoes)
- BLOQUEANTE: aplicar, re-rodar testes.
- IMPORTANTE: aplicar, re-rodar testes.
- SUGESTAO: registrar em `.opencode/rag/knowledge/<date>-dev-suggestions.md`.
- Gate: 0 BLOQUEANTE / 0 IMPORTANTE antes de Fase 7.

### Fase 6 — RAG depois
- Knowledge file `.opencode/rag/knowledge/2026-08-27-dev-bug-dfe-agent-embedding-normalization.md`:
  - Sintoma + causa raiz + fix + gate norm.
  - Embedding file via `npx tsx .opencode/rag/embed.ts --file <md>`.
- Sanity: `search.ts -q "embedding normalize_embeddings norm drift"` retorna top-1 = nosso knowledge.
- `AGENTS.md > Decisoes resolvidas (Sprint 17)` bloco adicionado.

### Fase 7 — Entrega humana
- Commit + tag `packages-v0.1.5` + push main + push tag (gate manual via `dev/pre_tool_use.py`).
- `npm publish --access public --provenance` (gate manual, executado pelo user; workflow ainda tem `if: false`).
- Relatorio final ao humano com:
  - Arquivos modificados.
  - Suite verde (npm test + pytest).
  - Code review final (0 BLOQUEANTE / 0 IMPORTANTE).
  - Comandos para o user publicar e validar.

## Testes criticos (gate duplo)

- [x] Gate Bug A — `paths.ts` (Sprint 15): ok.
- [x] Gate Bug B — `QueryCache(baseDir)` (Sprint 15): ok.
- [x] Gate Bug C — aliases SQL `document_id`/`chunk_index` (Sprint 16): ok.
- [ ] **Gate Bug D Sprint 17** — norm de embedding fresh Node == 1.0 (gate anti-regressao Node) + norm medio da base == 1.0 +/- 0.01 (gate anti-regressao base, requer re-ingest completo). Smoke test end-to-end: `npx dfe-agent query "cancelamento NF-e"` retorna chunks relevantes (NAO `NO_EVIDENCE_MESSAGE`).
- [ ] Suite Python: `pytest tests/ --cov=src --cov-branch --cov-fail-under=80` verde (gate anti-regressao Py).
- [ ] Suite Node: `npm test` no `packages/dfe-agent/` verde.
- [ ] Code review: 0 BLOQUEANTE / 0 IMPORTANTE (gate code-reviewer template).

## Criterios de fechamento

- [ ] `src/indexer/embeddings.py:213` com `normalize_embeddings=True`.
- [ ] `storage/dfe.db` re-ingerido (norm medio = 1.0).
- [ ] `data/dfe.db.gz` regenerado (~30-50 MB).
- [ ] `dfe.db.gz` publicado no GitHub Releases (tag `dfe.db-v*`).
- [ ] `packages/dfe-agent@0.1.5` publicado no npm registry.
- [ ] Smoke test end-to-end: `npx dfe-agent update && npx dfe-agent query "..."` retorna chunks (NAO `NO_EVIDENCE_MESSAGE`).
- [ ] Code review 0/0/N round 1 -> 0/0/0 round final.
- [ ] AGENTS.md atualizado (Sprint 17 bloco).
- [ ] RAG meta-cognitivo knowledge file embedado.

## Follow-ups Sprint 18+

1. **Re-criar `vec_chunks` com `distance_metric=cosine`** (mais correto que L2). Gate `vec0(embedding float[384], distance_metric=cosine, ...)`. Migration nova em `src/db/migrations.py`. Re-ingerir ~28.182 chunks (estimativa; corpus pode variar).
2. **Re-habilitar CI publish** (`publish-npm.yml` remover `if: false` + `needs: test`).
3. **Re-habilitar CI matrix Windows** (gate nativo Node 22/24 com `better-sqlite3` upgrade).
4. **Estender `tests/e2e/smoke-test.ps1`** para incluir `query` end-to-end.
5. **Criar versao bash de `smoke-test.ps1`** para CI Linux.
6. **Upgrade `better-sqlite3`** (issue #336 WillBrennan) para destravar gate nativo Win+Node>=22.
7. **Adicionar `--top-k` no CLI `dfe-agent query`** para inspecao de hits brutos (debug).

## Estimativa

~2-3 horas (incluindo 10-15 min de re-ingest). Riscos:
- Re-ingest longo (depende de hardware; CPU-bound em sentence-transformers).
- Republish de asset exige coordenacao (workflow ou manual).
- Smoke test do user pode precisar de mais 1 iteracao se a base ainda tiver drift residual.

## Links uteis

- Sprint 15 Bug A/B: `.opencode/rag/knowledge/2026-08-27-dev-bug-dfe-agent-runtime-path-and-cache.md`
- Sprint 16 Bug C: `.opencode/rag/knowledge/2026-08-27-dev-bug-dfe-agent-schema-drift.md`
- Gate D.7 (paridade Py <-> Node embeddings): `tests/integration/test_embedding_parity.test.ts`
- Pipeline `/bug`: `.opencode/command/bug.md`
- Code-reviewer template: `.opencode/agent/code-reviewer.md`
- Pre-tool-use hook: `.opencode/hooks/dev/pre_tool_use.py`
