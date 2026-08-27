# Changelog

Todas as mudancas notaveis neste projeto sao documentadas aqui.

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