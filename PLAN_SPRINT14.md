# PLAN_SPRINT14.md

> Plano de **empacotamento do agente `dfe-agent` como pacote npm `@dfe-agent/dfe-agent`** consumivel por outros projetos opencode. Cobre scaffold mono-repo, sync de assets, CLI Node, base RAG portatil via GitHub Releases, port do query engine, publicacao e CI.
>
> Origem: pedido do usuario em 2026-08-26 ("elabore um plano para que o agente dfe-agent possa ser disponibilizado para outros projetos via npm"). Design de alto nivel em `PLAN_FEATURE_dfe-agent-npm-package.md` (2026-08-26). Principio: **TDD** (teste vermelho primeiro, implementacao minima, verde, refactor), zero regressao nas 13 sprints anteriores, cobertura >= 80% no novo pacote, contratos CLI validados via subprocess.
>
> NAO cobre: mudancas em `src/` (pipeline Python continua canonico para o proprio DFe-Agent); novos portais oficiais; novos modelos de embedding (default permanece `paraphrase-multilingual-MiniLM-L12-v2`); refactor estrutural maior no harness opencode; migracao de bases v5→v6 (responsabilidade do DFe-Agent root).
>
> Numeracao: `14 = max(PLAN_SPRINT*.md) + 1 = 13 + 1`. Convenção de tag para publicacao: `packages-v*.*.*` (separada das tags `v*.*.*` do DFe-Agent root, conforme D9).

## Decisoes arquiteturais resolvidas (Fase 0)

| # | Decisao | Resolucao | Justificativa |
|---|---|---|---|
| **D1** | Layout do pacote | **mono-repo `packages/dfe-agent/`** | Reusa CI do DFe-Agent; sync via path relativo; versionamento SemVer separado via `packages/dfe-agent/package.json`. Alternativa (repo separado) dobra overhead de governance. |
| **D2** | Nome do pacote | **`@dfe-agent/dfe-agent`** | Alinha com GitHub org futura `dfe-agent`; evita conflito com nome `dfe-agent` (provavelmente tomado no npm). Publicacao requer npm org; MVP pode usar scope pessoal. |
| **D3** | Linguagem do CLI | **TypeScript (compilado para JS)** | Reusa `@xenova/transformers`, `better-sqlite3`, `sqlite-vec` ja em `.opencode/package.json`; build via `tsc` (ja configurado em `.opencode/tsconfig.json`). |
| **D4** | Localizacao da base RAG no consumidor | **`~/.dfe-agent/dfe.db` (default) + override `DFE_AGENT_BASE_DIR`** | Evita duplicacao de 50-100MB por projeto; CI pode sobrescrever via env; per-project via env explicito. |
| **D5** | Mecanismo de bootstrap da base | **GitHub Releases download + seed bundled mini (~5MB)** | Download unico, atomic, versionado; seed garante first-run offline; re-implementar collector em Node fica para Sprint 15+. |
| **D6** | Modelo de embedding no consumidor | **`Xenova/paraphrase-multilingual-MiniLM-L12-v2` (ONNX em Node)** | Espelha `DFE_EMBEDDING_MODEL` default do DFe-Agent; sem custo externo; offline-capable; ja testado em `.opencode/rag/embed.ts`. |
| **D7** | Sincronizacao de embeddings Py ↔ Node | **ONNX unico** — DFe-Agent CI exporta do Py e Node consome via `@xenova/transformers` | Drift zero se mesmo modelo + mesmo tokenizer; validado por `tests/integration/test_embedding_parity.{py,ts}` (gate de cosine similarity >= 0.99). |
| **D8** | Permissoes do postinstall | **opt-in via `--auto-setup`** | Default: postinstall so imprime proximos comandos. Evita surpresa em CI; usuario controla momento do install. |
| **D9** | Versionamento | **SemVer independente** | Primeiro digito sobe quando contrato CLI/skill mudar; segundo quando base RAG re-publicada; terceiro quando patch. Tag `packages-v*.*.*` separada de tags do DFe-Agent. |
| **D10** | Compatibilidade opencode CLI | **ultima estavel** | Campo `engines.opencode` em `package.json`; testar com versao do CI antes de publicar. Quebrar = minor bump. |

## Criterio global de conclusao

`npm install @dfe-agent/dfe-agent && npx dfe-agent install && npx dfe-agent update && npx dfe-agent query "O que e a NF-e?"` em um scratch project (path limpo, sem Python, sem assets pre-instalados, sem `.opencode/` pre-existente) retorna exit code 0 **E** o output contem JSON com `answer` citavel **E** `sources[]` com URL presente na base empacotada **E** `opencode agent list` no scratch project lista `dfe-agent` como `primary` **E** `npm view @dfe-agent/dfe-agent version` retorna a versao publicada **E** `pytest tests/ --cov=src --cov-fail-under=80` no DFe-Agent root continua verde (zero regressao).

```
Fase A ──► Fase B ──► Fase C ──► Fase D ──► Fase E ──► Fase F
scaffold  empacotar  CLI Node  RAG base  query     publicar
(mono-    assets     (install,  portatil  engine    (npm +
repo)     (sync +    update,    (GH       (Node,    CI)
          drift)     query,     releases)  sqlite-
                     status)               vec)
```

**Dependencias criticas entre fases**:

- **A** (scaffold) independente, deve rodar primeiro.
- **B** (empacotar assets) depende de A — precisa do `package.json` para definir `files[]`.
- **C** (CLI Node) depende de A (precisa do binario no `package.json`) e B (precisa dos assets em `dist/` para instalar).
- **D** (RAG base portatil) depende de A; independente de B/C (paralelo possivel ate D.3).
- **E** (query engine Node) depende de C (CLI para orquestrar) + D.3 (paridade validada).
- **F** (publicar) depende de B+C+D+E — gate de release.

**Paralelismo intra-fase**:

- **A**: A.1 + A.2 sequenciais (A.2 mexe em `.gitignore` e CI matrix, depende de A.1 existir).
- **B**: B.1 + B.2 em paralelo (sync independente); B.3 sequencial (depende de B.1+B.2).
- **C**: C.1 + C.4 podem ser desenvolvidos em paralelo (install + status); C.2 + C.3 dependem de Fase D e E respectivamente.
- **D**: D.1 (workflow) independente; D.2 (seed) sequencial (depende de D.1); D.3 (paridade) paralelo com D.1/D.2.
- **E**: E.1 (vector) + E.2 (FTS5) paralelos; E.3 (RRF) depende de E.1+E.2; E.4 (cache) depende de E.1; E.5 (orquestrador) depende de E.1+E.2+E.3+E.4.

---

## Resumo dos problemas observados

| ID | Sintoma | Causa raiz | Severidade |
|----|---------|------------|------------|
| **B14.1** | O agente `dfe-agent` (definido em `.opencode/agent/dfe-agent.md`) vive em mono-repo e NAO e' distribuido. Outros projetos opencode NAO consomem a base RAG sem clonar o repositorio inteiro. | DFe-Agent foi projetado como projeto local (CLI `python -m src.query`); ausencia de formato de empacotamento. | **BLOQUEANTE** |
| **B14.2** | O pipeline RAG e' 100% Python (`pypdf`, `sentence-transformers`, `sqlite-vec` via Python). Consumidores npm tipicamente NAO tem Python instalado. Bloqueio arquitetural. | Decisao Sprint 1 (Python como linguagem da skill). | **BLOQUEANTE** |
| **B14.3** | A base RAG (`storage/dfe.db` + embeddings + `vec_chunks`) tem dezenas de MB e e' regenerada apenas via `python -m src.indexer.ingest` (requer Python + sentence-transformers + ~2GB RAM). Consumidores npm NAO conseguem popular a base. | Pipeline Python-only sem formato portatil. | **BLOQUEANTE** |
| **I14.1** | `package.json` raiz NAO existe; NAO ha manifests Node alem de `.opencode/package.json` (escopo RAG meta-cognitivo). Impossivel publicar npm sem criar. | Escopo do projeto era apenas Python + opencode (TS so' no RAG meta-cognitivo). | IMPORTANTE |
| **I14.2** | Script de sync entre `.opencode/agent/dfe-agent.md` <-> `packages/dfe-agent/dist/agent.md` ainda NAO existe. Drift entre fonte e distribuicao e' certo apos Sprint 14+. | Sem pipeline de sync automatizado. | IMPORTANTE |
| **I14.3** | Query engine Python (`src/query/query_engine.py`) precisa ser portada para Node (`@xenova/transformers` + `better-sqlite3` + `sqlite-vec`) sem perda de qualidade. Drift de embeddings entre Py e Node precisa ser validado (gate D.7). | Decisao Sprint 5 C.2 (Py embeddings canonicos). | IMPORTANTE |
| **I14.4** | Skill `dfe-fiscal` (`SKILL.md:11-70`) cita comandos `python -m src.*` que NAO funcionam no projeto consumidor. Skill precisa de variants: `python -m` (DFe-Agent root) **OU** `dfe-agent <cmd>` (consumidor npm). | Skill monolitica sem awareness de contexto. | IMPORTANTE |
| **P14.1** | `npx dfe-agent update` precisa de hosting da base pre-built. Decisao D5: GitHub Releases + seed bundled. Sem implementar D.1 (workflow de publish), bloqueia F. | Decisao arquitetural resolvida em D5; falta implementacao. | PARCIAL |
| **P14.2** | Sem CI de publicacao; sem lock de versoes entre DFe-Agent root e `@dfe-agent/dfe-agent`. Risco de publicar versao inconsistente. | Sem automacao. | PARCIAL |

Itens cobertos: **3 BLOQUEANTE + 4 IMPORTANTE + 2 PARCIAL**.

---

## Fase A — Scaffold do mono-repo `packages/dfe-agent/` (B14.1 + I14.1)

**Criterio**: diretorio `packages/dfe-agent/` existe com `package.json`, `tsconfig.json`, `src/`, `tests/`, `.gitignore` local. `npm install` dentro dele retorna exit 0. Suite do DFe-Agent root continua 100% verde.

### Task A.1 — Criar `packages/dfe-agent/` com manifest TypeScript

- Agent: dev
- Input: nenhuma (decisao D1 tomada na Fase 0).
- Diagnostico:
  - `packages/` NAO existe no root; criar estrutura.
  - `.opencode/package.json` ja tem 4 deps runtime uteis para o novo pacote: `@xenova/transformers`, `better-sqlite3`, `sqlite-vec`, `tsx`. Reusar em `packages/dfe-agent/`.
  - `.opencode/tsconfig.json` define `target: ES2022`, `module: ESNext`, `moduleResolution: Bundler`. Extender dali para evitar duplicacao.
- Output:
  - `packages/dfe-agent/package.json` com:
    ```json
    {
      "name": "@dfe-agent/dfe-agent",
      "version": "0.1.0",
      "type": "module",
      "main": "./dist/index.js",
      "types": "./dist/index.d.ts",
      "bin": { "dfe-agent": "./dist/bin/dfe-agent.js" },
      "engines": { "node": ">=20 <23" },
      "files": ["dist/", "README.md", "CHANGELOG.md"],
      "scripts": {
        "build": "tsc",
        "test": "node --test --import tsx tests/",
        "lint": "tsc --noEmit",
        "sync": "tsx scripts/sync-assets.ts",
        "drift-check": "tsx scripts/drift-check.ts"
      },
      "dependencies": {
        "@xenova/transformers": "2.17.2",
        "better-sqlite3": "11.5.0",
        "sqlite-vec": "0.1.6"
      },
      "devDependencies": {
        "typescript": "5.6.3",
        "tsx": "4.19.2",
        "@types/node": "22.9.0",
        "@types/better-sqlite3": "7.6.12"
      }
    }
    ```
  - `packages/dfe-agent/tsconfig.json`:
    ```json
    {
      "extends": "../../.opencode/tsconfig.json",
      "compilerOptions": {
        "outDir": "./dist",
        "rootDir": "./src",
        "declaration": true,
        "sourceMap": true
      },
      "include": ["src/**/*"],
      "exclude": ["node_modules", "dist", "tests"]
    }
    ```
  - `packages/dfe-agent/.gitignore`:
    ```
    dist/
    node_modules/
    *.log
    .dfe-agent/
    coverage/
    ```
  - `packages/dfe-agent/src/index.ts`:
    ```ts
    export const VERSION = "0.1.0";
    export { runCli } from "./cli.js";
    export * from "./query/index.js";
    ```
  - `packages/dfe-agent/README.md` placeholder com secao "Status: MVP em desenvolvimento (Sprint 14)".
  - `packages/dfe-agent/CHANGELOG.md` com entrada inicial `## 0.1.0 — Sprint 14 MVP`.
- Testes criticos:
  - [ ] `cat packages/dfe-agent/package.json | jq -r .name` retorna `"@dfe-agent/dfe-agent"` (gate I14.1)
  - [ ] `cat packages/dfe-agent/package.json | jq -r '."engines".node'` retorna `">=20 <23"`
  - [ ] `cd packages/dfe-agent && npm install` retorna exit 0
  - [ ] `cd packages/dfe-agent && npx tsc --noEmit` retorna exit 0 (sem erros de tipo)
  - [ ] `cd packages/dfe-agent && npm run build` gera `dist/index.js` + `dist/index.d.ts`
  - [ ] `pytest tests/ --no-cov --no-header -q` no root continua verde (zero regressao)

### Task A.2 — `.gitignore` raiz + CI matrix

- Agent: dev
- Input: Task A.1 completa.
- Diagnostico:
  - `.gitignore` raiz precisa garantir que `packages/*/dist/` e `packages/*/node_modules/` NAO sao commitados.
  - Mas `packages/dfe-agent/` em si DEVE ser commitado (source).
  - CI matrix precisa de job separado `test-npm-package` para nao contaminar suite Python.
- Output:
  - Edicao `.gitignore` raiz: adicionar `packages/*/dist/` e `packages/*/node_modules/` (sem quebrar patterns existentes).
  - `.github/workflows/test-npm-package.yml` (criar se nao existir `.github/workflows/`):
    ```yaml
    name: test-npm-package
    on: [push, pull_request]
    jobs:
      test:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4
          - uses: actions/setup-node@v4
            with: { node-version: '22' }
          - name: Install deps
            working-directory: packages/dfe-agent
            run: npm ci
          - name: Build
            working-directory: packages/dfe-agent
            run: npm run build
          - name: Drift check
            working-directory: packages/dfe-agent
            run: npm run drift-check
          - name: Test
            working-directory: packages/dfe-agent
            run: npm test
    ```
- Testes criticos:
  - [ ] `cat .gitignore | grep -E "packages.*(dist|node_modules)"` retorna 2+ matches
  - [ ] `find packages/dfe-agent -name "*.ts" -not -path "*/node_modules/*" -not -path "*/dist/*" | wc -l` >= 3 (source versionado)
  - [ ] `find packages/dfe-agent -name "dist" -type d` NAO existe (gate: dist nao versionado)
  - [ ] Workflow file YAML valido (`python -c "import yaml; yaml.safe_load(open('.github/workflows/test-npm-package.yml'))"` exit 0)

---

## Fase B — Empacotar assets (agent.md + SKILL.md) com sync bidirecional (B14.1 + I14.2)

**Criterio**: `packages/dfe-agent/dist/agent.md` e copia exata de `.opencode/agent/dfe-agent.md` **E** `packages/dfe-agent/dist/skill/dfe-fiscal/SKILL.md` e copia exata de `.opencode/skills/dfe-fiscal/SKILL.md`. Drift detectado por teste.

### Task B.1 — Script de sync `sync-assets.ts` (source → dist)

- Agent: dev
- Input: Task A.1 completa.
- Diagnostico:
  - Drift entre fonte canonica (`.opencode/agent/dfe-agent.md`) e copia distribuida (`packages/dfe-agent/dist/agent.md`) e' certo sem automacao.
  - Decisao D9: fonte canonica vive no DFe-Agent root; copia e' regenerada via sync.
- Output:
  - `packages/dfe-agent/scripts/sync-assets.ts`:
    ```ts
    import { readFileSync, writeFileSync, mkdirSync, cpSync } from "node:fs";
    import { resolve, dirname } from "node:path";
    
    const ROOT = resolve(dirname(new URL(import.meta.url).pathname), "../../..");
    const PAIRS = [
      { src: `${ROOT}/.opencode/agent/dfe-agent.md`,
        dst: `${ROOT}/packages/dfe-agent/dist/agent.md` },
      { src: `${ROOT}/.opencode/skills/dfe-fiscal`,
        dst: `${ROOT}/packages/dfe-agent/dist/skill/dfe-fiscal` },
    ];
    
    for (const { src, dst } of PAIRS) {
      mkdirSync(dirname(dst), { recursive: true });
      cpSync(src, dst, { recursive: true });
      console.info(`[sync] copied ${src} -> ${dst}`);
    }
    ```
  - Adicionado em `package.json > scripts.sync`.
- Testes criticos (TDD vermelho primeiro):
  - [ ] `packages/dfe-agent/tests/sync-assets.test.ts`:
    - [ ] cria `dist/agent.md` quando nao existe (assertion: file exists + SHA-256 == source SHA-256)
    - [ ] sobrescreve quando ja existe (assertion: apos 2a chamada, SHA inalterado)
    - [ ] falha com erro claro se source NAO existe (assertion: throws Error com substring "source not found")
    - [ ] preserva encoding UTF-8 com acentos (assertion: source com "Nota Tecnica" == dist com "Nota Tecnica")
    - [ ] copia recursivamente o diretorio skill/ (assertion: `dist/skill/dfe-fiscal/SKILL.md` existe apos sync)
  - [ ] `cd packages/dfe-agent && npm run sync` retorna exit 0
  - [ ] `diff .opencode/agent/dfe-agent.md packages/dfe-agent/dist/agent.md` retorna vazio
  - [ ] `diff .opencode/skills/dfe-fiscal/SKILL.md packages/dfe-agent/dist/skill/dfe-fiscal/SKILL.md` retorna vazio

### Task B.2 — Script de validacao de drift `drift-check.ts` (CI gate)

- Agent: dev
- Input: Task B.1 completa.
- Diagnostico:
  - CI precisa de gate que detecte drift antes de merge, NAO apenas apos `npm run sync` manual.
- Output:
  - `packages/dfe-agent/scripts/drift-check.ts`:
    ```ts
    import { readFileSync } from "node:fs";
    import { createHash } from "node:crypto";
    
    const ROOT = resolve(dirname(new URL(import.meta.url).pathname), "../../..");
    const PAIRS = [
      `${ROOT}/.opencode/agent/dfe-agent.md`,
      `${ROOT}/packages/dfe-agent/dist/agent.md`,
    ];
    
    const sha = (p) => createHash("sha256").update(readFileSync(p)).digest("hex");
    if (sha(PAIRS[0]) !== sha(PAIRS[1])) {
      console.error(`[drift] ${PAIRS[0]} != ${PAIRS[1]}`);
      console.error(`[drift] run 'npm run sync' to regenerate`);
      process.exit(1);
    }
    // mesma logica para SKILL.md
    ```
  - Adicionado em `package.json > scripts.drift-check`.
- Testes criticos:
  - [ ] `packages/dfe-agent/tests/drift-check.test.ts`:
    - [ ] passa quando source == dist (exit 0)
    - [ ] falha quando divergem (exit 1, stderr contem "[drift]")
    - [ ] reporta ambos paths no stderr (util para debug)
  - [ ] Editar `.opencode/agent/dfe-agent.md` (inserir `# dummy` no fim) + `npm run drift-check` → exit 1 (gate B14.1)
  - [ ] `npm run sync && npm run drift-check` → exit 0 novamente

### Task B.3 — Documentar convencao "fonte canonica no root, copia distribuida"

- Agent: dev
- Input: Task B.2 completa.
- Diagnostico:
  - Sem documentacao explicita, proxima sprint que editar `.opencode/agent/dfe-agent.md` esquece de rodar sync.
- Output:
  - `packages/dfe-agent/README.md` secao "Development workflow":
    ```
    ## Development workflow
    A fonte canonica do agent e skill vive no DFe-Agent root:
    - `.opencode/agent/dfe-agent.md`
    - `.opencode/skills/dfe-fiscal/SKILL.md`

    Para distribuir atualizacoes:
    1. Edite a fonte canonica no DFe-Agent root.
    2. Rode `npm run sync` em `packages/dfe-agent/` para copiar para `dist/`.
    3. CI roda `npm run drift-check` para garantir consistencia.

    Drift detectado em CI = PR bloqueado.
    ```
  - Adicionar nota em `AGENTS.md > Padroes de codigo` secao "Convecoes de empacotamento" sobre a regra "agent canonico mora no DFe-Agent root; copia distribuida via sync-assets; drift-check no CI".
- Testes criticos:
  - [ ] `grep -l "sync-assets" packages/dfe-agent/README.md` retorna 1+ matches
  - [ ] `grep -A 3 "Convecoes de empacotamento" AGENTS.md` retorna 1+ matches
  - [ ] Markdown lint em `packages/dfe-agent/README.md` retorna 0 erros

---

## Fase C — CLI Node: `dfe-agent install | update | query | status` (B14.2 + I14.4)

**Criterio**: `npx dfe-agent --help` mostra os 4 subcommands **E** `npx dfe-agent install` em scratch project copia agent + skill para `.opencode/` **E** `npx dfe-agent status` mostra versao + base path + mtime **E** `npx dfe-agent query "..."` retorna JSON `{answer, sources[]}` com fontes citadas.

### Task C.1 — CLI skeleton + subcommand `install`

- Agent: dev
- Input: Task A.1 + Task B.1 (assets disponiveis em `dist/`).
- Diagnostico:
  - `node:util.parseArgs` (Node 20+) substitui `commander`/`yargs` — zero deps adicionais.
  - Subcommand `install` precisa copiar agent + skill preservando arvore de diretorios.
- Output:
  - `packages/dfe-agent/src/cli.ts`:
    ```ts
    import { parseArgs } from "node:util";
    import { install } from "./commands/install.js";
    import { update } from "./commands/update.js";
    import { query } from "./commands/query.js";
    import { status } from "./commands/status.js";
    
    export async function runCli(argv: string[]): Promise<number> {
      const { values, positionals } = parseArgs({
        args: argv,
        options: {
          auto: { type: "boolean", default: false },
          help: { type: "boolean", short: "h", default: false },
        },
        allowPositionals: true,
      });
      
      if (values.help || positionals.length === 0) {
        console.log(USAGE);
        return 0;
      }
      
      const [cmd] = positionals;
      switch (cmd) {
        case "install": return install({ autoSetup: values.auto });
        case "update":  return update({});
        case "query":   return query({ question: positionals[1] ?? "" });
        case "status":  return status({});
        default:
          console.error(`[dfe-agent] unknown command: ${cmd}`);
          return 1;
      }
    }
    ```
  - `packages/dfe-agent/src/commands/install.ts`:
    ```ts
    import { cpSync, existsSync, mkdirSync } from "node:fs";
    import { resolve } from "node:path";
    import { fileURLToPath } from "node:url";
    
    const PKG_ROOT = resolve(fileURLToPath(import.meta.url), "../../..");
    
    export function install(opts: { autoSetup: boolean }): number {
      const target = resolve(process.cwd(), ".opencode");
      mkdirSync(`${target}/agent`, { recursive: true });
      mkdirSync(`${target}/skills/dfe-fiscal`, { recursive: true });
      cpSync(`${PKG_ROOT}/dist/agent.md`, `${target}/agent/dfe-agent.md`);
      cpSync(`${PKG_ROOT}/dist/skill/dfe-fiscal`, `${target}/skills/dfe-fiscal`,
             { recursive: true });
      console.info(`[dfe-agent] installed agent + skill in ${target}`);
      if (opts.autoSetup) {
        // chama update() em sequencia
        return require("./update.js").update({});
      }
      return 0;
    }
    ```
- Testes criticos:
  - [ ] `packages/dfe-agent/tests/cli/install.test.ts`:
    - [ ] copia `agent/dfe-agent.md` + `skills/dfe-fiscal/SKILL.md` em scratch project limpo (`os.tmpdir()` + `fs.mkdtempSync`)
    - [ ] sobrescreve sem warning se ja existe (re-install = mesmo SHA)
    - [ ] falha com exit 1 se target dir NAO pode ser criado (mock com perm 000)
    - [ ] `--auto-setup` chama `update()` sequencialmente (spy em `update`)
    - [ ] `--help` imprime usage com 4 subcommands listados
    - [ ] exit code 0 em sucesso, 1 em erro I/O, 2 em target invalido

### Task C.2 — Subcommand `update` (download base RAG)

- Agent: dev
- Input: Task C.1 completa + Fase D em andamento (depende de D.1 workflow existir).
- Diagnostico:
  - GitHub Releases API: `GET https://api.github.com/repos/<owner>/DFe-Agent/releases/latest` retorna JSON com `assets[]`.
  - Asset names canonicos: `dfe.db.gz` + `dfe.db.gz.sha256`.
  - Atomic write: `dfe.db.tmp` → rename evita base corrompida em mid-download.
  - Fallback seed: se GitHub inacessivel ou rate-limited, usa `dist/seed/dfe.db.gz` (Task D.2).
- Output:
  - `packages/dfe-agent/src/commands/update.ts`:
    ```ts
    import { createHash } from "node:crypto";
    import { gunzipSync } from "node:zlib";
    import { existsSync, writeFileSync, renameSync } from "node:fs";
    import { resolve } from "node:path";
    import { tmpdir } from "node:os";
    
    const GH_API = "https://api.github.com/repos/dfe-agent/DFe-Agent/releases/latest";
    
    export async function update(opts: {}): Promise<number> {
      const baseDir = process.env.DFE_AGENT_BASE_DIR
        ?? resolve(process.env.HOME ?? tmpdir(), ".dfe-agent");
      const dbPath = resolve(baseDir, "dfe.db");
      
      // 1. fetch release metadata
      const release = await fetchJson(GH_API);
      const asset = release.assets.find((a) => a.name === "dfe.db.gz");
      if (!asset) { console.error("[dfe-agent] no dfe.db.gz asset"); return 3; }
      const shaAsset = release.assets.find((a) => a.name === "dfe.db.gz.sha256");
      
      // 2. download
      const gz = Buffer.from(await (await fetch(asset.browser_download_url)).arrayBuffer());
      const expectedSha = (await (await fetch(shaAsset.browser_download_url)).text()).trim();
      
      // 3. verify SHA-256
      const actualSha = createHash("sha256").update(gz).digest("hex");
      if (actualSha !== expectedSha) {
        console.error(`[dfe-agent] SHA mismatch: expected ${expectedSha}, got ${actualSha}`);
        return 3;
      }
      
      // 4. atomic write
      const tmpPath = `${dbPath}.tmp`;
      writeFileSync(tmpPath, gunzipSync(gz));
      renameSync(tmpPath, dbPath);
      console.info(`[dfe-agent] base updated: ${dbPath}`);
      return 0;
    }
    ```
- Testes criticos:
  - [ ] `packages/dfe-agent/tests/cli/update.test.ts`:
    - [ ] sucesso: mock fetch retorna asset valido, exit 0, arquivo escrito (assertion: `existsSync(dbPath)` + PRAGMA `user_version >= 6`)
    - [ ] SHA mismatch: mock retorna hash divergente, exit 3, stderr contem "SHA mismatch"
    - [ ] sem asset: mock release sem `dfe.db.gz`, exit 3, stderr contem "no dfe.db.gz"
    - [ ] `DFE_AGENT_BASE_DIR=/custom/path` resolve path custom (assertion: arquivo em `/custom/path/dfe.db`, NAO em `~/.dfe-agent/`)
    - [ ] GitHub inacessivel: fetch throws, fallback para seed bundled em `dist/seed/dfe.db.gz` (mock com `fetch` que rejeita)
    - [ ] PRAGMA `user_version` >= 6 apos write (gate B14.3)

### Task C.3 — Subcommand `query "<pergunta>"`

- Agent: dev
- Input: Task C.2 completa + Fase E (engine) completa.
- Output:
  - `packages/dfe-agent/src/commands/query.ts`:
    ```ts
    import { search } from "../query/index.js";
    
    export async function query(opts: { question: string; mode?: string }): Promise<number> {
      const result = await search(opts.question, { mode: opts.mode ?? "semantic" });
      console.log(JSON.stringify(result, null, 2));
      return result.answer === "Nao encontrei base para responder" && result.sources.length === 0
        ? 0  // NO_EVIDENCE_MESSAGE ainda e' success exit
        : 0;
    }
    ```
- Testes criticos:
  - [ ] `packages/dfe-agent/tests/cli/query.test.ts`:
    - [ ] output JSON valido com chaves `answer` + `sources`
    - [ ] `answer === "Nao encontrei base para responder"` literal quando `has_sufficient_evidence = false` (gate dfe-rules.md #4)
    - [ ] `sources[]` tem 1+ items, cada um com `url` http/https valida
    - [ ] cache hit na 2a chamada idêntica (spy em `embedder.encode` chamado 1x, NAO 2x)
    - [ ] exit 0 mesmo em NO_EVIDENCE_MESSAGE (NAO e' erro)

### Task C.4 — Subcommand `status`

- Agent: dev
- Input: Task C.1 + C.2.
- Output:
  - `packages/dfe-agent/src/commands/status.ts`:
    ```ts
    import { existsSync, statSync } from "node:fs";
    import Database from "better-sqlite3";
    import { resolve } from "node:path";
    import { tmpdir } from "node:os";
    
    export function status(opts: { json?: boolean }): number {
      const baseDir = process.env.DFE_AGENT_BASE_DIR
        ?? resolve(process.env.HOME ?? tmpdir(), ".dfe-agent");
      const dbPath = resolve(baseDir, "dfe.db");
      const exists = existsSync(dbPath);
      
      const info: Record<string, unknown> = {
        version: "0.1.0",
        basePath: dbPath,
        baseExists: exists,
      };
      if (exists) {
        const db = new Database(dbPath, { readonly: true });
        info.baseMtime = statSync(dbPath).mtime.toISOString();
        info.baseDocCount = db.prepare("SELECT COUNT(*) as c FROM documents").get().c;
        info.baseEmbeddingModel = process.env.DFE_EMBEDDING_MODEL
          ?? "paraphrase-multilingual-MiniLM-L12-v2";
        db.close();
      }
      console.log(JSON.stringify(info, null, 2));
      return 0;
    }
    ```
- Testes criticos:
  - [ ] `packages/dfe-agent/tests/cli/status.test.ts`:
    - [ ] `baseExists=false` quando path NAO existe
    - [ ] `baseExists=true`, `baseDocCount=N` (mock DB com 5 docs)
    - [ ] `DFE_AGENT_BASE_DIR` override reflete em `basePath` no output

---

## Fase D — RAG base portatil + hosting (B14.3 + P14.1)

**Criterio**: workflow GitHub Actions publica `dfe.db.gz` + `dfe.db.gz.sha256` como assets em todo tag `v*.*.*` do DFe-Agent **E** `npx dfe-agent update` baixa o ultimo release e popula base no consumidor **E** paridade embeddings Py↔Node >= 0.99.

### Task D.1 — Script `publish-base.yml` (GitHub Actions)

- Agent: dev
- Input: nenhuma (depende apenas de CI do DFe-Agent).
- Diagnostico:
  - DFe-Agent ja tem CI (verificar `.github/workflows/`).
  - `python -m src.ragctl migrate && python -m src.collector --once && python -m src.indexer.ingest` sao os comandos canonicos para gerar base (SKILL.md:13-39).
- Output:
  - `.github/workflows/publish-base.yml`:
    ```yaml
    name: publish-base
    on:
      push:
        tags: ['v*.*.*']
    jobs:
      build-and-publish:
        runs-on: ubuntu-latest
        permissions:
          contents: write
        steps:
          - uses: actions/checkout@v4
          - uses: actions/setup-python@v5
            with: { python-version: '3.11' }
          - name: Install deps
            run: pip install -r requirements.txt
          - name: Migrate
            run: python -m src.ragctl migrate
          - name: Collect
            run: python -m src.collector --once
          - name: Ingest
            run: python -m src.indexer.ingest --chunker=structural
          - name: Gzip
            run: gzip -c storage/dfe.db > dfe.db.gz
          - name: SHA-256
            run: sha256sum dfe.db.gz > dfe.db.gz.sha256
          - uses: softprops/action-gh-release@v2
            with:
              files: |
                dfe.db.gz
                dfe.db.gz.sha256
    ```
- Testes criticos:
  - [ ] Workflow YAML valido (`python -c "import yaml; yaml.safe_load(open('.github/workflows/publish-base.yml'))"` exit 0)
  - [ ] Manual run em tag de teste (`v0.0.0-test`) gera assets (verificavel em GitHub Releases)

### Task D.2 — Seed bundled para first-run offline

- Agent: dev
- Input: Task D.1 completa.
- Diagnostico:
  - First-run com rede off: consumidor cai em fallback.
  - Snapshot manual: regenerar seed a cada minor release (Task F.3 do CHANGELOG).
- Output:
  - `packages/dfe-agent/src/seed/dfe.db.gz` (snapshot da base em data X — gerado manualmente via `gzip -c storage/dfe.db > ...` apos Sprint 14 fechar).
  - Adicionar em `packages/dfe-agent/.gitignore` regra `!src/seed/dfe.db.gz` (forçar versionamento do asset).
  - Documentado em README: "seed bundled cobre ate <data>; rode `dfe-agent update` para latest".
- Testes criticos:
  - [ ] `ls -lh packages/dfe-agent/src/seed/dfe.db.gz` reporta tamanho
  - [ ] `zcat packages/dfe-agent/src/seed/dfe.db.gz | sqlite3 :memory: "PRAGMA user_version"` retorna versao >= 6
  - [ ] `git check-ignore packages/dfe-agent/src/seed/dfe.db.gz` retorna exit 1 (asset NAO ignorado)

### Task D.3 — Validacao de paridade Py <-> Node embeddings (B14.3 gate)

- Agent: dev
- Input: Task D.2 + Fase E em paralelo (gate de paridade antes de merge).
- Diagnostico:
  - Drift entre `sentence-transformers` (Py, Sprint 5 default) e `@xenova/transformers` (Node) precisa ser validado para garantir que base Py e' consumida corretamente por query engine Node.
- Output:
  - `tests/integration/test_embedding_parity.py` (Py, no DFe-Agent root):
    ```python
    import json
    from pathlib import Path
    from sentence_transformers import SentenceTransformer
    
    model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    sentences = json.loads(Path("tests/fixtures/eval_sentences.json").read_text())
    embeddings = model.encode(sentences).tolist()
    Path("tests/fixtures/embeddings_py.json").write_text(json.dumps(embeddings))
    ```
  - `packages/dfe-agent/tests/integration/test_embedding_parity.test.ts` (Node):
    ```ts
    import { test } from "node:test";
    import assert from "node:assert/strict";
    import { pipeline } from "@xenova/transformers";
    import { readFileSync } from "node:fs";
    
    test("Py <-> Node embeddings cosine similarity >= 0.99", async () => {
      const py = JSON.parse(readFileSync("../../../tests/fixtures/embeddings_py.json", "utf8"));
      const sentences = JSON.parse(readFileSync("../../../tests/fixtures/eval_sentences.json", "utf8"));
      const extractor = await pipeline("feature-extraction", "Xenova/paraphrase-multilingual-MiniLM-L12-v2");
      const nodeEmbeddings = await Promise.all(
        sentences.map((s) => extractor(s, { pooling: "mean", normalize: true }))
      );
      const sims = py.map((p, i) => cosineSimilarity(p, Array.from(nodeEmbeddings[i].data)));
      const meanSim = sims.reduce((a, b) => a + b, 0) / sims.length;
      assert.ok(meanSim >= 0.99, `mean cosine similarity ${meanSim} < 0.99`);
    });
    ```
- Testes criticos:
  - [ ] Suite Node passa com `meanSim >= 0.99`
  - [ ] Suite Py roda em CI (Python 3.11 + sentence-transformers) e gera fixture
  - [ ] Se drift > 0.01: gate falha; investigar tokenizer mismatch (Sprint 15+ follow-up)

---

## Fase E — Query engine Node (port de `src/query/query_engine.py`) (I14.3)

**Criterio**: `queryEngine.search(pergunta, {mode})` em Node retorna o mesmo `{answer, sources[]}` que `python -m src.query "<mesma pergunta>"` para as 10 perguntas do `eval_set.json` (Spearman correlation entre ranks >= 0.8).

### Task E.1 — Vector search (sqlite-vec + @xenova/transformers)

- Agent: dev
- Input: Task D.3 (paridade validada).
- Output:
  - `packages/dfe-agent/src/query/embedder.ts`:
    ```ts
    import { pipeline, env } from "@xenova/transformers";
    import { createHash } from "node:crypto";
    
    env.allowLocalModels = false;
    const CACHE = new Map<string, Float32Array>();
    
    export async function encode(text: string): Promise<Float32Array> {
      const key = hashText(text);
      if (CACHE.has(key)) return CACHE.get(key)!;
      const extractor = await pipeline("feature-extraction", "Xenova/paraphrase-multilingual-MiniLM-L12-v2");
      const out = await extractor(text, { pooling: "mean", normalize: true });
      const vec = new Float32Array(out.data);
      CACHE.set(key, vec);
      if (CACHE.size > 128) {
        const firstKey = CACHE.keys().next().value;
        CACHE.delete(firstKey);
      }
      return vec;
    }
    ```
  - `packages/dfe-agent/src/query/vectorSearch.ts`:
    ```ts
    import Database from "better-sqlite3";
    import * as sqliteVec from "sqlite-vec";
    
    export function vectorSearch(db: Database.Database, queryVec: Float32Array, k: number) {
      sqliteVec.load(db);
      const rows = db.prepare(`
        SELECT chunk_id, distance
        FROM vec_chunks
        WHERE embedding MATCH ?
        ORDER BY distance
        LIMIT ?
      `).all(queryVec, k);
      return rows;
    }
    ```
- Testes criticos:
  - [ ] `packages/dfe-agent/tests/query/vectorSearch.test.ts`:
    - [ ] embedder cache hit (2a chamada = 0ms, 1 inferencia)
    - [ ] LRU eviction apos 128 entradas
    - [ ] top-K respeitado (k=5 retorna 5 rows)
    - [ ] cosine distance monotonic (menor distance = mais similar)
  - [ ] `packages/dfe-agent/tests/query/embedder.test.ts`:
    - [ ] modelo carregado 1x (singleton via `pipeline()` cache do @xenova/transformers)
    - [ ] output dimensao = 384 (gate D6)

### Task E.2 — FTS5 search (BM25)

- Agent: dev
- Input: Task E.1 (independente em escopo).
- Output:
  - `packages/dfe-agent/src/query/ftsSearch.ts`:
    ```ts
    export function ftsSearch(db: Database.Database, query: string, k: number) {
      const ftsQuery = query.replace(/[^a-zA-Z0-9\s]/g, " ").trim();
      const rows = db.prepare(`
        SELECT chunk_id, bm25(fts_chunks) AS score
        FROM fts_chunks
        WHERE fts_chunks MATCH ?
        ORDER BY score
        LIMIT ?
      `).all(ftsQuery, k);
      return rows;
    }
    ```
- Testes criticos:
  - [ ] `packages/dfe-agent/tests/query/ftsSearch.test.ts`:
    - [ ] BM25 retorna rows para termos literais ("NF-e" retorna >=1 chunk)
    - [ ] phrase query `"nota tecnica"` retorna apenas matches exatos
    - [ ] tokenizacao PT: "Nota Tecnica" == "nota tecnica" == "nota  tecnica" (case + whitespace insensitive)
    - [ ] stopwords PT removidas ("de", "para", "em" — opcional, depende do tokenizer do FTS5)

### Task E.3 — Modo hibrido (RRF k=60 entre vector + FTS5)

- Agent: dev
- Input: Tasks E.1 + E.2 completas.
- Output:
  - `packages/dfe-agent/src/query/hybrid.ts`:
    ```ts
    export function rrf(vectorHits: Hit[], ftsHits: Hit[], k: number, k0 = 60): Hit[] {
      const scores = new Map<number, number>();
      vectorHits.forEach((h, i) => scores.set(h.chunk_id,
        (scores.get(h.chunk_id) ?? 0) + 1 / (k0 + i + 1)));
      ftsHits.forEach((h, i) => scores.set(h.chunk_id,
        (scores.get(h.chunk_id) ?? 0) + 1 / (k0 + i + 1)));
      return Array.from(scores.entries())
        .sort(([, a], [, b]) => b - a)
        .slice(0, k)
        .map(([chunk_id, score]) => ({ chunk_id, score }));
    }
    ```
- Testes criticos:
  - [ ] `packages/dfe-agent/tests/query/hybrid.test.ts`:
    - [ ] overlap de docs ranqueados mais alto (mesmo doc em vector + FTS = score somado)
    - [ ] docs exclusivos de um modo aparecem (rank mais baixo, mas score > 0)
    - [ ] k=60 canonico (comparacao com golden fixture `tests/fixtures/hybrid_expected.json`)
    - [ ] ordem estavel: 2 chamadas identicas = mesmo output

### Task E.4 — Cache de query embedding (HIT na 2a)

- Agent: dev
- Input: Task E.1 completa.
- Output:
  - `packages/dfe-agent/src/query/cache.ts`:
    ```ts
    import Database from "better-sqlite3";
    import { createHash } from "node:crypto";
    
    const hash = (model: string, mode: string, q: string) =>
      createHash("sha256").update(`${model}|${mode}|${q.trim().toLowerCase()}`).digest("hex");
    
    export class QueryCache {
      constructor(private db: Database.Database) {
        this.db.exec(`CREATE TABLE IF NOT EXISTS query_cache (
          query_hash TEXT PRIMARY KEY,
          embedding BLOB,
          created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )`);
      }
      
      get(model: string, mode: string, q: string): Float32Array | null {
        const row = this.db.prepare("SELECT embedding FROM query_cache WHERE query_hash = ?")
          .get(hash(model, mode, q)) as { embedding: Buffer } | undefined;
        return row ? new Float32Array(row.embedding.buffer,
          row.embedding.byteOffset, row.embedding.byteLength / 4) : null;
      }
      
      set(model: string, mode: string, q: string, embedding: Float32Array): void {
        this.db.prepare(`INSERT OR REPLACE INTO query_cache (query_hash, embedding)
                         VALUES (?, ?)`)
          .run(hash(model, mode, q), Buffer.from(embedding.buffer));
      }
    }
    ```
- Testes criticos:
  - [ ] `packages/dfe-agent/tests/query/cache.test.ts`:
    - [ ] miss na 1a chamada (spy em `embedder.encode` chamado)
    - [ ] hit na 2a chamada (spy NAO chamado, mas resultado identico)
    - [ ] hit mesmo com espacos/capitalizacao diferentes ("O que é NF-e  " == "o que é nf-e")
    - [ ] miss quando modelo muda (`DFE_EMBEDDING_MODEL=all-MiniLM-L6-v2`)
    - [ ] tabela `query_cache` criada automaticamente (idempotente em 2a instancia)

### Task E.5 — `queryEngine.search()` orquestrador + contrato `{answer, sources}`

- Agent: dev
- Input: Tasks E.1 + E.2 + E.3 + E.4.
- Output:
  - `packages/dfe-agent/src/query/contextBuilder.ts`:
    ```ts
    export function buildContext(chunks: Chunk[]): { answer: string; sources: Source[] } {
      if (chunks.length === 0) return { answer: NO_EVIDENCE_MESSAGE, sources: [] };
      const sources = dedupByDoc(chunks).map((c) => ({ url: c.url, title: c.title, score: c.score }));
      const answer = chunks.map((c) => c.text).join("\n\n");
      return { answer, sources };
    }
    ```
  - `packages/dfe-agent/src/query/index.ts`:
    ```ts
    export const NO_EVIDENCE_MESSAGE = "Nao encontrei base para responder";
    
    export async function search(question: string, opts: { mode?: string; topK?: number } = {}) {
      const db = openBase();
      const mode = opts.mode ?? "semantic";
      const k = opts.topK ?? 10;
      
      const cached = cache.get(MODEL, mode, question);
      const queryVec = cached ?? await encode(question);
      if (!cached) cache.set(MODEL, mode, question, queryVec);
      
      let hits: Hit[];
      if (mode === "hybrid") hits = rrf(vectorSearch(db, queryVec, k), ftsSearch(db, question, k), k);
      else hits = vectorSearch(db, queryVec, k);
      
      const chunks = hydrate(db, hits);
      return buildContext(chunks);
    }
    ```
- Testes criticos:
  - [ ] `packages/dfe-agent/tests/query/index.test.ts`:
    - [ ] modo default = "semantic" (nao precisa flag)
    - [ ] `mode=hybrid` funde vector + FTS (verificacao indireta: resultados diferentes de semantic puro)
    - [ ] `NO_EVIDENCE_MESSAGE` literal quando 0 chunks (gate dfe-rules.md #4)
    - [ ] `sources` sempre presente (mesmo que `[]`)
    - [ ] Spearman correlation com Py >= 0.8 para 10 perguntas de `tests/fixtures/eval_set.json`

---

## Fase F — Publicacao + CI + E2E em scratch project (B14.1 + P14.2)

**Criterio**: `npm view @dfe-agent/dfe-agent version` retorna versao **E** `npm install @dfe-agent/dfe-agent && npx dfe-agent install && npx dfe-agent update && npx dfe-agent query "O que e a NF-e?"` em projeto limpo retorna JSON valido com fontes citadas **E** suite pytest DFe-Agent root continua verde.

### Task F.1 — GitHub Actions: CI matrix + publish-on-tag

- Agent: dev
- Input: Fases A-E completas.
- Diagnostico:
  - Publicacao requer secret `NPM_TOKEN` (configurar em GitHub repo settings).
  - Provenance statements (`--provenance`) requerem npm 9+ + trusted publisher OU CI token.
- Output:
  - `.github/workflows/test-npm-package.yml` (ja' criado em A.2; verificar que dispara em PRs).
  - `.github/workflows/publish-npm.yml`:
    ```yaml
    name: publish-npm
    on:
      push:
        tags: ['packages-v*.*.*']
    jobs:
      publish:
        runs-on: ubuntu-latest
        permissions:
          contents: write
          id-token: write  # para provenance
        steps:
          - uses: actions/checkout@v4
          - uses: actions/setup-node@v4
            with:
              node-version: '22'
              registry-url: 'https://registry.npmjs.org'
          - name: Sync assets
            working-directory: packages/dfe-agent
            run: npm run sync
          - name: Drift check
            working-directory: packages/dfe-agent
            run: npm run drift-check
          - name: Build
            working-directory: packages/dfe-agent
            run: npm run build
          - name: Test
            working-directory: packages/dfe-agent
            run: npm test
          - name: Publish
            working-directory: packages/dfe-agent
            run: npm publish --access public --provenance
            env:
              NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
    ```
- Testes criticos:
  - [ ] CI matrix verde em PR de teste
  - [ ] Workflow YAML valido (`yaml.safe_load`)
  - [ ] Tag `packages-v0.1.0` dispara workflow (validar manualmente com tag dummy `packages-v0.0.0-test`)

### Task F.2 — Smoke test E2E em scratch project

- Agent: dev
- Input: Task F.1 completa.
- Output:
  - `packages/dfe-agent/tests/e2e/scratch-project-test.sh`:
    ```bash
    #!/usr/bin/env bash
    set -euo pipefail
    
    SCRATCH=$(mktemp -d)
    cd "$SCRATCH"
    
    echo "[e2e] npm init"
    npm init -y > /dev/null
    
    echo "[e2e] npm install (local tarball)"
    PKG_TARBALL=$(npm pack --workspace packages/dfe-agent 2>/dev/null | tail -1)
    npm install "./$PKG_TARBALL" > /dev/null
    
    echo "[e2e] dfe-agent install"
    npx dfe-agent install
    
    echo "[e2e] validate .opencode/"
    test -f .opencode/agent/dfe-agent.md
    test -f .opencode/skills/dfe-fiscal/SKILL.md
    
    echo "[e2e] dfe-agent status"
    npx dfe-agent status | jq -e '.baseExists'
    
    echo "[e2e] dfe-agent query"
    OUT=$(npx dfe-agent query "O que e a NF-e?")
    echo "$OUT" | jq -e '.answer'
    echo "$OUT" | jq -e '.sources | length >= 1'
    
    rm -rf "$SCRATCH"
    echo "[e2e] PASS"
    ```
  - Adicionado em `package.json > scripts.test:e2e`.
- Testes criticos:
  - [ ] Script executa em CI com exit 0 (validado em `test-npm-package` workflow com flag `e2e: true`)
  - [ ] JSON parseado contem chave `answer` nao-vazia
  - [ ] JSON parseado contem `sources` array com 1+ items, cada um com `url` http/https

### Task F.3 — README canonico + CHANGELOG

- Agent: dev
- Input: Task F.2 completa.
- Output:
  - `packages/dfe-agent/README.md` (reescrito):
    ```
    # @dfe-agent/dfe-agent

    Agente opencode + base RAG com documentacao fiscal eletronica oficial brasileira
    (NF-e, NFC-e, CT-e, MDF-e, SPED). Para outros projetos opencode que querem
    responder perguntas sobre DFes sem clonar o DFe-Agent inteiro.

    ## Install
    ```bash
    npm install @dfe-agent/dfe-agent
    npx dfe-agent install  # copia agent + skill para .opencode/
    npx dfe-agent update   # baixa base RAG (~30MB)
    ```

    ## Quick start
    ```bash
    npx dfe-agent query "O que e a NF-e?"
    # ou via opencode TUI: abra o projeto e selecione @dfe-agent
    ```

    ## Updating the base
    ```bash
    npx dfe-agent update
    ```

    ## Custom base path
    ```bash
    DFE_AGENT_BASE_DIR=/custom/path npx dfe-agent update
    ```

    ## Troubleshooting
    - "no dfe.db.gz asset" → GitHub Release nao publicado ainda; aguarde proximo release do DFe-Agent
    - "SHA mismatch" → base corrompida no download; rode `npx dfe-agent update` novamente
    - "PRAGMA user_version < 6" → base antiga; force update

    ## Development
    Veja [DFe-Agent repo](https://github.com/dfe-agent/DFe-Agent) — fonte canonica.
    Editar `.opencode/agent/dfe-agent.md` ou `.opencode/skills/dfe-fiscal/SKILL.md`
    e rodar `npm run sync` em `packages/dfe-agent/` antes de commit.
    ```
  - `packages/dfe-agent/CHANGELOG.md` com entrada:
    ```
    ## 0.1.0 — 2026-XX-XX (Sprint 14 MVP)

    ### Added
    - Pacote npm `@dfe-agent/dfe-agent` com agent + skill + CLI Node
    - Subcommands `install`, `update`, `query`, `status`
    - Base RAG via GitHub Releases + seed bundled
    - Query engine Node port de `src/query/query_engine.py` com paridade validada
    ```
- Testes criticos:
  - [ ] `markdownlint packages/dfe-agent/README.md` retorna 0 erros
  - [ ] README tem 6 secoes obrigatorias (Install, Quick start, Updating, Custom base path, Troubleshooting, Development)

### Task F.4 — Documentar integracao no AGENTS.md + SPEC.md + SKILL.md

- Agent: dev
- Input: Task F.3 completa.
- Output:
  - `AGENTS.md` nova secao "Distribuicao como pacote npm":
    ```
    ## Distribuicao como pacote npm

    Desde Sprint 14, o agente `dfe-agent` e distribuido como `@dfe-agent/dfe-agent` no npm.
    Outros projetos opencode consomem via:
    ```bash
    npm install @dfe-agent/dfe-agent
    npx dfe-agent install
    npx dfe-agent update
    ```

    Layout canonico: `packages/dfe-agent/` (mono-repo). Source em
    `.opencode/agent/dfe-agent.md` (DFe-Agent root); copia distribuida via
    `packages/dfe-agent/scripts/sync-assets.ts`. Drift-check no CI via
    `npm run drift-check`.
    ```
  - `SPEC.md` nota na secao "Stack" sobre distribuicao npm.
  - `.opencode/skills/dfe-fiscal/SKILL.md` secao "Contexto de uso" adicionada:
    ```
    ## Contexto de uso (Sprint 14+)

    Esta skill tem 2 modos de invocacao dependendo do contexto:

    ### Em DFe-Agent root (desenvolvimento)
    ```bash
    python -m src.query "<pergunta>" --mode=hybrid
    ```

    ### Em consumidor npm (`@dfe-agent/dfe-agent`)
    ```bash
    npx dfe-agent query "<pergunta>" --mode=hybrid
    ```

    O contrato de saida e identico: `{answer, sources[]}`. A escolha do modo
    depende apenas do `cwd` (root DFe-Agent vs projeto consumidor).
    ```
- Testes criticos:
  - [ ] `grep -l "@dfe-agent/dfe-agent" AGENTS.md SPEC.md packages/dfe-agent/README.md` retorna 3+ matches
  - [ ] `grep -A 5 "Contexto de uso" .opencode/skills/dfe-fiscal/SKILL.md` retorna secao presente

---

## Verificacao manual (executar no fim da sprint, antes de tag `packages-v0.1.0`)

```bash
# 1. Setup local do pacote
cd packages/dfe-agent
npm ci
npm run sync
npm run build
npm run drift-check
npm test

# 2. Smoke E2E em scratch project
mkdir /tmp/scratch-dfe && cd /tmp/scratch-dfe
npm init -y > /dev/null
npm install /path/to/DFe-Agent/packages/dfe-agent
npx dfe-agent install
npx dfe-agent update
npx dfe-agent query "O que e a NF-e?"
npx dfe-agent status

# 3. Validar regressao no DFe-Agent root
cd /path/to/DFe-Agent
pytest tests/ --cov=src --cov-fail-under=80

# 4. Publicar (CI)
git tag packages-v0.1.0
git push origin packages-v0.1.0
# GitHub Actions publica em https://www.npmjs.com/package/@dfe-agent/dfe-agent

# 5. Confirmar publicacao
npm view @dfe-agent/dfe-agent version
# esperado: 0.1.0
```

---

## Apendice A — Riscos

| Risco | Probabilidade | Impacto | Mitigacao |
|---|---|---|---|
| Drift de embeddings Py <-> Node invalida base | Media | Alto | Task D.3 gate de paridade (cosine >= 0.99); se falhar, regenerar base 100% em Node (re-rodar `python -m src.collector --once` em CI Node + gerar embeddings ONNX no momento do publish, NAO consumir base Py) |
| Tamanho do pacote npm excede 50MB (limite soft) | Media | Medio | D5 (GitHub Releases download) — pacote final ~5MB (bin CLI + agent.md + SKILL.md + seed mini). Base vem do release, NAO bundled completo |
| GitHub rate limits no `update` (60 req/h sem auth) | Baixa | Medio | Token de GitHub via env `GITHUB_TOKEN` (free tier 5000 req/h); fallback para seed bundled se rate-limited |
| Consumidores em Windows com `sqlite-vec` nativo quebra | Media | Alto | Usar `sqlite-vec-windows-x64` (ja' em `.opencode/node_modules/`); testar em Windows no CI matrix (runner `windows-latest`). Engines node >= 20 < 23 (pin) |
| `@xenova/transformers` falha ao carregar ONNX em Node 22.21.1 (issue conhecida em `.opencode/`) | Alta | Alto | Pin Node engine >= 20 < 23 em `package.json`; documentar em README "Node 22.21.1 tem issue conhecida; use 22.9 LTS ou 20.x"; fallback `DFE_EMBEDDING_DTYPE=float16` (se implementado) |
| Sprint 14+ mexe em `.opencode/agent/dfe-agent.md` e esquece de rodar sync | Alta | Medio | Task B.2 drift-check no CI + pre-commit hook (Task F.1) que rejeita commit se drift |
| Usuario roda `npx dfe-agent install` em projeto que ja tem agent custom | Baixa | Medio | Install sobrescreve sem warning (decisao B.1 design) — documentar em README; follow-up Sprint 15+: flag `--no-overwrite` |
| Escopo da Fase E incha (re-porter 13 sprints de Py para TS) | Alta | Alto | Decompor E em 5 tasks granulares; cada task entrega'vel independentemente; se E.3 (RRF) atrasar, MVP lanca so' com E.1 (vector) |
| Parity test (D.3) flake no CI por race condition no download de modelo ONNX | Media | Medio | Pin versao do modelo no cache; usar `env.localModelPath` se necessario |
| SKILL.md comecar a divergir entre DFe-Agent root e npm package | Media | Alto | B.2 drift-check cobre; CI falha PR |

---

## Apendice B — Fora de escopo

- Re-implementar collector/indexer em Node (Task 5+ follow-up Sprint 15+)
- Suporte a Windows ARM64 (sqlite-vec nao tem build oficial; documentar como follow-up)
- API HTTP (`POST /query`) — continua fora de escopo do SPEC.md
- Multi-tenant (uma base por usuario OK; multiplos perfis no mesmo usuario NAO)
- Embeddings via API externa (OpenAI, Cohere) — viola "100% local" do SPEC.md
- Sincronizacao em tempo real da base (consumer precisa rodar `dfe-agent update` manualmente)
- Internacionalizacao EN do agent (`dfe-agent.md` continua PT-only; documentacao EN pode ser follow-up)
- Migracao de bases antigas (v5 -> v6) no consumidor — responsabilidade do DFe-Agent root
- Suporte a `dfe-agent build` (regenerar base localmente em Node) — Sprint 15+
- Versionamento CalVer (considerado em D9, descartado a favor de SemVer)

---

## Apendice C — Comandos shell para reproduzir Sprint 14 manualmente

```bash
# === Local ===
cd packages/dfe-agent
npm ci
npm run sync
npm run build
npm run drift-check
npm test
npm run test:e2e

# === Smoke em scratch project ===
mkdir /tmp/scratch-dfe && cd /tmp/scratch-dfe
npm init -y
npm install /path/to/DFe-Agent/packages/dfe-agent
npx dfe-agent install
npx dfe-agent update
npx dfe-agent query "O que e a NF-e?"
npx dfe-agent status

# === Publicar (CI) ===
git tag packages-v0.1.0
git push origin packages-v0.1.0
# GitHub Actions publica automaticamente em https://www.npmjs.com/package/@dfe-agent/dfe-agent

# === Validar regressao no DFe-Agent root ===
cd /path/to/DFe-Agent
pytest tests/ --cov=src --cov-fail-under=80
pytest tests/integration/test_opencode_config.py -v  # gate de config

# === Validar paridade embeddings ===
pytest tests/integration/test_embedding_parity.py -v  # Py
cd packages/dfe-agent && npm test -- embedding_parity # Node
```

---

## Resumo final

- **6 fases** (A-F), **20 tasks** no total
- **3 BLOQUEANTE + 4 IMPORTANTE + 2 PARCIAL** resolvidos
- **10 decisoes arquiteturais** (D1-D10) resolvidas em Fase 0
- **Criterio global**: install + update + query em scratch project sem Python, retorna JSON com fontes citadas, suite pytest continua verde
- **Publicacao**: tag `packages-v0.1.0` dispara CI; npm publish automatico via `--provenance`