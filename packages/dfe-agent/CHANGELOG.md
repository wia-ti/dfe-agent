# Changelog

Todas as mudancas notaveis neste projeto sao documentadas aqui.

## 0.1.5 — 2026-08-27 (Sprint 17 bugfix — embedding normalization drift)

### Fixed
- **`dfe-agent query` retornava `NO_EVIDENCE_MESSAGE` para qualquer query** mesmo com base populada (28.182 chunks / 448 documentos). Causa raiz: drift de normalizacao entre `src/indexer/embeddings.py:213` (Py gerava embeddings SEM `normalize_embeddings=True`, norm ~2.6-3.3) e `packages/dfe-agent/src/query/embedder.ts:66` (Node normaliza para norm = 1.0). L2 distance > 1.0 sempre, score < 0.5 (gate `MIN_RELEVANCE_SCORE`), `hasSufficientEvidence` sempre `false`. Gate D.7 validava apenas sentencas curtas; drift em chunks longos nao era detectado. Fix: adicionar `normalize_embeddings=True` no encode em `src/indexer/embeddings.py:213` + re-ingerir 28.182 chunks + ajustar `MIN_RELEVANCE_SCORE` de 0.5 para 0.3 (drift residual Py↔Node em chunks longos: Py usa attention_mask no mean pooling, Node usa `@xenova/transformers` sem attention_mask explicito). Smoke test: queries com termos tecnicos especificos retornam chunks reais.

### Notes
- Esta versao requer re-ingerir a base (gate humano: `python -m src.indexer.ingest`).
- Asset `dfe.db.gz` re-publicado no GitHub Releases via tag `dfe.db-v*`.
- Antes da instalacao: rode `python -m src.indexer.ingest` no DFe-Agent root OU aguarde o `update` baixar a nova base.
- Sem change breaking na API publica. Patch bump (0.1.4 -> 0.1.5).
- Code review (subagent `general`): gate duplo do `/bug` aplicado.
- Plano: `PLAN_SPRINT17.md`.

## 0.1.4 — 2026-08-27 (Sprint 16 bugfix — schema drift Py<->Node)

## 0.1.3 — 2026-08-27 (Sprint 15 bugfix)

### Fixed
- **`dfe-agent update && dfe-agent query` end-to-end quebrava no Windows** com `"Cannot open database because the directory does not exist"`. Causa raiz: a regra `~/.dfe-agent/dfe.db` (decisao D4 da Sprint 14) estava duplicada em 3 funcoes locais (`src/commands/update.ts`, `src/commands/status.ts`, `src/query/index.ts`); 2 esqueceram o `resolve(..., ".dfe-agent")`. Fix: nova fonte UNICA `src/paths.ts` com `resolveBaseDir/resolveDbPath/resolveCacheDbPath`; os 3 entrypoints agora importam de la. Gate: `tests/query/paths.test.ts` (7 testes estruturais).
- **`dfe-agent query` quebrava em modo `semantic`/`hybrid` com `"attempt to write a readonly database"`**. Causa raiz: `QueryCache` aceitava `handle: BetterSqlite3Database` no construtor e escrevia `CREATE TABLE` no mesmo handle aberto com `readonly: true`. Fix: construtor agora recebe `baseDir: string` e abre SUA PROPRIA conexao (read-write) em `<baseDir>/cache.db`, isolada do `dfe.db` (read-only). Adicionado `close()` idempotente (gate destructor cleanup-hook). Gates: estrutural em `paths.test.ts` + comportamental em `cache.test.ts`.

### Notes
- Sem change breaking na API publica (`src/index.ts` nao exporta `QueryCache`). Patch bump.
- Gate CI estendido: auto-detecta `win32 && Node >= 22` para skip dos testes comportamentais em ambiente Windows (bug pre-existente better-sqlite3 `RemoveEnvironmentCleanupHook`). Gate estrutural cross-platform cobre o caminho em qualquer ambiente.
- Code review (subagent `general`): 1 BLOQUEANTE / 0 IMPORTANTE / 6 SUGESTAO (round 1) -> 0/0/1 (round 2). 1 iteracao do loop corretivo.
- Antes da instalacao da nova versao, mover base antiga: `Move-Item -LiteralPath "$HOME\dfe.db" -Destination "$HOME\.dfe-agent\dfe.db"` se voce rodou `update` com v0.1.0-v0.1.2 (onde a base foi gravada no path errado).

## 0.1.0 — 2026-08-26 (Sprint 14 MVP)

### Added
- Pacote npm `@wiati/dfe-agent` com agent + skill + CLI Node
- Subcommands `install`, `update`, `query`, `status`
- Base RAG via GitHub Releases (download obrigatorio no primeiro `update`; sem seed bundled para manter npm tarball <50MB)
- Query engine Node port de `src/query/query_engine.py` com paridade validada
- Sync bidirecional `agent.md` + `SKILL.md` com drift detection no CI
- Workflow GitHub Actions `publish-base.yml` para publicar `dfe.db.gz` em cada release
- Workflow GitHub Actions `publish-npm.yml` para publicar no npm em tag `packages-v*.*.*`

### Known limitations (Sprint 14)
- Ambiente de desenvolvimento historico tinha issue pre-existente com Node v22.21.1 + `sharp`/`better-sqlite3` nativos (Sprint 13). **Resolvido em 2026-08-26** via upgrade para Node 24.19.0 LTS.
- `npx dfe-agent install` NAO e' automatico no postinstall (decisao D8 opt-in).
- Collector/indexer continuam em Python — Sprint 15+ pode portar para Node.
- **Sem seed bundled** (decisao revisada: `storage/dfe.db` gzipado = 61MB, excede target <30MB). Primeiro `update` exige rede; em rede off, retorna exit 3 com mensagem clara. Follow-up Sprint 15+: gerar seed mini (<5MB) com subconjunto de docs.