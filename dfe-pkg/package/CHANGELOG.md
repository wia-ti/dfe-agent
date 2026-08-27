# Changelog

Todas as mudancas notaveis neste projeto sao documentadas aqui.

## 0.1.0 — 2026-XX-XX (Sprint 14 MVP, em desenvolvimento)

### Added
- Pacote npm `@dfe-agent/dfe-agent` com agent + skill + CLI Node
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