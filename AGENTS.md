# DFe-Agent
> Agente local que coleta documentação fiscal eletrônica oficial (NF-e, NFC-e, CT-e, MDF-e, SPED) e legislação fiscal eletrônica oficial, indexa em base RAG local e responde perguntas em linguagem natural fundamentadas em notas técnicas.

## Distribuicao como pacote npm (Sprint 14+)

Desde a Sprint 14, o agente `dfe-agent` e' distribuido como `@dfe-agent/dfe-agent` no npm. Outros projetos opencode consomem via:

```bash
npm install @dfe-agent/dfe-agent
npx dfe-agent install   # copia agent + skill para .opencode/
npx dfe-agent update    # baixa base RAG (~30MB) do GitHub Releases
```

### Convecoes de empacotamento

- **Fonte canonica no DFe-Agent root**:
  - `.opencode/agent/dfe-agent.md`
  - `.opencode/skills/dfe-fiscal/SKILL.md`
- **Copia distribuida** em `packages/dfe-agent/dist/`.
- **Sync automatizado**: `cd packages/dfe-agent && npm run sync` (executa `scripts/sync-assets.ts`).
- **Drift-check no CI**: `.github/workflows/test-npm-package.yml` roda `npm run drift-check`. Drift detectado = PR bloqueado (gate B.1).
- **Layout mono-repo**: `packages/dfe-agent/` (decisao D1, Sprint 14). Versionamento SemVer independente, tag `packages-v*.*.*`.

## Stack
| Camada | Tecnologia |
|--------|------------|
| Plataforma de agente | opencode (execução local) |
| Modelo LLM | MiniMax-M3 (pago, via opencode) |
| Base RAG (documentos fiscais) | SQLite + `sqlite-vec` (vec0) — versao operacional **6** |
| Linguagem da skill | Python 3.11+ |
| PDF parsing | `pypdf` |
| HTML parsing | `BeautifulSoup` + `lxml` |
| Embeddings (documentos) | `sentence-transformers` (`paraphrase-multilingual-MiniLM-L12-v2`; trocavel via `DFE_EMBEDDING_MODEL`) |
| Busca textual | FTS5 nativo do SQLite (BM25) |
| Persistência | SQLite local único (relacional + vetorial) |
| Execução | 100% local na máquina do usuário |

## Sistema de RAG meta-cognitivo (.opencode/rag/)

> **Sprint 12 (B12.4)**: RAG meta-cognitivo migrado de ``.claude/`` para
> ``.opencode/rag/`` (unificacao total do harness em ``.opencode/``).

Além do RAG de documentos fiscais, o projeto tem um segundo RAG que captura
**aprendizados de agents e sessoes** (``.opencode/rag/rag.db``). Inspirado nos
eventos `SubagentStop` / `Stop` / `UserPromptSubmit` do Claude Code.

| Camada | Tecnologia |
|---|---|
| Base | SQLite + `sqlite-vec` (vec0) — dimensao 384 |
| Linguagem | TypeScript (rodado via `tsx`, sem build step) |
| Embeddings | `all-MiniLM-L6-v2` via `@xenova/transformers` (ONNX em Node) |
| Chunker | sentence-aware, 200-300 tokens, overlap 50 |
| Categorias | `bug_root_cause` / `architecture_decision` / `team_pattern` / `what_didnt_work` |
| Hooks (opencode) | wrappers Python que disparam os scripts TS via subprocess |
| Async | `subprocess.Popen` com `DETACHED_PROCESS` (fire-and-forget) |

```
.opencode/rag/
├── schema.sql                 # CREATE TABLE knowledge + vec_knowledge (vec0)
├── lib/{db,chunker,embedder,classifier}.ts
├── init_db.ts                 # cria .opencode/rag/rag.db
├── summarize.ts               # transcript -> .md em knowledge/
├── embed.ts                   # .md -> chunks -> embeddings -> rag.db
├── search.ts                  # pergunta -> top-3 (prioriza categoria do agent)
├── smoke_test.ts              # teste end-to-end
└── knowledge/                 # .md extraidos e pendentes de embed
```

> **Sprint 11**: `.opencode/hooks/` agora contem apenas `domain_guard.py` (modulo Python vivo, importado por `src/utils/http_guard.py`) e `allowed_domains.py` (constante `ALLOWED_DOMAINS`). Os 3 scripts `learning_*.py` foram REMOVIDOS (B11.2: eram "letra morta" desde Sprint 5 C.1; opencode nao suporta nativamente `pre_request`/`subagent_end`/`session.stopped`). O pipeline de captura `summarize.ts -> embed.ts` continua ativo e e' disparado por `.opencode/hooks/dev/stop.py` (canonico, Sprint 10).

Mapeamento event-style (pos-Sprint 11):
- `tool.execute.before` / `tool.execute.after` / `session.stopped` → plugin TS `.opencode/plugin/agent-hooks.ts` → scripts Python em `.opencode/hooks/<agent>/<hook>.py`.
- `dev/stop.py` chama `learning.spawn_summarize_then_embed` (em `.opencode/hooks/_lib/learning.py`) → `summarize.ts -> embed.ts` (fire-and-forget).

Decisoes-chave:
- **Por que TypeScript?** Pedido explicito; `@xenova/transformers` roda ONNX em Node sem dependencia Python no caminho.
- **Por que classificador heuristico?** Hooks Stop disparam em background; chamar LLM para classificar adicionaria latencia + custo. Heuristicas cobrem 80%+ dos casos; o .md pode ser revisado manualmente.
- **Por que hooks Python chamam TS?** opencode ja tem pipeline Python em `.opencode/hooks/dev/` (canonico); os scripts TS ficam reutilizaveis via CLI (`npx tsx .opencode/rag/...`).

## Estrutura de pastas
```
DFe-Agent/
├── .opencode/                  # Harness completo (Sprint 12 unificou .claude/ em .opencode/)
│   ├── agent/                  # Definicoes canonicas (dfe-agent, dev, code-reviewer)
│   ├── command/                # Slash commands (/feature, /bug, /duvida)
│   ├── hooks/                  # Hooks Python (dev/, code-reviewer/, _lib/) + guardrails (domain_guard.py, allowed_domains.py)
│   ├── plugin/agent-hooks.ts   # Plugin TS que despacha PreToolUse/PostToolUse/Stop
│   ├── rag/                    # RAG meta-cognitivo (scripts TS + rag.db + knowledge/) — antes em .claude/
│   ├── rules/                  # Rules carregadas via opencode.json > instructions
│   └── skills/dfe-fiscal/      # Skill canonica do dominio fiscal
├── src/                        # Codigo backend Python (RAG fiscal principal)
├── src/
│   ├── collector/              # Coletor/Scraper (portais oficiais)
│   ├── parser/                 # PDF/HTML/metadata_extractor
│   ├── indexer/                # Chunkers, embeddings, RagIndexer
│   ├── query/                  # QueryEngine + CLI (search, hybrid, hierarchical, rerank)
│   ├── eval/                   # Runner do benchmark Fase 16
│   ├── db/                     # Storage (sqlite_storage, vector_store, fts_store, doc_summaries, migrations)
│   ├── ragctl.py               # CLI administrativo (migrate, benchmark, reindex, stats)
│   └── utils/                  # Logging, retry, throttling
├── data/                       # PDFs/HTML brutos baixados
├── tests/                      # Testes (unit + integration)
│   ├── fixtures/               # sample_nt.pdf, fake_portal/, eval_set.json
│   └── integration/            # Smoke E2E + guardrails
├── storage/                    # storage/dfe.db + query_cache.db + benchmark_report.json
├── PLAN.md                     # Plano Sprint 1
├── PLAN_SPRINT2.md             # Plano Sprint 2 (RAG profundo)
├── SPEC.md                     # Especificação original
└── AGENTS.md                   # Este context file
```

## Como rodar localmente
**Pré-requisitos**
- opencode instalado e configurado
- Python 3.11+
- SQLite com `sqlite-vec` instalado (ver `requirements.txt`)

**Backend / Skill (Python)**
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m src.ragctl migrate                 # cria DB e aplica todas as migrations
python -m src.collector --once               # varredura inicial para popular a base
python -m src.indexer.ingest                 # ingestao dos pendentes
```

**Agente (opencode)**
```bash
opencode run                                 # modo interativo
opencode run "Como cancelar NF-e apos a NT 2024.001?"
```

**Pipeline de feature (slash command `/feature`)**
```bash
opencode run "/feature <descricao livre da feature>"
```
Dispara o pipeline canonico definido em `.opencode/command/feature.md`:
Fase 0 (briefing + RAG meta-cognitivo) -> Fase 1 (cria `PLAN_SPRINT{n}.md`
seguindo o template de `PLAN_SPRINT7.md`) -> Fase 2 (TDD por task) -> Fase 3
(gate de testes com cobertura minima) -> Fase 4 (code review via subagent
`code-reviewer`) -> Fase 5 (loop corretivo ate' 0 BLOQUEANTE / 0 IMPORTANTE)
-> Fase 6 (`.opencode/rag/knowledge/<slug>.md` + `embed.ts --file`) -> Fase 7
(relatorio final para arbitragem humana). Voce NAO comita: o humano fecha
commit + push. Re-executa o ciclo se o code review reportar BLOQUEANTE ou
IMPORTANTE (max 3 iteracoes; apos isso, pede arbitragem humana).

**Consultas CLI direto**
```bash
python -m src.query "<pergunta>"              # busca semantica (Sprint 1)
python -m src.query --hybrid "<pergunta>"     # RRF com BM25
python -m src.query --hierarchical "<pergunta>" # two-stage via summaries
python -m src.query --rerank "<pergunta>"     # cross-encoder opt-in
python -m src.ragctl benchmark                # roda eval_set + reporta metricas
python -m src.ragctl stats                    # contadores da base
```

**Testes**
```bash
pytest tests/                                # suíte completa (372+)
pytest tests/unit/ --cov=src --cov-fail-under=80   # unit + cobertura
pytest tests/integration/                    # smoke E2E
```

**RAG meta-cognitivo (.opencode/rag/)**
```bash
npm install --prefix .opencode                # deps Node (better-sqlite3, sqlite-vec, tsx, @xenova/transformers)
npx --prefix .opencode tsx .opencode/rag/init_db.ts   # cria .opencode/rag/rag.db
npx --prefix .opencode tsx .opencode/rag/summarize.ts -i <transcript> -a <agent>   # transcript -> .md
npx --prefix .opencode tsx .opencode/rag/embed.ts --file <md>                       # .md -> embeddings
npx --prefix .opencode tsx .opencode/rag/embed.ts --all                             # processa todos os .md
npx --prefix .opencode tsx .opencode/rag/search.ts -q "<pergunta>" -a <agent>      # top-3 chunks
npx --prefix .opencode tsx .opencode/rag/smoke_test.ts                              # teste end-to-end
```

**Variaveis de ambiente do embedding** (PLAN_SPRINT5 F.1/F.3)

| Variavel | Default | Efeito |
|---|---|---|
| `DFE_EMBEDDING_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | Troca o modelo (ex.: `all-MiniLM-L6-v2` para ingles) |
| `DFE_EMBEDDING_DTYPE` | `float32` | `float16` reduz ~50% o footprint em RAM/pagefile |

Quando o load do embedding falha com `OSError 1455` (page file do
Windows insuficiente), o erro e' re-levantado como `RuntimeError` com
workaround canonico apontando para `DFE_EMBEDDING_DTYPE=float16`.
O script `scripts/check_env.ps1` valida o ambiente (memoria, page
file, embedding load, db acessivel) e imprime JSON com
recomendacao acionavel.

## Estratégia RAG (Sprint 2)

A busca acontece em **3 modos opt-in** via CLI, alem do modo padrao pre-Sprint-2:

| Modo | Flag | Algoritmo | Quando usar |
|---|---|---|---|
| Semantica (default) | (nenhuma) | cosine cosseno no vec_chunks + dedup por doc + boost temporal | Perguntas genericas |
| Hibrido | `--hybrid` | RRF (k=60) entre semantica e FTS5 (BM25) | Termos literais (numero de NT, codigo) |
| Hierarquico | `--hierarchical` | embedding -> top-10 summaries -> vec_chunks filtrado | Quando a base cresce >1000 docs |
| Re-rank | `--rerank` | cross-encoder nos top-5*5 candidatos | Quando o benchmark mostra ganho de MRR |

Cache de embeddings de query ativado por default (`storage/query_cache.db`);
desative com `--no-cache`.

## Padrões de código
- Nomenclatura de arquivos: snake_case em Python (`pdf_parser.py`, `rag_indexer.py`); kebab-case em configs do opencode (skill dedicada em `.opencode/skills/<kebab>/SKILL.md`; regras em `.opencode/rules/<kebab>.md`).
- Nomenclatura de variáveis e funções: snake_case em Python (`extract_text_from_pdf`, `chunk_size`); PascalCase para classes (`RagIndexer`, `DocumentCollector`); UPPER_SNAKE_CASE para constantes (`REQUEST_INTERVAL_MS`, `ALLOWED_DOMAINS`).
- Estrutura de endpoints: não há API HTTP — toda interação é via invocação do agente opencode e chamadas internas entre módulos Python.
- Estrutura de componentes: cada módulo em `src/` é independente, com `__init__.py` expondo apenas a interface pública; lógica de I/O separada da lógica de domínio.
- Tipagem: type hints obrigatórios em todas as funções Python (`def extract(pdf_path: Path) -> str:`); sem `Any` implícito; usar `dataclass` ou `pydantic` para modelos de domínio.

## TDD
- Framework backend: `pytest` (com `pytest-mock` e `pytest-cov`)
- Framework frontend: não se aplica (sem UI)
- Onde ficam os testes: espelhados em `tests/unit/` e `tests/integration/`, com estrutura paralela a `src/`
- Regra: cobertura mínima de 80% em `src/` (medida atual ~95%); **100% em `src/parser/`** e **>=95% em `src/indexer/`** (caminhos críticos de ingestão)
- Migration framework: cada `_apply_vN(conn)` é idempotente e roda via `apply_pending(db_path)` (controlado por `PRAGMA user_version`)

### Testes críticos deste projeto
- [x] Coletor identifica corretamente um novo documento e o marca como `não ingerido` antes de baixar
- [x] Parser extrai texto limpo de PDF de nota técnica sem corromper acentuação/encoding
- [x] Indexador não reprocessa documento já ingerido (idempotência por hash)
- [x] Agente recusa responder quando nenhum chunk relevante é encontrado (guardrail de veracidade)
- [x] Hook bloqueia requisição para domínio fora da lista permitida
- [x] Coletor respeita intervalo mínimo entre requisições (não "metralhar" portais)
- [x] Toda resposta gerada cita a fonte (URL + nome do documento) presente na base
- [x] Migration framework upgrade v1→v6 sem perda de dados
- [x] Busca hibrida (RRF) e hierarquica (two-stage) retornam resultados consistentes e complementares
- [x] Cache de query embedding eh hit na 2a chamada (sem nova invocacao do modelo)
- [x] Guard HTTP in-process NAO recursiva ao chamar URL autorizada (`test_safe_session_get_does_not_recurse` + `test_safe_get_does_not_recurse` em `tests/integration/test_domain_guard_plugin.py`; pre-fix `RecursionError`, post-fix 1 chamada)

## Decisoes resolvidas (Sprint 7)

- [x] **Bootstrap canonico de ``sys.path`` para ``hooks.domain_guard`` (BLOQUEANTE B7)**. O modulo ``src/utils/syspath_bootstrap.py`` expoe ``ensure_sys_path()`` (idempotente por flag de modulo) que prepende ``.opencode/`` e ``src/`` em ``sys.path``. Invocado top-level em ``src/utils/http_guard.py`` ANTES do import `from hooks.domain_guard import ...`. ``tests/conftest.py`` e ``tests/unit/query/test_main.py`` continuam prependendo ``src/`` em ``PYTHONPATH`` apenas para localizar o PACOTE ``src`` em subprocesso isolado (``cwd=tmp_path``); isso e' design do subprocess, nao workaround do bootstrap. Ver `tests/integration/test_cli_runs_without_pythonpath.py` (cobre o caminho real: cwd do projeto, sem PYTHONPATH).

- [x] **UTF-8 explicito em stdout/stderr do ``python -m src.query`` (BLOQUEANTE B8)**. O helper ``_configure_utf8_stdout()`` em ``src/query/__main__.py`` reconfigura ``sys.stdout``/``sys.stderr`` para UTF-8 via ``reconfigure(encoding="utf-8")`` ou fallback via ``io.TextIOWrapper(sys.<stream>_buffer, encoding="utf-8")``. Chamado no inicio de ``main()``, antes de qualquer I/O. Resolve ``UnicodeEncodeError: 'charmap' codec can't encode character '\uf0b7'`` que quebrava a impressao de JSON quando chunks do RAG continham bullet, emoji ou caracteres acentuados. Cobertura de testes em ``tests/unit/query/test_utf8_stdout.py``.

- [x] **`--diagnose-net` no coletor + categorizacao de erros de rede (IMPORTANTE I7.1)**. Flag ``--diagnose-net`` em ``src/collector/__main__.py`` itera ``ALLOWED_DOMAINS`` (DNS + GET https://<host>/ com timeout 5s), imprime JSON com status por host, exit 0 se todos OK / 1 senao. Erros de ``discover_and_register`` agora passam por ``_categorize_request_error`` que distingue NXDOMAIN / timeout / ConnectionRefused / erro generico.

- [x] **Log em stderr quando query nao retorna chunks (IMPORTANTE I7.2 + D.2)**. ``_build_answer`` em ``src/query/__main__.py`` imprime ``[query] sem chunks relevantes — count=N`` em stderr quando a busca retorna lista vazia ou abaixo de ``MIN_RELEVANCE_SCORE``. Evita que o usuario confunda "sem base" com "CLI travou" (o sintoma ``(no output)`` registrado em 2026-08-26 era o mesmo ``UnicodeEncodeError`` de B8, resolvido por tabela via decisao anterior).

## Decisoes resolvidas (Sprint 8)

- [x] **RAG meta-cognitivo restaurado (BLOQUEANTE B8.1 + B8.2)**. O pipeline ``summarize.ts -> embed.ts`` que capturava aprendizados foi perdido na migracao dos Sprints 4-6 (substituicao dos hooks legados por `stop.py` que so' rodam pytest). Restauracao via 3 mudancas:
    1. Novo helper ```[LEGADO]```<LEGACY>`/.hooks/_lib/learning.py` expoe `spawn_summarize_then_embed`, `marker_path`, `should_record`, `payload_has_edits`, `resolve_transcript` (DRY entre os 3 stop.py).
    2. Cada `stop.py` (backend/ml/prompt-engineer) chama o helper apos pytest passar E payload conter `tool_writes_count > 0` (gate duplo: qualidade + escopo).
    3. Plugin `.opencode/plugin/agent-hooks.ts` conta `writesPerSession: Map<sessionID, number>` em `tool.execute.after` e injeta `tool_writes_count` no payload do stop event. Limpa o contador apos o stop (evita memory leak).

- [x] **`opencode.json` raiz tem campo `"plugin": [".opencode/plugin/agent-hooks.ts"]`** (reverte Sprint 5 C.1). A instalacao via CLI `opencode plugin add` gravou `.opencode/opencode.json` com path invalido (`"list"` em vez do path real). Forma canonica: adicionar `"plugin"` manualmente em `opencode.json` raiz. `.opencode/opencode.json` foi REMOVIDO e adicionado ao `.gitignore` (subproduto do CLI).

- [x] **Marker de idempotencia composto `(agent_slug, session_id)`** (B.5). Antes era apenas `agent_slug` em `learning_subagent_stop.py:84-87`, o que colapsava 2 sessoes distintas do mesmo agent em uma unica entrada. Agora `_pending-<safe-agent>-<safe-session>.md.lock` no diretorio ```[LEGADO]```<LEGACY>`/.knowledge/` (canonicalizado via `_safe_slug`).

- [x] **Escopo de captura: apenas sessoes com `tool_writes_count > 0`** (B.1). Gate no `stop.py` antes de chamar `learning.spawn_summarize_then_embed`. Sessoes apenas de leitura (consulta, dry-run) NAO poluem o RAG meta-cognitivo. Helper `learning.payload_has_edits(payload)` aplica o gate.

- [x] **Defesa em profundidade em testes de guard HTTP** (corrige flake pre-existing). `tests/integration/test_domain_guard_plugin.py::test_http_guard_blocks_evil_url` agora chama `uninstall_http_guard()` antes de `install_http_guard()` (em vez de apenas install). Bug: testes anteriores com `mocker.patch.object(cli_main.requests, "get")` revertem `requests.get` para o original mas deixam `_guards_installed=True`; install idempotente nesse caso e' no-op silencioso e o teste falha.

## Decisoes resolvidas (Sprint 9)

- [x] **Cobertura completa dos cenarios do `code-reviewer` agent** (3 IMPORTANTE). Hardening do reviewer cobrindo os 8 cenarios identificados na auditoria (`C1` definicao, `C2` Write/Edit, `C3` Bash destrutivo, `C4` plugin TS, `C5` env var dispatch, `C6` /feature Fase 4, `C7` permission.* denies, `C8` stop no-op). 4 arquivos novos: `tests/unit/test_code_reviewer_definition.py` (13 testes estruturais), `tests/unit/hooks/test_code_reviewer_pre_tool_use.py` (15 testes dos 4 write-tools), `tests/unit/hooks/test_code_reviewer_pre_tool_use_bash.py` (58 testes parametrizados cobrindo 24 BLOCK + 26 ALLOW + 5 edge cases + 3 sqlite-db paths), `tests/integration/test_code_reviewer_plugin_dispatch.py` (10 testes do plugin TS + sanity do `feature.md` Fase 4). Suite: 599 passed + 1 skipped, cobertura 84.93% (gate 80% verde). Plano: `PLAN_SPRINT9.md`. Codigo TS nao foi tocado; so' a definicao `.opencode/agents/code-reviewer.md` ganhou a secao "Bloqueio de escrita (hooks Python complementares)" (documentacao, nao logica).

- [x] **Convencao "teste de definicao para cada agent"**. Estabelecido pelo `tests/unit/test_code_reviewer_definition.py` (analogia a `tests/unit/test_dfe_agent_definition.py`). Padrao aplicado: arquivo de teste por agent, validando (a) `name: <slug>`, (b) `mode: subagent`, (c) `permission.{edit,task,skill,todowrite}: deny` para read-only, (d) `permission.read: allow`, (e) `model: <provider>/<name>`, (f) body contem as 3 classes canonicas (BLOQUEANTE/IMPORTANTE/SUGESTAO) + termo `read-only`. Follow-up Sprint 10+: aplicar o mesmo template a `ml-engineer`, `qa-engineer`, `prompt-engineer` (precedente em `PLAN_SPRINT9.md` Padroes adotados).

- [x] **Convencao "subprocess.run([sys.executable, ...])" para hooks Python**. Quando o hook tem side-effects (log em `storage/agent_hooks.log`) ou pode disparar auto-recursao, prefere-se subprocess a import direto. Aplicado em 4 testes desta sprint (substituindo a duvida "importar o modulo X ou rodar via subprocess"). Padrao ja' estabelecido por `test_agent_dispatch.py` e `test_domain_guard_plugin.py` (Sprint 6).

- [x] **Tipagem em funcoes de teste (`-> None` em toda `def test_*`)**. Mantida em 100% dos 96 testes novos desta sprint. Precedente ```[LEGADO]```<LEGACY>`/.rules/tests.md` ("tipagem em `src/`" — estendido para testes nesta sprint como boa pratica).

- [x] **Subagent `code-reviewer` nao invocavel via Task tool no opencode atual** (gap conhecido). Sintoma: `Task(subagent_type="code-reviewer")` retorna `Model not found: MiniMax-M3/.`. Causa provavel: frontmatter `.opencode/agents/code-reviewer.md:5` tem `model: MiniMax-M3` sem prefixo de provider (precedente `test_dfe_agent_definition.py:33-42` exige `^\S+/\S+$`). Workaround aplicado nesta sprint: invocar subagent `general` com prompt pedindo template canonico do code-reviewer. Follow-up Sprint 10+: normalizar formato de `model:` em todos os agents (`PROVIDER/MiniMax-M3`) e adicionar `test_frontmatter_has_model_with_provider` a `test_code_reviewer_definition.py`.

- [x] **Duplicacao de definicao do `code-reviewer` em 2 paths nao resolvida** (SUGESTAO Sprint 9 aceita). `.opencode/agents/code-reviewer.md` (formato opencode CLI) e ```[LEGADO]```<LEGACY>`/.agents/code-reviewer.md` (formato Claude Code legado) coexistem. Sprint 9 sincronizou a `description` (linha 3) entre os dois; descricao canonica agora e' a do `.opencode/`. A duplicacao estrutural (164 vs 180 linhas, formatos diferentes) segue como follow-up de Sprint 10+ (consolidacao ou decisao formal de qual path e' canonico).

- [x] **Coverage tool branch vs statement conflito** (informativo). 100+ arquivos `.coverage.NTANDREWS.pid*` orfaos na raiz confundiram o `coverage combine`. Workaround aplicado: `--cov-branch` explicito + limpeza manual pre-suite. Follow-up Sprint 10+: automatizar cleanup via `pyproject.toml` (`tool.coverage.run.cleanup = true`) ou `.gitignore` dos `.coverage.*`.

## Decisoes resolvidas (Sprint 10)

- [x] **Agente `@dev` e' o UNICO agent implementador** (BLOQUEANTE B10.1). Substitui os agents fragmentados em ```[LEGADO]```<LEGACY>`/.agents/` (`backend-engineer`, `ml-engineer`, `prompt-engineer`, `qa-engineer`) como owner de todas as alteracoes no projeto. Definido em 2 formatos complementares:
    1. `.opencode/agent/dev.md` — formato opencode CLI (`mode: subagent`, `permission.*: allow` para escrita, `external_directory: deny`).
    2. ```[LEGADO]```<LEGACY>`/.agents/dev.md` — formato Claude-Code-like (`hooks:` no frontmatter) consumido pelo plugin TS `agent-hooks.ts`. Hooks em ```[LEGADO]```<LEGACY>`/.hooks/dev/{pre_tool_use,post_tool_use,stop}.py`. Agents legados ficam em ```[LEGADO]```<LEGACY>`/.agents/` como referencia historica (continuam roteaveis pelo plugin TS mas NAO devem ser usados pela interface atual).

- [x] **3 slash commands canonicos `/feature`, `/bug`, `/duvida`** (BLOQUEANTE B10.4). Todos invocam `agent: dev` no frontmatter:
    - **`/feature`** — pipeline completo de feature (planning sprint, TDD, suite verde, code-review, loop corretivo, RAG, entrega humana).
    - **`/bug`** — pipeline de correcao com **gate de aprovacao humana** entre investigacao (read-only) e correcao (write). Investigacao sempre termina com relatorio estruturado que pergunta "posso prosseguir?". Read-only ate' aprovacao explicita.
    - **`/duvida`** — Q&A estruturado read-only por contrato. SEMPRE le o projeto antes de responder (Read, Grep, Glob), cita `file_path:line_number` para cada evidencia, termina com bloco `Fontes:`. Nunca faz Write/Edit/Bash destrutivo.
    - Comandos `agent: build` e `agent: plan` foram REMOVIDOS da interface (referencias textuais ao slug `build` foram limpas em `.opencode/command/feature.md`, AGENTS.md, e `_lib/test_runner.py`).

- [x] **Hooks ```[LEGADO]```<LEGACY>`/.hooks/dev/*` implementam gate duplo: qualidade + seguranca** (BLOQUEANTE B10.2):
    - `pre_tool_use.py` — bloqueia `git push`/`gh pr create`, `pip install`/`poetry add`, `curl`/`wget`, `rm -rf`, `sed -i`, redirecionamento `>`/`tee`, `sqlite3` direto, comandos do pipeline RAG (`python -m src.collector --once`, `src.indexer.ingest`, `src.ragctl {migrate,reindex,benchmark}`), scripts do RAG meta-cognitivo (`npx tsx ``[LEGADO]```<LEGACY>`/.scripts/{embed,search,summarize}.ts`). NAO bloqueia paths (escopo amplo). `python -m src.ragctl stats` e `python -m src.collector --diagnose-net` sao escape hatches explicitos.
    - `post_tool_use.py` — roda pytest da suite apropriada (definida em `_lib/test_runner.py::suites_for_path(rel_path, agent="dev")`; `@dev` retorna uniao das suites backend + ml para qualquer path).
    - `stop.py` — roda `pytest tests/` geral (suite completa). Em sucesso + `tool_writes_count > 0` + transcript existe: chama `learning.spawn_summarize_then_embed`. Em falha: exit 2 (gate bloqueia encerramento).

- [x] **RAG meta-cognitivo reconhece slug `dev`** (BLOQUEANTE B10.3). 4 arquivos atualizados:
    1. ```[LEGADO]```<LEGACY>`/.hooks/_lib/payload.py` — adicionado `("dev", re.compile(r"\bdev\b(?!elop|ice|el|our|oid)"))` em `_AGENT_HINTS`. Lookhead negativo evita falsos positivos com "developer", "device", "devout".
    2. `.opencode/hooks/learning_prompt_submit.py` — adicionado `("dev", r"\b(implementar|criar|adicionar|desenvolver|fix|bug|refatorar|codigo|src/|test/|ajustar|corrigir|feature)\b")` em `AGENT_HINTS`. Prompt de implementacao ativa slug `dev` antes de chegar no `search.ts`.
    3. `.opencode/plugin/agent-hooks.ts` — adicionado profile `"dev": { slug, preToolUse, postToolUse, stop }` no map `AGENTS`. Constante `RECOGNIZED_AGENT_SLUGS: Set([dev, code-reviewer, backend-engineer, ml-engineer, prompt-engineer, qa-engineer])` documentada como referencia estavel (slugs `build`/`plan` NAO fazem parte).
    4. ```[LEGADO]```<LEGACY>`/.hooks/_lib/test_runner.py` — adicionado branch `if agent == "dev": tables = (_BACKEND_SUITES, _ML_SUITES)` em `suites_for_path`. `@dev` retorna todas as suites aplicaveis para qualquer path.

- [x] **RAG antes/depois garantido em todos os slash commands**. Padrao canonico documentado em cada command:
    - **RAG antes** (Fase 0): `npx tsx ``[LEGADO]```<LEGACY>`/.scripts/search.ts -q "$ARGUMENTS" -a dev --top-k 5` injeta aprendizados anteriores no contexto do agent.
    - **RAG depois** (Fase final): grava ```[LEGADO]```<LEGACY>`/.knowledge/<date>-dev-<contexto>.md` (categoria `bug_root_cause` para `/bug`, `team_pattern` para `/duvida`, `architecture_decision` para `/feature`) e roda `npx tsx ``[LEGADO]```<LEGACY>`/.scripts/embed.ts --file <md>` sincrono. Hooks `.opencode/hooks/learning_*` e ```[LEGADO]```<LEGACY>`/.hooks/dev/stop.py` continuam como safety net em background (fire-and-forget).

- [x] **Agentes `build` e `plan` nao estao mais disponiveis na interface** (E.4). Verificacao automatizada em `tests/unit/test_commands_definitions.py::test_no_command_references_legacy_agent[build|plan]` (2 testes parametrizados). Nenhum arquivo em `.opencode/command/` referencia `agent: build` ou `agent: plan`.

## Decisoes resolvidas (Sprint 11)

- [x] **Manifest.json + 3 learning_*.py orfaos removidos (B11.2)**. O `.opencode/hooks/manifest.json` era "letra morta" desde Sprint 5 C.1 (decisao de mover dispatch para plugin TS). Os 3 scripts `learning_*.py` so' rodavam sob testes via subprocess. Removidos em Sprint 11. Runtime RAG meta-cognitivo passa por ```[LEGADO]```<LEGACY>`/.hooks/_lib/learning.py::spawn_summarize_then_embed`, chamado pelos `stop.py` de `dev` (canonico, Sprint 10). O `.opencode/hooks/domain_guard.py` continua como modulo Python vivo (importado por `src/utils/http_guard.py`); apenas o bloco `if __name__ == "__main__":` (CLI morto) foi removido. `src/utils/manifest_loader.py` (zero consumidores em `src/`) tambem removido.

- [x] **4 agents legacy (backend/ml/prompt/qa-engineer) removidos (I11.2)**. Plugin TS `.opencode/plugin/agent-hooks.ts:42-76` reduziu o map `AGENTS` de 6 para 2 (`code-reviewer` + `dev`). ~625 LoC duplicadas apagadas em ```[LEGADO]```<LEGACY>`/.hooks/{backend,ml,prompt,qa}-engineer/`. Os 4 ```[LEGADO]```<LEGACY>`/.agents/<legacy>.md` tambem removidos. Tests correspondentes reescritos. Gate anti-regressao em `tests/integration/test_no_legacy_agents.py` (7 testes) impede ressurreicao.

- [x] **`code-reviewer.md` consolidado em `.opencode/agent/` (B11.5 + I11.1)**. Path canonico do opencode CLI e' singular (`.opencode/agent/`, nao `.opencode/agents/`). Frontmatter `model: PROVIDER/MiniMax-M3` adicionado (Sprint 9 follow-up finalmente fechado). `tests/unit/test_code_reviewer_definition.py::test_frontmatter_has_model_field` agora exige o formato `^\S+/\S+$` (precedente do `test_dfe_agent_definition.py`). O diretorio `.opencode/agents/` foi removido; 7 referencias em ```[LEGADO]```<LEGACY>`/.agents/dev.md`, `.opencode/command/{feature,bug}.md`, `.opencode/{README,agent/README,command/README}.md` foram atualizadas.

- [x] **`_lib/learning.py:37` off-by-one corrigido (B11.1)**. Trocado `parents[2]` por `parents[3]` (consistente com `_lib/payload.py`). Antes da correcao, `PROJECT_ROOT` resolvia para `.claude/` em vez de DFe-Agent root, fazendo `_knowledge_dir()` apontar para `.claude/``[LEGADO]```<LEGACY>`/.knowledge/` e `LOG_PATH` para ```[LEGADO]```<LEGACY>`/.storage/agent_hooks.log`. Tests monkeypatchavam `PROJECT_ROOT` em 9+5 sites, entao CI nao detectava. Artefatos `.claude/.claude/` (diretorio aninhado, 6 arquivos `_pending-*.md`) e ```[LEGADO]```<LEGACY>`/.storage/agent_hooks.log` (431 linhas) foram limpos. Gate novo em `tests/unit/hooks/test_learning_helper.py::test_project_root_resolves_to_dfe_agent_root` + 2 testes correlatos (`test_knowledge_dir_is_canonical`, `test_log_path_is_storage_root`).

- [x] **Regra 3 do dfe-rules.md removida (I.5)**. "Sempre executar `python -m src.collector --once` antes de qualquer resposta" foi removida de `.opencode/rules/dfe-rules.md` (4 regras restantes, era 5) e de `.opencode/agent/dfe-agent.md`. A regra contradizia o gate `dev/pre_tool_use.py:79-90` que BLOQUEIA esse comando. Skill `.opencode/skills/dfe-fiscal/SKILL.md` continua sendo a fonte canonica do fluxo de varredura (Passo 2). Gate em `tests/unit/test_dfe_rules_definition.py` agora exige "exactly 4 ordered items".

- [x] **`.opencode/node_modules/` adicionado ao `.gitignore` (B11.4)**. Latente ate inicializar git repo (env atual: nao e' git repo). Cobertura via `tests/integration/test_gitignore_opencode.py` (3 testes: root pattern, package-lock.json, recursividade). Sem isso, 55 MB de deps do SDK `@opencode-ai/plugin` seriao commitados. Tambem adicionado `.opencode/package-lock.json` (output de `npm install` no `.opencode/`).

- [x] **Suite de testes de hooks consolidada**. Pre-Sprint 11: `test_learning_hooks_dispatch.py` (testava manifest), `test_learning_hooks_idempotent.py` (testava `.opencode/hooks/learning_*.py`), `test_learning_prompt_submit.py` — todos removidos (codigo morto). `test_learning_stop_hook.py` reescrito para focar em `dev/stop.py` (unico hook canonico). `test_domain_guard.py` perdeu 2 testes CLI (forma morta desde Sprint 5). `test_code_reviewer_pre_tool_use.py` reduziu lista de agents legacy de 5 para 1 (`dev`).

## Nunca fazer
- Nunca inventar informação: toda afirmação do agente deve ter fonte na base RAG; se não houver base, declarar explicitamente a ausência de informação (`NO_EVIDENCE_MESSAGE`)
- Nunca acessar domínios fora da lista oficial permitida (NF-e, NFC-e, CT-e, MDF-e, SPED) — enforced por hook de guardrail `domain_guard.py`
- Nunca metralhar requisições aos portais: respeitar intervalo entre chamadas, sem proxy rotativo, CAPTCHA solving ou contorno de anti-bot
- Nunca emitir documento fiscal, substituir contador ou emitir opinião legal/contábil (fora de escopo)
- Nunca reprocessar documento já marcado como `ingerido` na base SQLite (idempotência obrigatória por `content_hash`)
- Nunca dropar `vec_chunks` sem antes backfill (perda de embeddings; use `python -m src.ragctl reindex` que orquestra o ciclo)

## Rules por submódulo (```[LEGADO]```<LEGACY>`/.rules/`)

Rules complementares ao system prompt de cada agent, carregadas via
`opencode.json > instructions`. Cada rule contém apenas o que o agent não
descobriria lendo o código.

| Rule | Path scope | Escopo |
|---|---|---|
| `seguranca.md` | (nenhum — incondicional) | Restrições de segurança aplicáveis a qualquer agent: segredos fora do repo, anti-bot como política (`Throttler`), guardrails invioláveis, proveniência do RAG, escrita na base via portões explícitos, exfiltração, `replaces_doc_id`, abort do code-reviewer em caso de bypass |
| `convencoes-gerais.md` | (nenhum — incondicional) | Padrões transversais: nomenclatura (snake_case/PascalCase/UPPER_SNAKE_CASE), frontmatter obrigatório, tipagem em `src/`, `NO_EVIDENCE_MESSAGE` canônico em `src/query/context_builder.py`, contrato `{answer, sources[]}`, migration framework idempotente (`PRAGMA user_version`), cobertura mínima, política de comentários |
| `src.md` | `src/**/*.py` | Backend Python: sem API HTTP, `__init__.py` expõe só interface, todo path HTTP via `Throttler`, schema de `documents` obrigatório, `replaces_doc_id` para substituição, índices via migrations (FTS5/0004, doc_summaries/0005), `Summarizer` determinístico sem LLM, embedding via `DFE_EMBEDDING_MODEL`, cache de query HIT, CLI = `__main__.py`+argparse |
| `tests.md` | `tests/**/*.py` | Suíte pytest: stack pytest+pytest-mock+pytest-cov, estrutura espelhando `src/`, fixtures centralizadas em `tests/fixtures/`, integração sem rede (usa `fake_portal/` via `monkeypatch`), DB isolada (`tmp_path` + monkeypatch), cobertura como gate (`--cov-fail-under=80`; 100% em `src/parser/`; 95% em `src/indexer/`), idempotência de migration, cache HIT, "Testes críticos" do AGENTS.md com cobertura obrigatória |

Submódulos do `src/` (collector, parser, indexer, query, db, eval, utils)
compartilham `src.md`. Para paths não cobertos por nenhuma rule escopada
(ex.: `.opencode/`, `.opencode/rag/`), valem apenas as rules
incondicionais + o conteúdo deste AGENTS.md.

## Decisões resolvidas (Sprint 12)
- [x] **Harness unificado em `.opencode/`** (B12.1 + B12.2 + B12.3 + B12.4). O diretorio `.claude/` foi REMOVIDO completamente (Fase 5). Todo o harness (hooks Python, scripts TS, rules, agents stub, skill legado, state, .cache, storage, README) vive em `.opencode/`. Cobertura nova em `tests/unit/hooks/test_path_safety.py` (11 testes) + `tests/integration/test_unified_harness.py` (gate final).
- [x] **Hooks Python vivem em `.opencode/hooks/{dev,code-reviewer,_lib}/`** (B12.1). O plugin TS `.opencode/plugin/agent-hooks.ts:46-56` aponta para os novos paths; suite de hooks atualizada em `tests/unit/hooks/test_*.py` + `tests/integration/test_dev_plugin_dispatch.py` + `test_code_reviewer_plugin_dispatch.py` + `test_agent_dispatch.py`.
- [x] **Scripts TS do RAG meta-cognitivo vivem em `.opencode/rag/{*.ts, lib/}`** (B12.4). Subdiretorio NOVO: `.opencode/rag/`. `db.ts` ajustou paths relativos de `..,..` para `..` (nova profundidade). `npx --prefix .opencode tsx .opencode/rag/init_db.ts` continua funcionando (validado em Fase 2 Task 2.6).
- [x] **Rules vivem em `.opencode/rules/`** (B12.3). As 4 rules historicas (`seguranca.md`, `convencoes-gerais.md`, `src.md`, `tests.md`) migraram de ```[LEGADO]```<LEGACY>`/.rules/` para `.opencode/rules/` (5 rules no total: 4 migradas + `dfe-rules.md` nativo). `opencode.json > instructions` ajustado em Task 3.2. Gate em `tests/integration/test_opencode_config.py::test_instructions_references_opencode_rules_only`.
- [x] **Skill `dfe-agent-runner` removida** (B12.5). Skill orfaa em ```[LEGADO]```<LEGACY>`/.skills/dfe-agent-runner/SKILL.md` (citava `confaz.fazenda.gov.br` removido em Sprint 4 D.1 e "rule 3" removida em Sprint 11 D.4) foi apagada na Fase 5. Funcionalidade equivalente em `.opencode/skills/dfe-fiscal/SKILL.md`.
- [x] **Agents stub ```[LEGADO]```<LEGACY>`/.agents/{dev,code-reviewer}.md` removidos** (B12.2). Duplicatas 95% removidas na Fase 3; canonical continua em `.opencode/agent/` (singular, Sprint 11 D.1). O opencode CLI ignora o frontmatter `hooks:`; a verdade runtime e' o map `AGENTS` em `agent-hooks.ts`. Gate anti-regressao em `tests/integration/test_no_legacy_agents.py` (11 testes).
- [x] **`_lib/learning.py::PROJECT_ROOT` continua valido** (B12.1 + B11.1). O arquivo vive agora em `.opencode/hooks/_lib/learning.py` (3 niveis ate a raiz); `parents[3]` mantem o calculo. Gates em `tests/unit/hooks/test_path_safety.py::test_*_project_root_resolves_to_dfe_agent_root` (3 testes) e `tests/unit/hooks/test_learning_helper.py::test_project_root_resolves_to_dfe_agent_root`.
- [x] **Suite verde + cobertura 85.11%** (gate 80% mantido). 745 testes passam + 1 skip (CONFAZ). Baseline Sprint 11: 727. +18 testes novos (11 path_safety + 4 opencode_config + 3 ajustes). Validado com `pytest tests/ --cov=src --cov-branch --cov-fail-under=80`.

## Decisões resolvidas (Sprint 2)
- [x] Extensão vetorial: `sqlite-vec` (vec0) — confirmado
- [x] Linguagem e bibliotecas: Python 3.11+ + `pypdf` + `BeautifulSoup` + `lxml` + `sentence-transformers` — confirmado
- [x] Estratégia de espaçamento: `Throttler` com jitter aleatorio (Sprint 1) — mantido
- [x] Política de retenção: vetorial sem `DELETE` automatico (Fase 14); substituicoes via `replaces_doc_id`. Reindex exige comando explicito.
- [x] Schema de metadados: `documents(nt_number, version, replaces_doc_id, language)` adicionado em migration 0002

## Decisões resolvidas (Sprint 4)
- [x] **Pin exato obrigatorio em `requirements.txt` e `pyproject.toml`** (C.1). Bounds (`>=X,<Y`) NAO sao permitidos. Reproducibilidade total entre ``pip install -r requirements.txt`` e ``pip install -e .``. Ver `tests/unit/test_dependency_pinning.py`.
- [x] **CONFAZ descontinuado a partir de 2026-XX-XX** (D.1). Os hosts ``confaz.fazenda.gov.br`` e ``www.confaz.fazenda.gov.br`` nao resolvem mais no DNS publico desde 2024 (subdominio removido). Tentativas de reativacao em 2026-XX-XX na URI ``https://www.confaz.fazenda.gov.br/legislacao`` retornaram timeout; mirror direto ``https://confaz.fazenda.gov.br/legislacao`` retorna NXDOMAIN. Decisao: removido de `SPEC.md` (atualizar) e `PLAN_SPRINT3.md` (atualizar). A entrada ``confaz`` em ``PORTAL_URLS`` (``src/collector/portal_index.py``) foi REMOVIDA. Testes que dependiam de CONFAZ (ex.: `test_portal_urls_contains_all_spec_sources`) usam ``pytest.skip("CONFAZ descontinuado")``.

## Decisões resolvidas (Sprint 5)
- [x] **Plugin TS instalado via CLI, nao inline em `opencode.json`** (C.1). O plugin `.opencode/plugin/agent-hooks.ts` e' carregado pelo opencode via CLI:
    ```bash
    opencode plugin add .opencode/plugin/agent-hooks.ts
    ```
    Decisao: nao adicionar campo `plugin` / `plugins` em `opencode.json` (risco de quebra silenciosa por schema nao documentado). A instalacao via CLI e' a forma suportada e aparece em `opencode plugin list` apos o add. Ver PLAN_SPRINT5.md Fase C.1.
- [x] **`session_end` renomeado para `session.stopped` no manifest** (C.2). O plugin `.opencode/plugin/agent-hooks.ts:266` so' escuta `session.stopped` e `session.idle`. O hook `learning_stop` em `manifest.json:30` foi corrigido para usar `session.stopped` (event type consistente com o dispatch do plugin).
- [x] **`www.gov.br` removido de `ALLOWED_DOMAINS`** (A.2). Adicionado `sped.gov.br` como host canonico. URL em `src/collector/portal_index.py:46` migrada de `https://www.gov.br/sped/pt-br` para `https://sped.gov.br/`. PLAN_SPRINT5.md A.2.
- [x] **4 scripts ad-hoc descartados** (F.2). `scripts/answer_nf_e_10_2026.py`, `scripts/buscar_dfereferenciado.py`, `scripts/demo_query.py`, `scripts/demo_query_2026.py` foram REMOVIDOS. Apenas `scripts/demo_cli.py` permanece (canonico, coberto por teste). PLAN_SPRINT5.md F.2.

## Decisões resolvidas (Sprint 6)
- [x] **Auto-recursao do guard HTTP in-process corrigida (BLOQUEANTE B6)** (A.1). `src/utils/http_guard.py:79` e `:92` chamavam `requests.get(url, **kwargs)` / `session.get(url, **kwargs)` apos o monkey-patch ter substituido `requests.get` / `requests.Session.get` por `safe_get` / `safe_session_get`, gerando `RecursionError` em runtime (sintoma: `python -m src.collector --once` quebra com recursion ate ``urllib/parse.py:394``). Correcao: chamar `_original_requests_get` / `_original_session_get` (ja' capturados em `http_guard.py:95-96`) em vez dos atributos da classe patchada. Adicionados 2 testes de caminho positivo em `tests/integration/test_domain_guard_plugin.py::test_safe_session_get_does_not_recurse` e `::test_safe_get_does_not_recurse` (substituem `_original_*` por contador via `monkeypatch.setattr`; pre-fix o teste levanta `RecursionError` antes do contador, post-fix o contador registra exatamente 1). Testes novos usam restauracao DIRETA de `requests.get` e `requests.Session.get` no ``finally`` (captura dos originais ANTES do ``install_http_guard``) para evitar leak via ``monkeypatch`` revert ordem pytest. Ver `PLAN_SPRINT6.md` A.1 e B.1.
- [x] **Test isolation em `test_http_guard_bootstrap.py::test_install_guard_once_idempotent` corrigido (B.1 secundario)**. O spy chamava `real_install()` (= `install_http_guard()`) sem teardown, vazando `requests.Session.get = safe_session_get` para testes posteriores (sintoma: `test_guardrail_response_cites_source` falhava quando `test_http_guard_bootstrap.py` rodava antes de `test_guardrails.py`; mascarado pela ordem alfabetica do pytest). Correcao: try/finally com `http_guard.uninstall_http_guard()`. Ver `PLAN_SPRINT6.md` Apêndice B (risco A.1 documentado mas nao implementado em Sprint 5).

## Decisoes resolvidas (Sprint 13)

- [x] **`.opencode/rules/dfe-rules.md` carregada pelo opencode runtime** (BLOQUEANTE B13.1). `opencode.json > instructions` agora lista as 5 rules canonicas (4 path-scope + `dfe-rules.md` domain-specific + `AGENTS.md` context). Antes da Sprint 13, `dfe-rules.md` (4 guardrails inviolaveis: veracidade, `ALLOWED_DOMAINS`, Fontes, `NO_EVIDENCE_MESSAGE`) vivia no disco desde Sprints 4-7 mas NAO era carregada pelo opencode runtime — todos os 3 agents (`dev`, `dfe-agent`, `code-reviewer`) a referenciavam como guardrail canonico mas nenhum a carregava. Posicao no array: apos `tests.md` (path-scope) e antes de `AGENTS.md` (context). Gate novo em `tests/integration/test_opencode_config.py::test_instructions_lists_dfe_rules`. Plano: `PLAN_SPRINT13.md` Fase B.
- [x] **`tsx` canonicalizado em `devDependencies`** (IMPORTANTE I13.1). `.opencode/package.json` agora separa `dependencies` (4 runtime: `@opencode-ai/plugin`, `@xenova/transformers`, `better-sqlite3`, `sqlite-vec`) de `devDependencies` (1: `tsx@4.19.2`). Antes da Sprint 13, `tsx` estava em `dependencies` (semantica incorreta: `tsx` e' usado apenas em runtime de dev/test via `npx tsx`, nao em producao). SUGESTAO S1 do Sprint 12 (knowledge file `2026-08-26-feature-unify-harness.md:196-198`) implementada. Gate novo em `tests/integration/test_opencode_config.py::test_tsx_is_devdependency`. `npm ls --prefix .opencode tsx` continua retornando `tsx@4.19.2` (instalado via npm install). Plano: `PLAN_SPRINT13.md` Fase C.
- [x] **Knowledge legado reclassificado** (IMPORTANTE I13.2). `.opencode/rag/knowledge/2026-08-25-backend-engineer.md` renomeado para `2026-08-25-dev.md` (slug canonico: `dev`, owner unico desde Sprint 10). Header do arquivo atualizado: removida referencia `> Extraido automaticamente de transcript via .claude/scripts/summarize.ts` (path morto pos-Sprint 12) e adicionada nota sobre a reclassificacao Sprint 13. `rag.db` (`.opencode/rag/rag.db`) teve 5 entradas stale removidas via cleanup one-off (paths `.claude/knowledge/2026-08-25-backend-engineer.md` + agent `backend-engineer`). Vec_knowledge orfaos nao purgados (requer `sqlite-vec` carregado, fora do escopo desta sprint). Gate novo em `tests/integration/test_unified_harness.py::test_rag_knowledge_no_legacy_slugs` impede ressurreicao de slugs legacy (`backend-engineer`, `ml-engineer`, `prompt-engineer`, `qa-engineer`, `build`, `plan`) em filenames. Plano: `PLAN_SPRINT13.md` Fase D.
- [x] **2 scripts orfaos removidos** (PARCIAL P13.1). `scripts/demo_sprint2.ps1` (3196 bytes) e `scripts/demo_sprint2.sh` (1952 bytes) apagados. Ambos eram variantes shell de demo end-to-end do CLI `python -m src.query`, criados em Sprint 2 e substituidos por `scripts/demo_cli.py` (Python, canonico, exempted do `.gitignore`) em Sprint 5 F.2. Pre-Sprint 11, scripts shell eram documentados em ```[LEGADO]```<LEGACY>`/.scripts/`; pos-Sprint 12, references em `AGENTS.md` foram removidas mas os arquivos persistiram ate' Sprint 13. `scripts/` agora contem apenas `check_env.ps1` (6855 bytes) + `demo_cli.py` (1915 bytes). Gate do `.gitignore` linha 119 (`scripts/*.py` + `!scripts/demo_cli.py`) continua valido.
- [x] **Suite verde + cobertura mantida** (gate 80%). 760 testes passam + 1 skip (CONFAZ descontinuado, pre-Sprint 13) + 1 falha pre-existente (`test_opencode_init_db_creates_db_in_opencode_rag` — `better_sqlite3.node` nao compilado para Node v22.21.1, problema de ambiente `.opencode/node_modules/` nao relacionado a Sprint 13). Baseline Sprint 12: 757 passed. +3 testes novos (B.2 + C.2 + D.3). Validado com `pytest tests/ --no-cov --no-header -q` em 195s.
