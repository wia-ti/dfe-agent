# PLAN_FEATURE_dfe-agent-npm-package.md

> Plano de **distribuição do agente `dfe-agent` como pacote npm** consumível por
> outros projetos opencode. Cobre: empacotamento, CLI de bootstrap, base RAG
> portátil (Node), publicação e CI.
>
> Origem: pedido do usuário em 2026-08-26 ("elabore um plano para que o agente
> dfe-agent possa ser disponibilizado para outros projetos via npm"). Princípio:
> **TDD** (teste vermelho primeiro), zero regressão nas 13 sprints existentes,
> cobertura >= 80% no novo pacote, contratos CLI validados via subprocess.
>
> NAO cobre: mudanças em `src/` (pipeline Python continua canônico para o
> próprio DFe-Agent); novos portais oficiais; novos modelos de embedding
> (default permanece `paraphrase-multilingual-MiniLM-L12-v2`).
>
> Convenção de versionamento: data ISO da sprint + tag SemVer (`0.1.0` para o
> primeiro MVP, `1.0.0` ao fechar Fase F).

## Criterio global de conclusao

`npm install @dfe-agent/dfe-agent && npx dfe-agent install && npx dfe-agent update && npx dfe-agent query "O que é a NF-e?"` em um scratch project (path limpo, sem Python, sem assets pré-instalados) retorna exit code 0 **E** o output contém JSON com `answer` citável **E** `sources[]` com URL presente na base empacotada **E** `npm view @dfe-agent/dfe-agent version` retorna versão publicada **E** os 3 agents canonicos (`dfe-agent`, `dev`, `code-reviewer`) aparecem no menu `opencode agent list` do scratch project **E** a suite `pytest tests/` do DFe-Agent root continua verde (zero regressão).

```
Fase A ──► Fase B ──► Fase C ──► Fase D ──► Fase E ──► Fase F
scaffold  empacotar  CLI Node  RAG base  query     publicar
(mono-    assets     (install,  portável  engine    (npm +
repo)     (sync)     update,    (GH       (Node,    CI)
                     query)     releases)  sqlite-
                                          vec)
```

**Dependencias criticas entre fases**:
- A (scaffold) independente, deve rodar primeiro.
- B (empacotar assets) depende de A — precisa do package.json.
- C (CLI Node) depende de A (precisa do binário no package.json) e B (precisa dos assets para instalar).
- D (RAG base portátil) depende de A; independente de B/C (paralelo possível).
- E (query engine Node) depende de C (CLI) + D (base disponível).
- F (publicar) depende de B+C+D+E — gate de release.

**Paralelismo intra-fase**:
- B: B.1 (sync agent.md) + B.2 (sync SKILL.md) + B.3 (drift test) em paralelo.
- C: C.1 (install) + C.2 (update) + C.3 (query) + C.4 (status) podem ser desenvolvidos em paralelo, mas testes integrados dependem de todos.
- E: E.1 (vector search) + E.2 (FTS5) + E.3 (RRF) + E.4 (cache) — vetor e FTS paralelos; RRF depende dos dois; cache depende de vetor.

---

## Tabela de IDs

| Prefixo | Significado |
|---|---|
| `B<n>` | BLOQUEANTE — bloqueia publicação até resolver |
| `I<n>` | IMPORTANTE — pode ir para próxima minor |
| `P<n>` | PARCIAL — cleanup/dívida técnica |
| `S<n>` | SUGESTÃO — nice-to-have |

Itens cobertos: **3 BLOQUEANTE + 4 IMPORTANTE + 2 PARCIAL** (preliminar; refinar na Fase 0.6 do `/feature`).

---

## Resumo dos problemas observados (preliminar)

| ID | Sintoma | Causa raiz | Severidade |
|----|---------|------------|------------|
| **B14.1** | O agente `dfe-agent` (definido em `.opencode/agent/dfe-agent.md`) vive em mono-repo e NAO é distribuído. Outros projetos opencode NAO conseguem consumir a base RAG sem clonar o repositório inteiro. | O DFe-Agent foi projetado como projeto local (CLI `python -m src.query`); ausência de formato de empacotamento. | **BLOQUEANTE** |
| **B14.2** | O pipeline RAG é 100% Python (`pypdf`, `sentence-transformers`, `sqlite-vec` via Python). Consumidores npm tipicamente NÃO têm Python instalado. Bloqueio arquitetural. | Decisão Sprint 1 (Python como linguagem da skill). | **BLOQUEANTE** |
| **B14.3** | A base RAG (`storage/dfe.db` + embeddings + `vec_chunks`) tem dezenas de MB e é regenerada apenas via `python -m src.indexer.ingest` (requer Python + sentence-transformers + ~2GB RAM). Consumidores npm não conseguiriam popular a base. | Pipeline Python-only sem formato portátil. | **BLOQUEANTE** |
| **I14.1** | `package.json` raiz não existe; não há manifests Node no projeto. Impossível publicar npm sem criar. | Escopo do projeto era apenas Python + opencode (TypeScript só no RAG meta-cognitivo em `.opencode/rag/`). | IMPORTANTE |
| **I14.2** | Script de sync entre `.opencode/agent/dfe-agent.md` ↔ `packages/dfe-agent/dist/agent.md` ainda não existe. Drift entre fonte e distribuição é certo após Sprint 14+. | Sem pipeline de sync automatizado. | IMPORTANTE |
| **I14.3** | Query engine Python (`src/query/query_engine.py`) precisa ser portada para Node (`@xenova/transformers` + `better-sqlite3` + `sqlite-vec`) sem perda de qualidade. Drift de embeddings entre `paraphrase-multilingual-MiniLM-L12-v2` (Py) e `Xenova/paraphrase-multilingual-MiniLM-L12-v2` (Node) precisa ser validado. | Decisão Sprint 5 C.2 (Py embeddings). | IMPORTANTE |
| **I14.4** | Skill `dfe-fiscal` (`SKILL.md:1-58`) cita comandos `python -m src.*` que NAO funcionam no projeto consumidor. Skill precisa de variants: `python -m` (DFe-Agent root) **OU** `dfe-agent <cmd>` (consumidor npm). | Skill monolítica sem awareness de contexto. | IMPORTANTE |
| **P14.1** | `npx dfe-agent update` precisa de hosting da base pré-built. Sem decisão de hosting (GitHub Releases vs npm asset vs CDN), bloqueia F. | Decisão arquitetural em aberto. | PARCIAL |
| **P14.2** | Sem CI de publicação; sem lock de versões entre DFe-Agent (mono-repo) e `@dfe-agent/dfe-agent` (npm). Risco de publicar versão inconsistente. | Sem automação. | PARCIAL |

---

## Decisoes arquiteturais (resolver na Fase 0 do `/feature` antes de Fase A)

| # | Decisao | Opcoes | Recomendacao |
|---|---|---|---|
| D1 | Layout do pacote | (a) mono-repo `packages/dfe-agent/` ; (b) repo separado `dfe-agent-npm` ; (c) monorepo tools (npm workspaces, pnpm, turbo) | **(a) mono-repo `packages/dfe-agent/`** — reusa CI do DFe-Agent; sync via path relativo; versionamento SemVer separado via `packages/dfe-agent/package.json` |
| D2 | Nome do pacote | (a) `dfe-agent` (unscoped, pode estar tomado) ; (b) `@dfe-agent/dfe-agent` (org escopada) | **(b) `@dfe-agent/dfe-agent`** — alinha com GitHub org (criar `dfe-agent` org se necessário). Publicação requer npm org; MVP pode usar scope pessoal. |
| D3 | Linguagem do CLI | (a) TypeScript (compilado para JS) ; (b) JavaScript puro ; (c) Node com dependências nativas | **(a) TypeScript** — reusa `@xenova/transformers` e `better-sqlite3` que já estão em `.opencode/package.json`; build via `tsc` (já configurado em `.opencode/tsconfig.json`) |
| D4 | Localização da base RAG no consumidor | (a) `~/.dfe-agent/dfe.db` (user-global) ; (b) `<project>/.dfe-agent/dfe.db` (per-project) ; (c) `<project>/node_modules/@dfe-agent/dfe-agent/data/dfe.db` | **(a) user-global por default + override via env `DFE_AGENT_BASE_DIR`** — evita duplicação de 50-100MB por projeto; CI pode sobrescrever |
| D5 | Mecanismo de bootstrap da base | (a) bundled seed (npm asset, ~30MB gzip) ; (b) GitHub Releases download ; (c) Node-only collector/indexer (re-implementar em TS) | **(b) GitHub Releases download** + seed mínimo bundled para first-run offline. (a) alternativa se hosting falhar. (c) é follow-up Sprint 15+ se刷新 for requisito. |
| D6 | Modelo de embedding no consumidor | (a) `Xenova/paraphrase-multilingual-MiniLM-L12-v2` (ONNX em Node) ; (b) `Xenova/all-MiniLM-L6-v2` (EN-only, menor) ; (c) API externa (OpenAI, Cohere) | **(a)** — espelha `DFE_EMBEDDING_MODEL` default; sem custo externo; offline-capable. Drift test obrigatório (B14.3 mitigado). |
| D7 | Sync da base entre DFe-Agent (Py) e consumidor (Node) | (a) embeddor Py gera, embeddor Node consome — drift zero se mesmo modelo+tokenizer ; (b) gerador unico ONNX, ambos consomem | **(b) ONNX unico** — export do modelo Py para ONNX (já é o que `@xenova/transformers` carrega); garantir que `sentence-transformers` use o mesmo ONNX. Validar com `tests/integration/test_embedding_parity.py` (cosine similarity >= 0.99 entre Py e Node para 100 sentenças de teste). |
| D8 | Permissões do CLI de bootstrap | (a) postinstall auto-roda `install` + `update` ; (b) postinstall só avisa, usuário roda manualmente ; (c) opt-in via flag | **(c) opt-in via flag `--auto-setup` no install** + README explícito. Default: postinstall só imprime próximos comandos. Evita surpresa em CI. |
| D9 | Versionamento SemVer | (a) CalVer (2026.08.0) ; (b) SemVer estrito atrelado a sprints DFe-Agent ; (c) SemVer independente | **(c) SemVer independente** — primeiro dígito sobe quando contrato CLI/skill mudar; segundo dígito quando base RAG for re-publicada; terceiro dígito quando patch. Sincronizar com tag git do DFe-Agent via `npm version` no CI. |
| D10 | Compatibilidade com opencode CLI | (a) suportar opencode CLI >= 1.0 ; (b) suportar versao X especifica ; (c) suportar a ultima estavel | **(c) suportar a ultima estavel** — campo `engines.opencode` no `package.json`; testar com a versão do CI antes de publicar. Quebrar = minor bump. |

---

## Fase A — Scaffold do mono-repo `packages/dfe-agent/` (B14.1 + I14.1)

**Criterio**: diretorio `packages/dfe-agent/` existe com `package.json`, `tsconfig.json`, `src/`, `tests/`, `.gitignore` local. `npm install` dentro dele retorna exit 0. Suite do DFe-Agent root continua 100% verde.

### Task A.1 — Criar `packages/dfe-agent/` com manifest TypeScript

- Agent: dev
- Input: nenhuma
- Output:
  - `packages/dfe-agent/package.json` com `name: "@dfe-agent/dfe-agent"`, `version: "0.1.0"`, `type: "module"`, `bin: { "dfe-agent": "./dist/bin/dfe-agent.js" }`, `main: "./dist/index.js"`, `engines: { "node": ">=20" }`, `files: ["dist/", "README.md"]`, `scripts: { "build": "tsc", "test": "node --test --import tsx tests/", "lint": "tsc --noEmit" }`, `dependencies` espelhando `.opencode/package.json` (4 runtime: `@xenova/transformers`, `better-sqlite3`, `sqlite-vec`, `@opencode-ai/plugin` se necessário), `devDependencies: { "typescript": "5.x", "tsx": "4.x", "@types/node": "22.x", "@types/better-sqlite3": "7.x" }`
  - `packages/dfe-agent/tsconfig.json` extendendo `../../.opencode/tsconfig.json` com `outDir: "./dist"`, `rootDir: "./src"`, `include: ["src/**/*"]`
  - `packages/dfe-agent/.gitignore` ignorando `dist/`, `node_modules/`, `*.log`, `.dfe-agent/` (data local de dev)
  - `packages/dfe-agent/README.md` placeholder com seção "Status: MVP em desenvolvimento (Sprint 14)"
  - `packages/dfe-agent/src/index.ts` com `export const VERSION = "0.1.0"; export * from "./cli.js";` (reexport)
- Testes criticos:
  - [ ] `cat packages/dfe-agent/package.json | jq .name` retorna `"@dfe-agent/dfe-agent"`
  - [ ] `cat packages/dfe-agent/package.json | jq .bin` retorna objeto com `dfe-agent`
  - [ ] `cd packages/dfe-agent && npm install` retorna exit 0 (gate B14.1)
  - [ ] `pytest tests/ --no-cov --no-header -q` no root continua verde (zero regressao)

### Task A.2 — Adicionar `packages/dfe-agent/` ao `.gitignore` raiz e ao CI matrix

- Agent: dev
- Input: Task A.1 completa
- Output:
  - `.gitignore` raiz: garantir `packages/*/dist/` e `packages/*/node_modules/` ignorados; `packages/dfe-agent/` em si NÃO (queremos versionar o source)
  - CI matrix (workflow `.github/workflows/test.yml` se existir, ou documentar em PLAN_SPRINT14.md): adicionar job `test-npm-package` que roda `npm install && npm run build && npm test` em `packages/dfe-agent/`
- Testes criticos:
  - [ ] `cat .gitignore | grep -E "packages.*dist"` retorna 1+ matches
  - [ ] `find packages/dfe-agent -name "*.ts" -not -path "*/node_modules/*"` retorna 1+ arquivos (não está sendo ignorado)
  - [ ] CI job `test-npm-package` aparece em `.github/workflows/*.yml` (se CI existir) ou documentado como follow-up

---

## Fase B — Empacotar assets (agent.md + SKILL.md) com sync bidirecional (B14.1 + I14.2)

**Criterio**: `packages/dfe-agent/dist/agent.md` é cópia exata de `.opencode/agent/dfe-agent.md` **E** `packages/dfe-agent/dist/skill/dfe-fiscal/SKILL.md` é cópia exata de `.opencode/skills/dfe-fiscal/SKILL.md`. Drift entre fonte e distribuição é detectado por teste.

### Task B.1 — Script de sync `sync-assets.ts` (source → dist)

- Agent: dev
- Input: Task A.1 completa
- Output:
  - `packages/dfe-agent/scripts/sync-assets.ts` que lê `.opencode/agent/dfe-agent.md` + `.opencode/skills/dfe-fiscal/SKILL.md` (paths relativos ao DFe-Agent root, hardcoded em constante `SOURCE_ROOT`) e escreve cópias em `packages/dfe-agent/dist/agent.md` e `packages/dfe-agent/dist/skill/dfe-fiscal/SKILL.md`
  - Loga via `console.info("[sync] copied <src> -> <dst>")` para cada arquivo
  - Idempotente (rodar 2x = mesmo resultado)
  - Adicionado ao `package.json > scripts.sync`
- Testes criticos (TDD vermelho primeiro):
  - [ ] `tests/sync-assets.test.ts` cobre: (a) cria arquivos quando não existem; (b) sobrescreve quando existem; (c) falha com erro claro se source não existe; (d) preserva encoding UTF-8 com acentos; (e) idempotente (2 rodadas = mesmo SHA-256)
  - [ ] `npm run sync` no `packages/dfe-agent/` retorna exit 0
  - [ ] `diff .opencode/agent/dfe-agent.md packages/dfe-agent/dist/agent.md` retorna vazio

### Task B.2 — Script de validação de drift `drift-check.ts` (CI gate)

- Agent: dev
- Input: Task B.1 completa
- Output:
  - `packages/dfe-agent/scripts/drift-check.ts` que compara `dist/agent.md` ↔ source; falha com exit 1 + mensagem clara se diferir
  - Adicionado ao `package.json > scripts.drift-check`
  - Adicionado ao CI (job `test-npm-package` roda `npm run drift-check` antes de `npm test`)
- Testes criticos:
  - [ ] `tests/drift-check.test.ts` cobre: (a) passa quando idêntico; (b) falha com mensagem clara quando divergente; (c) exit code 1 em divergência
  - [ ] Editar `.opencode/agent/dfe-agent.md` (inserir linha dummy) + rodar `npm run drift-check` → exit 1 (gate B14.1)

### Task B.3 — Documentar convenção "fonte canonica no root, distrib copia"

- Agent: dev
- Input: Task B.2 completa
- Output:
  - `packages/dfe-agent/README.md` seção "Development workflow" explicando: editar fonte canonica em `.opencode/agent/dfe-agent.md` ou `.opencode/skills/dfe-fiscal/SKILL.md` no DFe-Agent root; rodar `npm run sync` em `packages/dfe-agent/` antes de commit
  - Adicionar nota em `AGENTS.md > Padroes de codigo` sobre a convenção "agent canonico mora no root do DFe-Agent, copia distribuida via sync-assets"
- Testes criticos:
  - [ ] `grep -r "sync-assets" --include="*.md" AGENTS.md packages/dfe-agent/README.md` retorna 1+ matches

---

## Fase C — CLI Node: `dfe-agent install | update | query | status` (B14.2 + I14.4)

**Criterio**: `npx dfe-agent --help` mostra os 4 subcommands **E** `npx dfe-agent install` em scratch project copia agent + skill para `.opencode/` **E** `npx dfe-agent status` mostra versão + base path + mtime **E** `npx dfe-agent query "..."` retorna JSON `{answer, sources[]}` com fontes citadas.

### Task C.1 — CLI skeleton + subcommand `install`

- Agent: dev
- Input: Task A.1 + Task B.1 (assets disponiveis em `dist/`)
- Output:
  - `packages/dfe-agent/src/cli.ts` com parser de subcommands via `node:util.parseArgs`
  - `packages/dfe-agent/src/commands/install.ts` que: (a) resolve target dir (default `.opencode/` do cwd); (b) copia `dist/agent.md` → `<target>/agent/dfe-agent.md`; (c) copia `dist/skill/dfe-fiscal/` → `<target>/skill/dfe-fiscal/` recursivamente; (d) loga cada cópia; (e) respeita flag `--auto-setup` que também dispara `update`
  - Exit codes: 0 sucesso, 1 erro de I/O, 2 target inválido
- Testes criticos:
  - [ ] `tests/cli/install.test.ts` cobre: (a) copia em scratch project limpo; (b) falha se target dir não pode ser criado; (c) sobrescreve sem warning (comportamento desejado para re-install); (d) `--auto-setup` chama update sequencialmente; (e) --help imprime usage

### Task C.2 — Subcommand `update` (download base RAG)

- Agent: dev
- Input: Task C.1 completa + Fase D em paralelo (depende de base existir para testar end-to-end)
- Output:
  - `packages/dfe-agent/src/commands/update.ts` que: (a) resolve base path (default `~/.dfe-agent/dfe.db` ou override `DFE_AGENT_BASE_DIR`); (b) busca último release em GitHub API (`https://api.github.com/repos/<owner>/DFe-Agent/releases/latest`); (c) baixa asset `dfe.db.gz` + `dfe.db.gz.sha256`; (d) verifica SHA-256; (e) descompacta em path atômico (write to `dfe.db.tmp` + rename); (f) abre a base e roda `PRAGMA user_version` para confirmar schema
  - Fallback: se rede falhar, oferece seed bundled em `dist/seed/dfe.db.gz` (TBD na Fase D)
- Testes criticos:
  - [ ] `tests/cli/update.test.ts` cobre: (a) sucesso com mock de GitHub API + asset fake; (b) falha com SHA mismatch (exit 3 + mensagem); (c) fallback para seed bundled em rede off (mock); (d) resolução de path via `DFE_AGENT_BASE_DIR` env var

### Task C.3 — Subcommand `query "<pergunta>"`

- Agent: dev
- Input: Task C.2 completa + Fase E (engine) completa
- Output:
  - `packages/dfe-agent/src/commands/query.ts` que: (a) parseia args (`--mode=semantic|hybrid|hierarchical`, `--no-cache`, `--top-k`); (b) delega para `queryEngine.search()` em `src/query.ts`; (c) formata saída como JSON `{answer, sources: [{url, title, score}]}` (mesmo contrato do `python -m src.query`); (d) escreve em stdout; (e) se exit code != 0 quando base ausente
- Testes criticos:
  - [ ] `tests/cli/query.test.ts` cobre: (a) output JSON válido; (b) `answer` é literal quando `has_sufficient_evidence = false` (`NO_EVIDENCE_MESSAGE`); (c) `sources[]` tem URLs presente na base; (d) cache hit na 2a chamada idêntica (mesmo conteúdo, sem nova chamada ao embedder)

### Task C.4 — Subcommand `status`

- Agent: dev
- Input: Task C.1 + C.2
- Output:
  - `packages/dfe-agent/src/commands/status.ts` que imprime JSON com: `{version, basePath, baseExists, baseMtime, baseDocCount, baseEmbeddingModel, opencodeVersion}`
- Testes criticos:
  - [ ] `tests/cli/status.test.ts` cobre: (a) reporta `baseExists=false` quando path não existe; (b) reporta `baseDocCount=N` corretamente (mock DB); (c) `--json` (default) vs `--text` (humano-legível)

---

## Fase D — RAG base portátil + hosting (B14.3 + P14.1)

**Criterio**: workflow GitHub Actions publica `dfe.db.gz` + `dfe.db.gz.sha256` como assets em todo release `v*.*.*` do DFe-Agent **E** `npx dfe-agent update` baixa o último release e popula base no consumidor.

### Task D.1 — Script `publish-base.yml` (GitHub Actions)

- Agent: dev
- Input: nenhuma (depende apenas de CI do DFe-Agent)
- Output:
  - `.github/workflows/publish-base.yml` que roda em `push tags: v*.*.*` no DFe-Agent root: (a) checkout; (b) setup Python + install deps; (c) `python -m src.ragctl migrate`; (d) `python -m src.collector --once`; (e) `python -m src.indexer.ingest`; (f) `gzip -c storage/dfe.db > dfe.db.gz`; (g) `sha256sum dfe.db.gz > dfe.db.gz.sha256`; (h) upload como release assets via `softprops/action-gh-release@v2`
- Testes criticos:
  - [ ] Workflow file valid (yamllint ou `actionlint`)
  - [ ] Manual run em tag de teste (`v0.0.0-test`) gera assets (verificável em GitHub Releases)

### Task D.2 — Seed bundled para first-run offline

- Agent: dev
- Input: Task D.1 completa
- Output:
  - `packages/dfe-agent/src/seed/dfe.db.gz` (snapshot da base em data X, regenerado manualmente a cada minor release)
  - Documentado em README: "seed bundled cobre ~95% das NTs até <data>; rode `dfe-agent update` para latest"
  - Tamanho alvo: <30MB gzip
- Testes criticos:
  - [ ] `ls -lh packages/dfe-agent/src/seed/dfe.db.gz` reporta <30MB
  - [ ] `zcat packages/dfe-agent/src/seed/dfe.db.gz | sqlite3 :memory: "PRAGMA user_version"` retorna versão válida (>= 6, schema atual)

### Task D.3 — Validação de paridade Py ↔ Node embeddings (B14.3 gate)

- Agent: dev
- Input: Task D.2 + Fase E em paralelo
- Output:
  - `packages/dfe-agent/tests/integration/test_embedding_parity.py` (Py, no DFe-Agent root): para 100 sentenças fiscais de `tests/fixtures/eval_set.json`, gera embeddings com `sentence-transformers` e salva `fixtures/embeddings_py.npy`
  - `packages/dfe-agent/tests/integration/test_embedding_parity.test.ts` (Node): carrega mesmo modelo via `@xenova/transformers`, gera embeddings para as mesmas 100 sentenças, calcula cosine similarity média com Py
  - Gate: similarity >= 0.99 (drift aceitável de quantization ONNX)
- Testes criticos:
  - [ ] Suite Node passa com similarity >= 0.99
  - [ ] Se drift > 0.01, documentar follow-up Sprint 15+ para investigar tokenizer mismatch

---

## Fase E — Query engine Node (port de `src/query/query_engine.py`) (I14.3)

**Criterio**: `queryEngine.search(pergunta, {mode})` em Node retorna o mesmo `{answer, sources[]}` que `python -m src.query "<mesma pergunta>"` para as 10 perguntas do `eval_set.json` (cosine similarity entre ranks >= 0.8).

### Task E.1 — Vector search (sqlite-vec + @xenova/transformers)

- Agent: dev
- Input: Task D.3 (paridade validada)
- Output:
  - `packages/dfe-agent/src/query/embedder.ts` wrapper de `@xenova/transformers` com cache LRU em memória (LRU 128)
  - `packages/dfe-agent/src/query/vectorSearch.ts` que: (a) carrega `vec_chunks` via `sqlite-vec`; (b) gera embedding da query; (c) busca top-K via `vec_chunks MATCH ? ORDER BY distance LIMIT K`; (d) dedup por `doc_id`; (e) boost temporal (mais recente primeiro)
- Testes criticos:
  - [ ] `tests/query/vectorSearch.test.ts` cobre: (a) embedder cache hit; (b) top-K respeitado; (c) dedup por doc_id; (d) boost temporal (mock de datas)
  - [ ] `tests/query/embedder.test.ts` cobre: (a) cache miss na 1a chamada, hit na 2a; (b) modelo carregado 1x (singleton)

### Task E.2 — FTS5 search (BM25)

- Agent: dev
- Input: Task E.1 (independente em escopo)
- Output:
  - `packages/dfe-agent/src/query/ftsSearch.ts` que: (a) carrega `fts_chunks`; (b) parseia query em `MATCH ?` (suportar phrase queries com aspas); (c) retorna top-K com `bm25(fts_chunks)` score
- Testes criticos:
  - [ ] `tests/query/ftsSearch.test.ts` cobre: (a) BM25 retorna termos literais corretamente; (b) phrase query `"nota tecnica"` retorna apenas matches exatos; (c) tokenização PT (acentos, stopwords)

### Task E.3 — Modo híbrido (RRF k=60 entre vector + FTS5)

- Agent: dev
- Input: Tasks E.1 + E.2 completas
- Output:
  - `packages/dfe-agent/src/query/hybrid.ts` que: (a) recebe top-K de vector e top-K de FTS; (b) funde via RRF `score = sum(1 / (k + rank_i))` com `k=60`; (c) retorna lista ranqueada
- Testes criticos:
  - [ ] `tests/query/hybrid.test.ts` cobre: (a) overlap de docs ranqueados mais alto; (b) docs exclusivos de um modo aparecem; (c) RRF k=60 (não k=10 ou k=100) — comparacao com golden

### Task E.4 — Cache de query embedding (HIT na 2a)

- Agent: dev
- Input: Task E.1 completa
- Output:
  - `packages/dfe-agent/src/query/cache.ts` que persiste em `<basePath>.cache.db` (SQLite): tabela `query_cache(query_hash TEXT PRIMARY KEY, embedding BLOB, created_at TEXT)`
  - Hash = SHA-256 de `model + mode + query_normalized`
  - Lookup antes de chamar embedder; insert após gerar
- Testes criticos:
  - [ ] `tests/query/cache.test.ts` cobre: (a) miss → embedder chamado; (b) hit na 2a chamada idêntica (spy); (c) hit mesmo com query string identica mas espaços diferentes (normalização); (d) invalidação quando modelo muda (DFE_EMBEDDING_MODEL env var)

### Task E.5 — `queryEngine.search()` orquestrador + contrato `{answer, sources}`

- Agent: dev
- Input: Tasks E.1 + E.2 + E.3 + E.4
- Output:
  - `packages/dfe-agent/src/query/index.ts` com `search(query, opts)` que: (a) roteia para vector/fts/hybrid; (b) chama `contextBuilder.build()` (port de `src/query/context_builder.py`); (c) chama `has_sufficient_evidence()`; (d) retorna `{answer, sources: [...]}` com `NO_EVIDENCE_MESSAGE` literal se insuficiente
  - `packages/dfe-agent/src/query/contextBuilder.ts` que monta o prompt com chunks + fontes (mesma logica do Py)
- Testes criticos:
  - [ ] `tests/query/index.test.ts` cobre: (a) modo default = vector; (b) `--hybrid` muda modo; (c) NO_EVIDENCE_MESSAGE literal quando vazio; (d) sources sempre presente (mesmo que vazio)

---

## Fase F — Publicação + CI + E2E em scratch project (B14.1 + P14.2)

**Criterio**: `npm view @dfe-agent/dfe-agent version` retorna versão **E** `npm install @dfe-agent/dfe-agent && npx dfe-agent install && npx dfe-agent update && npx dfe-agent query "O que é a NF-e?"` em projeto limpo retorna JSON válido com fontes citadas.

### Task F.1 — GitHub Actions: CI matrix + publish-on-tag

- Agent: dev
- Input: Fases A-E completas
- Output:
  - `.github/workflows/test-npm-package.yml` que roda em todo PR: (a) checkout; (b) `cd packages/dfe-agent && npm ci && npm run build && npm test && npm run drift-check`
  - `.github/workflows/publish-npm.yml` que roda em `push tags: packages-v*.*.*`: (a) roda test-npm-package; (b) builda; (c) `npm publish --access public --provenance` com `NODE_AUTH_TOKEN` de secret
- Testes criticos:
  - [ ] CI matrix verde em PR de teste
  - [ ] Tag `packages-v0.1.0` dispara workflow; assets aparecem em GitHub Releases
  - [ ] `npm view @dfe-agent/dfe-agent version` retorna `0.1.0` após publish (validar em npmjs.com)

### Task F.2 — Smoke test E2E em scratch project

- Agent: dev
- Input: Task F.1 completa
- Output:
  - `packages/dfe-agent/tests/e2e/scratch-project-test.sh` que: (a) cria tmp dir; (b) `cd tmp && npm init -y`; (c) `npm install @dfe-agent/dfe-agent` (mockado via `npm pack` + local install em CI); (d) `npx dfe-agent install`; (e) `npx dfe-agent update`; (f) `npx dfe-agent query "O que é a NF-e?"`; (g) valida exit 0 + JSON com `answer` + `sources[]`; (h) cleanup tmp
- Testes criticos:
  - [ ] Script executa em CI com exit 0
  - [ ] JSON parseado contém chave `answer` não-vazia
  - [ ] JSON parseado contém `sources` array com 1+ items, cada um com `url` válida

### Task F.3 — README canônico + CHANGELOG

- Agent: dev
- Input: Task F.2 completa
- Output:
  - `packages/dfe-agent/README.md` reescrito com: (a) "What is this" — agent + RAG base; (b) "Install" — `npm install ...` + `npx dfe-agent install`; (c) "Quick start" — `npx dfe-agent query "..."`; (d) "Updating the base" — `npx dfe-agent update`; (e) "Custom base path" — `DFE_AGENT_BASE_DIR`; (f) "Troubleshooting" — common errors; (g) "Development" — link para DFe-Agent repo
  - `packages/dfe-agent/CHANGELOG.md` com entrada `0.1.0` (MVP)
- Testes criticos:
  - [ ] `markdownlint packages/dfe-agent/README.md` retorna 0 erros
  - [ ] README tem todas as 6 secoes obrigatorias

### Task F.4 — Documentar integração no AGENTS.md + SPEC.md

- Agent: dev
- Input: Task F.3 completa
- Output:
  - `AGENTS.md` nova seção "Consumindo dfe-agent de outro projeto" com quickstart
  - `SPEC.md` nota na seção "Stack" sobre distribuição npm
  - `.opencode/skills/dfe-fiscal/SKILL.md` seção "Contexto de uso" mencionando dual mode (Py local vs Node via npm)
- Testes criticos:
  - [ ] `grep -r "npm install @dfe-agent" --include="*.md" AGENTS.md SPEC.md packages/dfe-agent/README.md` retorna 3+ matches

---

## Apêndice A — Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Drift de embeddings Py ↔ Node invalida base | Média | Alto | Task D.3 gate de paridade; se falhar, gerar base 100% em Node (re-rodar `python -m src.collector --once` em CI Node + gerar embeddings ONNX no momento do publish, NAO consumir base Py) |
| Tamanho do pacote npm excede 50MB (limite soft) | Média | Médio | D5 (GitHub Releases download) — pacote final ~5MB (bin CLI + agent.md + SKILL.md + seed mini). Base vem do release |
| GitHub rate limits no `update` (60 req/h sem auth) | Baixa | Médio | Token de GitHub via env `GITHUB_TOKEN` (free tier 5000 req/h); fallback para seed bundled se rate-limited |
| Consumidores em Windows com `sqlite-vec` nativo quebra | Média | Alto | Usar `sqlite-vec-windows-x64` (já em `.opencode/node_modules/`); testar em Windows no CI matrix (runner `windows-latest`) |
| `@xenova/transformers` falha ao carregar ONNX em Node 22+ (problema visto em `.opencode/`) | Alta | Alto | Pin Node engine >= 20 < 23; documentar em README "Node 22.21.1 tem issue conhecida"; fallback `DFE_EMBEDDING_DTYPE=float16` |
| Sprint 14+ mexe em `.opencode/agent/dfe-agent.md` e esquece de rodar sync | Alta | Médio | Task B.2 drift-check no CI + pre-commit hook (Task F.1) que rejeita commit se drift |
| Usuário roda `npx dfe-agent install` em projeto que já tem agent custom | Baixa | Médio | Install sobrescreve sem warning (decisão B.1) — documentar em README; futuro: flag `--no-overwrite` |
| Escopo da Fase E incha (re-porter 13 sprints de Py para TS) | Alta | Alto | Decompor E em 5 tasks granulares; cada task entregável independentemente; se E.3 (RRF) atrasar, MVP lança só com E.1 (vector) |

---

## Apêndice B — Fora de escopo

- Re-implementar collector/indexer em Node (Task 5+ follow-up Sprint 15+)
- Suporte a Windows ARM64 (sqlite-vec não tem build oficial; documentar como follow-up)
- API HTTP (`POST /query`) — continua fora de escopo do SPEC.md
- Multi-tenant (uma base por usuário OK; múltiplos perfis no mesmo usuário NÃO)
- Embeddings via API externa (OpenAI, Cohere) — viola "100% local" do SPEC.md
- Sincronização em tempo real da base (consumer precisa rodar `dfe-agent update` manualmente)
- Internacionalização EN do agent (`dfe-agent.md` continua PT-only; documentação EN pode ser follow-up)
- Migração de bases antigas (v5 → v6) no consumidor — responsabilidade do DFe-Agent root

---

## Apêndice C — Comandos shell para reproduzir Sprint 14 manualmente

```bash
# Setup local
cd packages/dfe-agent
npm install
npm run build
npm run sync
npm run drift-check
npm test

# Smoke E2E em scratch project
mkdir /tmp/scratch-dfe && cd /tmp/scratch-dfe
npm init -y
npm install /path/to/dfe-agent/packages/dfe-agent  # local install
npx dfe-agent install
npx dfe-agent update
npx dfe-agent query "O que é a NF-e?"
npx dfe-agent status

# Publicar (CI)
git tag packages-v0.1.0
git push origin packages-v0.1.0
# GitHub Actions publica automaticamente em https://www.npmjs.com/package/@dfe-agent/dfe-agent

# Validar regressão no DFe-Agent root
cd /path/to/DFe-Agent
pytest tests/ --cov=src --cov-fail-under=80
```

---

## Próximos passos (resumo executivo)

1. **Aprovar este plano** via `/feature empacotar dfe-agent como @dfe-agent/dfe-agent no npm` (criará `PLAN_SPRINT14.md` detalhando as 6 fases com base neste doc, com TDD vermelho primeiro em cada task).
2. **Resolver 10 decisões arquiteturais** (D1-D10) na Fase 0 do `/feature` — output: tabela de decisões no novo `PLAN_SPRINT14.md`.
3. **Iniciar Fase A** (scaffold mono-repo) — gate B14.1.
4. **Após Fase F**: tag `packages-v0.1.0` + primeira publicação npm.
5. **Sprint 15+** (follow-ups): E.5 (paridade eval), collector/indexer em Node, suporte multi-idioma, Windows ARM64.