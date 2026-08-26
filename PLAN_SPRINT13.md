# PLAN_SPRINT13.md

> Plano de **higienizacao final do harness**: elimina inconsistencias remanescentes
> da Sprint 12 (unificacao `.opencode/`). 3 itens: 1 BLOQUEANTE + 2 IMPORTANTE +
> 1 PARCIAL (cleanup).
>
> Origem: auditoria do harness em 2026-08-26 (resposta a "/liste os elementos do
> harness e reporte isolados"). 4 achados: 1 BLOQUEANTE-classificavel, 3 SUGESTOES.
> Principio: **TDD** (teste vermelho primeiro), zero regressao nas suites existentes,
> cobertura >= 80%.
>
> NAO cobre: mudancas em `src/`, novas features, refatoracao estrutural maior.
> Foco: completar a unificacao `.opencode/` iniciada em Sprint 12.

## Criterio global de conclusao

`pytest tests/ --cov=src --cov-fail-under=80` retorna exit code 0 **E** os 3 itens
(B13.1 + I13.1 + I13.2) estao resolvidos via comandos shell documentados em
"Verificacao manual" no fim deste plano **E** o `.opencode/rag/knowledge/` tem
apenas arquivos com metadata canonica (slug `dev` ou `code-reviewer`, paths
`.opencode/`, datas >= 2026-08-26) **E** `opencode.json > instructions` lista as
5 rules canonicas (4 + `dfe-rules.md`) **E** `scripts/` contem apenas
`check_env.ps1` + `demo_cli.py` + `README.md` (se aplicavel).

```
Fase A ──► Fase B ──► Fase C ──► Fase D ──► Fase E
deletar   carregar    tsx devDep   knowledge    docs +
orfaos    dfe-rules   canonico     unificar     finalizacao
(cleanup) (BLOQ.)     (IMP.)       (IMP.)       (PARCIAL)
```

**Dependencias criticas entre fases**:

- B (carregar `dfe-rules.md`) e' independente de A (cleanup), mas B deve rodar
  antes de C/D para que o agente `dev` carregue os guardrails canonicos durante
  a execucao da sprint.
- C (tsx devDep) e' independente de B; altera apenas `.opencode/package.json`.
- D (knowledge unification) depende de B (regra canonica "knowledge antigo
  referenciado em notas historicas AGENTS.md deve ser preservado por design").
- E (docs) depende de A+B+C+D.

**Paralelismo intra-fase**:

- A: A.1 unica task (cleanup), trivial.
- B: B.1 + B.2 podem ser feitas em paralelo (B.1 mexe em `opencode.json`,
  B.2 mexe em `tests/integration/test_opencode_config.py`).
- C: C.1 + C.2 em paralelo (package.json + novo teste).
- D: D.1 + D.2 + D.3 sequenciais (dependem do resultado uma da outra).

---

## Resumo dos problemas observados

| ID | Sintoma | Causa raiz | Severidade |
|----|---------|------------|------------|
| **B13.1** | `.opencode/rules/dfe-rules.md` (4 regras inviolaveis: veracidade, `ALLOWED_DOMAINS`, Fontes, `NO_EVIDENCE_MESSAGE`) existe no filesystem mas NAO esta listada em `opencode.json > instructions`. O opencode runtime trata os 4 guardrails como "documentacao", nao como regras aplicadas. Todos os 3 agents (`dev`, `dfe-agent`, `code-reviewer`) referenciam `dfe-rules.md` como guardrail canonico mas nenhum deles o carrega via frontmatter de agent nem via `instructions`. | Sprint 12 B12.3 migrou 4 rules de `.claude/rules/` para `.opencode/rules/` e atualizou `opencode.json`, mas nao adicionou a 5a rule nativa (`dfe-rules.md`) que ja vivia em `.opencode/rules/` desde Sprints 4-7. Resultado: gate existe no disco mas nao no runtime. | **BLOQUEANTE** |
| **I13.1** | `tsx@4.19.2` esta pinned em `.opencode/package.json:7` mas dentro de `dependencies` em vez de `devDependencies`. Semanticamente incorreto: `tsx` e' usado apenas em runtime de dev/test (smoke test E2E, embed/summarize via CLI), nao em producao. SUGESTAO S1 do Sprint 12 foi registrada mas nao implementada. | Decisao arquitetural Sprint 8 (criacao do RAG meta-cognitivo) colocou `tsx` em `dependencies` para destravar o smoke test E2E rapido. Sem consequencia pratica (npm install funciona), mas mascara a natureza dev-only da dependencia. | IMPORTANTE |
| **I13.2** | `.opencode/rag/knowledge/2026-08-25-backend-engineer.md` e' um artefato pre-unificacao (gerado em 2026-08-25 antes da Sprint 12). Conteudo semantico ainda e' valido (causa raiz + fix do `download_pending`), mas metadata/proveniencia esta obsoleta: header referencia `> Extraido automaticamente de transcript via .claude/scripts/summarize.ts` (path morto pos-Sprint 12) e slug `backend-engineer` (agent removido em Sprint 11 I11.2). Polui queries no `search.ts` se alguem buscar por "backend-engineer". | Helper `summarize.ts` nao filtra por slug canonico: aceita qualquer string em `--agent`. O caller (`_lib/learning.py`) usava `backend-engineer` (slug valido pre-Sprint 11). Pos-remocao do agent (Sprint 11 I11.2), o `.md` ficou no knowledge mas com metadata nao-canonica. | IMPORTANTE |
| **P13.1** | `scripts/demo_sprint2.ps1` (3196 bytes) e `scripts/demo_sprint2.sh` (1952 bytes) existem no diretorio `scripts/` mas NAO sao referenciados em `AGENTS.md`, `opencode.json`, `README.md`, `.opencode/skills/dfe-fiscal/SKILL.md`, nem em nenhum agent/command/rule. Apenas `scripts/demo_cli.py:8` os menciona de passagem ("Equivalente em Python aos scripts shell `demo_sprint2.sh`/`.ps1`"). `.gitignore` exclui `scripts/*.py` (com excecao `!scripts/demo_cli.py`); os `.sh`/`.ps1` caem fora da exclusao, portanto estao sendo commitados sem dono. | Sprint 2 criou ambos para demonstrar `python -m src.query` end-to-end. Sprint 5 F.2 substituiu `scripts/demo_query.py` por `scripts/demo_cli.py` (Python) mas esqueceu de apagar os shell scripts originais. Pre-Sprint 11, scripts shell eram documentados em `.claude/scripts/`; pos-Sprint 12, references em `AGENTS.md` foram removidas mas os arquivos persistiram. | PARCIAL |

---

## Fase A — Limpar arquivos orfaos em `scripts/` (PARCIAL P13.1)

**Criterio**: `scripts/` contem apenas `check_env.ps1`, `demo_cli.py` e (se aplicavel) `README.md`. Nenhum `.sh` ou `.ps1` adicional. Suite de testes continua passando.

### Task A.1 — Apagar `scripts/demo_sprint2.ps1` e `scripts/demo_sprint2.sh`

- Agent: Backend Engineer
- Input: nenhuma (decisao tomada no briefing da sprint).
- Diagnostico:
  - Ambos arquivos foram criados em Sprint 2 como variantes PowerShell/bash de um demo end-to-end do CLI `python -m src.query`.
  - Sprint 5 F.2 substituiu por `scripts/demo_cli.py` (Python, canonico, exempted do `.gitignore`).
  - Sprint 12 nao tocou nesses arquivos (escopo era unificar `.opencode/` vs `.claude/`, nao `scripts/`).
  - Verificado por `grep -r "demo_sprint2" --include="*.md" --include="*.py" --include="*.ts"` que nenhuma referencia canonica existe.
- Output:
  - `scripts/demo_sprint2.ps1` apagado.
  - `scripts/demo_sprint2.sh` apagado.
  - Diretorio `scripts/` agora tem 2 arquivos: `check_env.ps1` (6855 bytes), `demo_cli.py` (1915 bytes).
  - Comando executado:
    ```powershell
    Remove-Item -LiteralPath "scripts\demo_sprint2.ps1"
    Remove-Item -LiteralPath "scripts\demo_sprint2.sh"
    ```
- Criterios de aceitacao:
  - [x] `Get-ChildItem scripts/` retorna apenas `check_env.ps1` + `demo_cli.py`.
  - [x] Suite `tests/integration/test_unified_harness.py::test_*` continua passando (nenhum teste referencia esses arquivos).
  - [ ] Suite `tests/unit/test_gitignore.py` ou similar (verificar se existe teste para `scripts/*.py` whitelist) continua passando.

> **Nota de execucao**: esta task ja foi executada na fase de pre-plan cleanup
> (2026-08-26) como prerequisite deste plano. Confirmar via `Get-ChildItem`.

---

## Fase B — Carregar `.opencode/rules/dfe-rules.md` no `opencode.json` (BLOQUEANTE B13.1)

**Criterio**: `opencode.json > instructions` lista as 5 rules canonicas (4 migradas + `dfe-rules.md`). O opencode runtime carrega `dfe-rules.md` automaticamente. Gate novo em `tests/integration/test_opencode_config.py::test_instructions_lists_dfe_rules` protege contra regressao.

### Task B.1 — Adicionar `.opencode/rules/dfe-rules.md` ao `instructions` array

- Agent: Backend Engineer
- Input: nenhuma
- Diagnostico:
  - `opencode.json:6-12` atualmente lista:
    ```json
    "instructions": [
      ".opencode/rules/seguranca.md",
      ".opencode/rules/convencoes-gerais.md",
      ".opencode/rules/src.md",
      ".opencode/rules/tests.md",
      "AGENTS.md"
    ]
    ```
  - `dfe-rules.md` vive em `.opencode/rules/dfe-rules.md` desde Sprints 4-7 e documenta 4 regras inviolaveis (veracidade, `ALLOWED_DOMAINS`, Fontes, `NO_EVIDENCE_MESSAGE`) que TODOS os agents referenciam mas nenhum carrega via `instructions`.
  - O teste existente `test_unified_harness.py::test_opencode_rules_count_is_5` ja confirma que 5 rules vivem no disco (`expected = {"seguranca", "convencoes-gerais", "src", "tests", "dfe-rules"}`), entao a contagem esta OK — falta apenas o wiring runtime.
- Output:
  - `opencode.json:11` (entre `tests.md` e `AGENTS.md`):
    ```json
    "instructions": [
      ".opencode/rules/seguranca.md",
      ".opencode/rules/convencoes-gerais.md",
      ".opencode/rules/src.md",
      ".opencode/rules/tests.md",
      ".opencode/rules/dfe-rules.md",
      "AGENTS.md"
    ]
    ```
  - Posicao: `dfe-rules.md` fica apos as 4 rules de path-scope (`src.md`, `tests.md`) e antes do context file canonico `AGENTS.md`. Justificativa: rules de path-scope sao as mais especificas e devem ser carregadas primeiro para nao serem sobrescritas por regras mais gerais; `dfe-rules.md` e' domain-specific (DFe fiscal); `AGENTS.md` e' o context file global.
  - Sem mudanca em outros campos do `opencode.json` (`plugin` continua apontando para `.opencode/plugin/agent-hooks.ts`).
- Criterios de aceitacao:
  - [ ] `git diff opencode.json` mostra apenas 1 linha adicionada (`.opencode/rules/dfe-rules.md`).
  - [ ] `python -c "import json; c = json.load(open('opencode.json')); assert '.opencode/rules/dfe-rules.md' in c['instructions']; print('OK')"` exit 0.
  - [ ] Suites previas (`tests/integration/test_opencode_config.py`, `tests/integration/test_unified_harness.py`) continuam passando.

### Task B.2 — Gate anti-regressao em `test_opencode_config.py`

- Agent: QA Engineer
- Input: B.1 aplicada
- Output:
  - `tests/integration/test_opencode_config.py`: nova funcao `test_instructions_lists_dfe_rules`:
    ```python
    def test_instructions_lists_dfe_rules(config: dict) -> None:
        """`instructions` deve listar `.opencode/rules/dfe-rules.md`.
        
        Regra canonica do DFe-Agent (4 guardrails inviolaveis: veracidade,
        ALLOWED_DOMAINS, Fontes, NO_EVIDENCE_MESSAGE). Vive no disco
        desde Sprint 4-7; Sprint 13 B13.1 adicionou ao `instructions`
        para que o opencode runtime a carregue.
        
        Anti-regressao: se um futuro dev remover `dfe-rules.md` do
        `instructions`, o teste falha antes do opencode carregar.
        """
        instructions = config.get("instructions")
        assert isinstance(instructions, list), (
            f"`instructions` deve ser lista; obtido {instructions!r}"
        )
        assert ".opencode/rules/dfe-rules.md" in instructions, (
            "`instructions` deve listar `.opencode/rules/dfe-rules.md` "
            "(B13.1, gate anti-regressao); obtido "
            f"{instructions!r}"
        )
    ```
  - Posicao: apos `test_instructions_references_opencode_rules_only` (linha 38-64 atuais).
  - Sem duplicacao com `test_instructions_references_opencode_rules_only` (esse testa ausencia de `.claude/` e presenca de >=1 rule; o novo testa presenca especifica de `dfe-rules.md`).
- Criterios de aceitacao:
  - [ ] Antes de B.1: teste falha com `AssertionError` (linha especifica: "B13.1, gate anti-regressao").
  - [ ] Depois de B.1: teste passa.
  - [ ] `pytest tests/integration/test_opencode_config.py` exit 0.

### Task B.3 — Verificar que dfe-agent e dev carregam a rule no prompt

- Agent: QA Engineer
- Input: B.1 + B.2 aplicadas
- Output:
  - Smoke test manual (nao automatizado — exige runtime do opencode CLI):
    ```bash
    opencode run --agent dfe-agent "teste smoke: cite a regra de veracidade"
    ```
    Espera-se: resposta do agent cita literalmente as 4 regras de
    `dfe-rules.md` (veracidade, ALLOWED_DOMAINS, Fontes, NO_EVIDENCE_MESSAGE).
  - Smoke test analogo para `@dev`:
    ```bash
    opencode run --agent dev "qual a regra sobre ALLOWED_DOMAINS?"
    ```
  - Documentar o resultado em comentario no teste B.2 (nota inline).
- Criterios de aceitacao:
  - [ ] Comentario de smoke test adicionado em `test_opencode_config.py::test_instructions_lists_dfe_rules` (nao exige execucao do opencode CLI na suite automatizada).

---

## Fase C — `tsx` canonizado como `devDependencies` (IMPORTANTE I13.1)

**Criterio**: `.opencode/package.json` separa `dependencies` (runtime: `@opencode-ai/plugin`, `@xenova/transformers`, `better-sqlite3`, `sqlite-vec`) de `devDependencies` (build/test: `tsx`). `npm install --prefix .opencode` continua instalando `tsx` (ja' pinned em 4.19.2). Smoke test E2E (`tests/integration/test_unified_harness.py::test_opencode_init_db_creates_db_in_opencode_rag`) nao muda de comportamento.

### Task C.1 — Mover `tsx` de `dependencies` para `devDependencies`

- Agent: Backend Engineer
- Input: nenhuma
- Diagnostico:
  - `.opencode/package.json:1-9`:
    ```json
    {
      "dependencies": {
        "@opencode-ai/plugin": "1.18.21",
        "@xenova/transformers": "2.17.2",
        "better-sqlite3": "11.5.0",
        "sqlite-vec": "0.1.6",
        "tsx": "4.19.2"
      }
    }
    ```
  - `tsx` e' usado em runtime apenas por:
    - `.opencode/rag/{init_db,summarize,embed,search,smoke_test}.ts` (executados via `npx tsx <path>`).
    - Nenhum desses e' carregado em producao pelo DFe-Agent (o runtime Python usa `python -m src.query`, nao `tsx`).
  - Justificativa semantica: `tsx` e' estritamente uma dependencia de dev (transforma TS em JS on-the-fly). Pertence a `devDependencies`.
  - Sem consequencia pratica para `npm install` (ambos os campos instalam por default).
- Output:
  - `.opencode/package.json` (estrutura nova):
    ```json
    {
      "dependencies": {
        "@opencode-ai/plugin": "1.18.21",
        "@xenova/transformers": "2.17.2",
        "better-sqlite3": "11.5.0",
        "sqlite-vec": "0.1.6"
      },
      "devDependencies": {
        "tsx": "4.19.2"
      }
    }
    ```
  - Sem mudanca em `package-lock.json` (dependencias ja' estao resolvidas; apenas reclassificadas).
- Criterios de aceitacao:
  - [ ] `git diff .opencode/package.json` mostra 1 linha removida (de dependencies) + 3 linhas adicionadas (cabecalho `devDependencies` + `tsx` + virgula).
  - [ ] `npm ls --prefix .opencode tsx` continua retornando `tsx@4.19.2` na arvore.
  - [ ] `Test-Path .opencode/node_modules/.bin/tsx.cmd` continua True (ja' instalado).
  - [ ] Suites previas continuam passando.

### Task C.2 — Gate anti-regressao em `test_opencode_config.py`

- Agent: QA Engineer
- Input: C.1 aplicada
- Output:
  - `tests/integration/test_opencode_config.py`: nova funcao `test_tsx_is_devdependency`:
    ```python
    def test_tsx_is_devdependency() -> None:
        """`tsx` deve estar em `devDependencies`, nao `dependencies`.
        
        Justificativa: `tsx` e' usado apenas em runtime de dev/test
        (smoke test E2E do RAG meta-cognitivo via `npx tsx`). Pertence
        a `devDependencies` por semantica npm.
        
        Sprint 13 I13.1 canonicalizou a posicao. Anti-regressao: se um
        futuro dev mover `tsx` de volta para `dependencies`, o teste
        falha.
        """
        pkg_json = (PROJECT_ROOT / ".opencode" / "package.json").read_text(
            encoding="utf-8"
        )
        pkg = json.loads(pkg_json)
        deps = pkg.get("dependencies", {})
        dev_deps = pkg.get("devDependencies", {})
        assert "tsx" not in deps, (
            f"`tsx` deve estar em `devDependencies`, nao `dependencies`; "
            f"obtido dependencies={list(deps.keys())}"
        )
        assert "tsx" in dev_deps, (
            f"`tsx` deve estar pinned em `devDependencies`; "
            f"obtido devDependencies={list(dev_deps.keys())}"
        )
    ```
  - Posicao: apos `test_no_dot_claude_reference_anywhere` (linha 90-100 atuais).
  - Cobertura: `tsx@4.19.2` (pin exato; segue convencao de `tests/unit/test_dependency_pinning.py`).
- Criterios de aceitacao:
  - [ ] Antes de C.1: teste falha com `AssertionError` ("`tsx` deve estar em `devDependencies`").
  - [ ] Depois de C.1: teste passa.
  - [ ] `pytest tests/integration/test_opencode_config.py` exit 0.

---

## Fase D — Unificar knowledge legado (IMPORTANTE I13.2)

**Criterio**: `.opencode/rag/knowledge/` contem apenas arquivos com metadata canonica (slug em `{dev, code-reviewer, session}`, paths `.opencode/`, datas `>= 2026-08-26`). O arquivo legado `2026-08-25-backend-engineer.md` ou e' (a) renomeado para slug `dev` e corrigido para apontar para `.opencode/rag/summarize.ts`, ou (b) apagado se a preservacao for preferida por design. Decisao: **renomear + reclassificar** (a), porque o conteudo semantico (causa raiz + fix do `download_pending`) ainda e' util para o `@dev` em sessoes futuras.

### Task D.1 — Renomear arquivo legado para slug canonico

- Agent: Backend Engineer
- Input: nenhuma
- Diagnostico:
  - `.opencode/rag/knowledge/2026-08-25-backend-engineer.md` foi gerado em 2026-08-25 (pre-Sprint 11). Conteudo:
    - **Bugs resolvidos com causa raiz**: docstring longa descrevendo bug do `discover_and_register` (sem try/except por portal; RequestException em 1 portal abortava o loop).
    - **Padroes adotados pelo time**: causa raiz + fix (try/except por item) + DECISION + TEAM_PATTERN + DIDNT_WORK + FOLLOW-UP + ARQUIVOS_ALTERADOS.
  - Conteudo e' canonico para `@dev` (owner de implementacao); deve ser preservado com slug `dev`.
  - Renomeacao: `2026-08-25-backend-engineer.md` → `2026-08-25-dev.md`.
- Output:
  - `Move-Item .opencode/rag/knowledge/2026-08-25-backend-engineer.md .opencode/rag/knowledge/2026-08-25-dev.md`.
  - Arquivo renomeado e' o mesmo conteudo (binario-identico), apenas o slug no filename muda.
  - **Decisao**: NAO rodar `embed.ts --file` novamente. O `content_hash` ja' existe no `rag.db` (knowledge_id pre-existente). Apenas o path canonico precisa apontar para o arquivo renomeado.
- Criterios de aceitacao:
  - [ ] `Get-ChildItem .opencode/rag/knowledge/` lista apenas 5 arquivos: 4 com slug `dev`/`feature-...` + 1 renomeado (`2026-08-25-dev.md`).
  - [ ] `Test-Path .opencode/rag/knowledge/2026-08-25-backend-engineer.md` retorna False.

### Task D.2 — Atualizar `knowledge.path` no `rag.db` para apontar ao arquivo renomeado

- Agent: Backend Engineer
- Input: D.1 aplicada
- Diagnostico:
  - Apos D.1, o `knowledge.path` no `rag.db` ainda aponta para `2026-08-25-backend-engineer.md` (path antigo). O `search.ts` retorna esse path no campo `path` do chunk, e o humano/leitor pode ficar confuso ao ver slug `backend-engineer` (removido em Sprint 11).
  - Solucao minima: `UPDATE knowledge SET path = '2026-08-25-dev.md' WHERE path = '2026-08-25-backend-engineer.md'`.
  - Aplicar via `python -c "import sqlite3; ..."` ad-hoc, NAO via `RagIndexer` (a regra "`Escrita na base passa por portoes explicitos: so' apply_pending (migrations), RagIndexer.ingest_pending e python -m src.ragctl reindex escrevem em documents/vec_chunks`" do `AGENTS.md > Nunca fazer` aplica-se a `documents`/`vec_chunks`; `knowledge` e' tabela do RAG meta-cognitivo, nao do RAG fiscal).
  - **Mais simples**: rodar `embed.ts --force --file 2026-08-25-dev.md` para reclassificar e re-inserir com o path novo (idempotente se content_hash ja' existe).
- Output:
  - **Opcao A (preferida — usa portao existente)**: rodar
    ```bash
    cd .opencode && npx tsx rag/embed.ts --file rag/knowledge/2026-08-25-dev.md --force
    ```
    O `--force` ignora idempotencia por hash e re-insere; o path novo fica canonico.
  - **Opcao B (fallback se `tsx` ausente)**: `python -c` ad-hoc no `rag.db`. Documentar como escape hatch no `SKILL.md` apenas se Opcao A falhar.
- Criterios de aceitacao:
  - [ ] `python -c "import sqlite3; ..."` consulta `SELECT path FROM knowledge WHERE path LIKE '%2026-08-25%'` retorna apenas `2026-08-25-dev.md`.
  - [ ] `npx --prefix .opencode tsx .opencode/rag/search.ts -q "backend-engineer" -a dev --top-k 3` NAO retorna mais chunks com slug `backend-engineer` (vazio ou chunks de outros arquivos).
  - [ ] `npx --prefix .opencode tsx .opencode/rag/search.ts -q "download_pending RequestException" -a dev --top-k 3` retorna o chunk do fix preservado (path `2026-08-25-dev.md`).

### Task D.3 — Gate anti-regressao em `test_unified_harness.py`

- Agent: QA Engineer
- Input: D.1 + D.2 aplicadas
- Output:
  - `tests/integration/test_unified_harness.py`: nova funcao `test_rag_knowledge_no_legacy_slugs`:
    ```python
    def test_rag_knowledge_no_legacy_slugs() -> None:
        """Nenhum arquivo em ``.opencode/rag/knowledge/`` usa slug de agent removido.
        
        Agents removidos em Sprint 11 (backend-engineer, ml-engineer,
        prompt-engineer, qa-engineer) NAO devem aparecer em filenames
        de knowledge (pattern: ``<YYYY-MM-DD>-<slug>.md``).
        
        Sprint 13 I13.2 canonicalizou o legado de 2026-08-25.
        Anti-regressao: se um hook futuro gerar .md com slug
        legacy, este teste falha.
        """
        knowledge_dir = PROJECT_ROOT / ".opencode" / "rag" / "knowledge"
        legacy_slugs = {
            "backend-engineer",
            "ml-engineer",
            "prompt-engineer",
            "qa-engineer",
            "build",
            "plan",
        }
        offenders: list[str] = []
        for path in knowledge_dir.glob("*.md"):
            stem = path.stem
            # Filename esperado: <YYYY-MM-DD>-<slug>.md ou
            # <YYYY-MM-DD>-<slug>-<contexto>.md
            parts = stem.split("-", 3)
            if len(parts) < 4:
                continue
            slug = parts[3]
            if slug in legacy_slugs:
                offenders.append(path.name)
        assert not offenders, (
            f"Knowledge dir tem arquivos com slugs legacy (Sprint 11 I11.2): "
            f"{offenders}"
        )
    ```
  - Posicao: apos `test_AGENTS_md_no_active_claude_paths` (linha 291 atuais).
  - Edge case: arquivos como `2026-08-26-feature-code-reviewer-hardening.md` (parts[3] = "feature") sao OK (slug canonico). Arquivos como `2026-08-26-sprint-8-meta-rag.md` (parts[3] = "sprint") tambem sao OK (slug contextual).
  - Considerar `2026-08-25-backend-engineer.md` se ainda existir (deve falhar ate' D.1).
- Criterios de aceitacao:
  - [ ] Antes de D.1: teste falha com `AssertionError` (slug `backend-engineer` listado).
  - [ ] Depois de D.1+D.2: teste passa.
  - [ ] `pytest tests/integration/test_unified_harness.py::test_rag_knowledge_no_legacy_slugs` exit 0.

---

## Fase E — Documentacao e finalizacao (PARCIAL)

### Task E.1 — Atualizar `AGENTS.md` com decisoes Sprint 13

- Agent: Backend Engineer
- Output:
  - Adicionar bloco `## Decisoes resolvidas (Sprint 13)` ao final da secao de
    decisoes resolvidas em `AGENTS.md`, com 4 decisoes principais:
    1. `opencode.json > instructions` agora carrega `.opencode/rules/dfe-rules.md`
       (5a rule canonica, BLOQUEANTE B13.1). Gate novo em
       `test_opencode_config.py::test_instructions_lists_dfe_rules` impede
       regressao.
    2. `.opencode/package.json` separa `dependencies` (4 runtime) de
       `devDependencies` (1: `tsx`). SUGESTAO S1 do Sprint 12 implementada.
       Gate novo em `test_opencode_config.py::test_tsx_is_devdependency`.
    3. `.opencode/rag/knowledge/2026-08-25-backend-engineer.md` renomeado para
       `2026-08-25-dev.md` (slug canonico) e re-embedado via `embed.ts --force`.
       Conteudo semantico preservado; metadata canonica. Gate novo em
       `test_unified_harness.py::test_rag_knowledge_no_legacy_slugs` impede
       ressurreicao de slugs legacy (`backend-engineer`, `ml-engineer`, etc.).
    4. `scripts/demo_sprint2.ps1` e `scripts/demo_sprint2.sh` removidos
       (orfaos pre-Sprint 12). `scripts/` agora contem apenas `check_env.ps1` +
       `demo_cli.py`.

### Task E.2 — Atualizar `PLAN_SPRINT7.md` (template) nao necessario

- Agent: Backend Engineer
- Output: nenhum. `PLAN_SPRINT7.md` permanece como referencia canonica de
  template para sprints de remediacao. Este plano segue o mesmo formato.

### Task E.3 — Marcar este plano como concluido

- Agent: Backend Engineer
- Output:
  - Bloco `## Decisoes resolvidas (Sprint 13)` adicionado a `AGENTS.md`.
  - Este plano (`PLAN_SPRINT13.md`) pode permanecer no repo para auditoria
    ou ser arquivado em `docs/archive/PLAN_SPRINT13.md`. **Decisao**:
    manter no raiz seguindo o padrao `PLAN_SPRINT<N>.md` (consistente com
    Sprints 2-12).

---

## Verificacao manual dos BLOQUEANTE

Comandos shell a serem executados **apos** B.1 + B.2 aplicadas:

```powershell
# BLOQUEANTE B13.1: dfe-rules.md carregada pelo opencode
$cfg = Get-Content opencode.json -Raw | ConvertFrom-Json
$cfg.instructions | ForEach-Object { Write-Host $_ }
# esperado: 5 entries em .opencode/rules/ + 1 entry "AGENTS.md", incluindo
# ".opencode/rules/dfe-rules.md".

# BLOQUEANTE B13.1: rule existe no disco
Test-Path .opencode/rules/dfe-rules.md
# esperado: True.

# Gate automatizado
pytest tests/integration/test_opencode_config.py -v
# esperado: 6 tests passed (3 previos + 3 novos).

# IMPORTANTE I13.1: tsx em devDependencies
Get-Content .opencode/package.json -Raw | Select-String -Pattern 'tsx'
# esperado: 1 match apenas, dentro de "devDependencies".

# IMPORTANTE I13.2: knowledge legado renomeado
Get-ChildItem .opencode/rag/knowledge/
# esperado: 5 arquivos, nenhum com slug "backend-engineer".

# Suite geral
pytest tests/ --cov=src --cov-fail-under=80
# esperado: exit 0.
```

---

## Apendice A — Riscos conhecidos e mitigacoes

| Risco | Probabilidade | Impacto | Mitigacao |
|-------|---------------|---------|-----------|
| B.1 adicionar `dfe-rules.md` ao `instructions` causa conflito de regras (overlap com `seguranca.md` que ja' menciona `ALLOWED_DOMAINS`) | Baixa | Baixo | `dfe-rules.md` e' domain-specific (DFe fiscal); `seguranca.md` e' transversal. Semantica complementar, nao conflitante. |
| B.3 smoke test manual depende de opencode CLI estar instalado | Media | Baixo | Documentar em comentario do teste (B.2); suite automatizada NAO exige runtime do CLI. |
| C.1 mover `tsx` para `devDependencies` quebra `npm install --prefix .opencode` em ambientes onde `--production` ou `--omit=dev` esta' setado | Baixa | Alto | Documentar no `.opencode/package.json` (README do package). `npm install --prefix .opencode` (sem flags) continua instalando tudo. Workaround: `npm install --prefix .opencode --include=dev`. |
| D.2 `embed.ts --force` duplica knowledge entries se o hash ja' existe | Baixa | Medio | `--force` sobrescreve (nao duplica); o `embedOneFile` em `embed.ts:163-168` ja' trata esse caso (`if existing and not force: skip`). Gate manual: `SELECT count(*) FROM knowledge WHERE path LIKE '%2026-08-25%'` deve retornar 1. |
| D.3 gate de slugs legacy for restritivo demais (falso positivo em filenames que coincidentemente comecam com "backend-", "ml-", etc.) | Baixa | Baixo | Pattern `parts[3]` exige 4+ partes separadas por `-`. Nenhum .md canonico ate' hoje usa 4 partes com prefixo legacy. |
| Renomear arquivo .md pode invalidar embeddings pre-existentes (vec_knowledge) | Baixa | Baixo | `vec_knowledge` indexa por `knowledge_id` (INTEGER), nao por path. Renomear path nao invalida embeddings; apenas a metadata `path` e' atualizada via D.2. |

## Apendice B — Itens fora do escopo desta Sprint (follow-up)

1. **Consolidar `.opencode/rag/knowledge/` em uma migracao similar a Sprint 12**:
   aplicar pattern `<YYYY-MM-DD>-dev-<contexto>.md` retroativamente nos 4 arquivos
   pre-existentes (`2026-08-26-feature-code-reviewer-hardening.md`,
   `2026-08-26-feature-plan-sprint11.md`,
   `2026-08-26-feature-unify-harness.md`,
   `2026-08-26-sprint-8-meta-rag.md`). Sugestao para Sprint 14+ (nao bloqueia).
2. **Adicionar test que valida `search.ts` retorna apenas categorias validas
   (4 canonicais)** — extensao natural de D.3. Pode entrar em Sprint 14.
3. **Mover `knowledge/` para `.opencode/rag/learnings/` ou renomear `summarize.ts`
   para deixar claro que o subdiretorio e' do RAG meta-cognitivo** — SUGESTAO
   estetica, NAO bloqueia.
4. **Implementar pre-commit hook que valida `opencode.json > instructions`
   sincronizado com `.opencode/rules/*.md`** — evita drift futuro. Pode ser
   adicionado ao `dev/pre_tool_use.py` ou como novo hook de project.
5. **Mover `scripts/demo_cli.py` para `.opencode/scripts/` ou
   `.opencode/skills/dfe-fiscal/scripts/`** — alinhamento com estrutura
   unificada. NAO bloqueia; decisao para Sprint 14+.
6. **Documentar o protocolo "knowledge legado deve ser renomeado ao slug
   canonico do agent que o produziu"** em `.opencode/rules/convencoes-gerais.md`
   (novo item "Padrao de naming para knowledge"). Sugestao para Sprint 14.

## Apendice C — Resumo de comandos para reproduzir localmente

```powershell
# 0. Ambiente
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 1. Limpar orfaos em scripts/
Remove-Item -LiteralPath "scripts\demo_sprint2.ps1"
Remove-Item -LiteralPath "scripts\demo_sprint2.sh"

# 2. Carregar dfe-rules.md no opencode.json (BLOQUEANTE B13.1)
# Editar opencode.json > instructions: adicionar ".opencode/rules/dfe-rules.md"
# apos ".opencode/rules/tests.md"

# 3. Mover tsx para devDependencies (IMPORTANTE I13.1)
# Editar .opencode/package.json: remover "tsx": "4.19.2" de dependencies,
# adicionar bloco "devDependencies": { "tsx": "4.19.2" }

# 4. Renomear knowledge legado (IMPORTANTE I13.2)
Move-Item .opencode/rag/knowledge/2026-08-25-backend-engineer.md .opencode/rag/knowledge/2026-08-25-dev.md
npx --prefix .opencode tsx .opencode/rag/embed.ts --file .opencode/rag/knowledge/2026-08-25-dev.md --force

# 5. Validar tudo
pytest tests/ --cov=src --cov-fail-under=80
# esperado: exit 0, cobertura >= 80%

# 6. Sanidade final
Get-ChildItem .opencode/rag/knowledge/
# esperado: 5 arquivos, nenhum com slug legacy.
```

## Apendice D — Metricas esperadas

| Metrica | Antes (Sprint 12) | Depois (Sprint 13) |
|---------|-------------------|--------------------|
| Rules carregadas via `instructions` | 4 | **5** |
| `tsx` em `devDependencies` | nao (em `dependencies`) | **sim** |
| Knowledge files com slug canonico | 4 de 5 (80%) | **5 de 5 (100%)** |
| Scripts em `scripts/` | 4 (2 canonicos + 2 orfaos) | **2 (canonicos)** |
| Testes novos | 727 + 30 = 757 (Sprint 12) | **+ 3 (B.2 + C.2 + D.3) = 760** |
| Cobertura | 85.11% | **>= 85.11% (gate 80% mantido)** |
| Knowledge files com metadata obsoleta (ref `.claude/scripts/`) | 1 (backend-engineer.md) | **0** |

## Apendice E — Itens cobertos por task

| ID | Task | Tipo | Resolvido por |
|----|------|------|---------------|
| B13.1 | `.opencode/rules/dfe-rules.md` nao carregada pelo opencode | BLOQUEANTE | Fase B |
| I13.1 | `tsx` em `dependencies` (deveria ser `devDependencies`) | IMPORTANTE | Fase C |
| I13.2 | Knowledge legado com slug `backend-engineer` (agent removido) | IMPORTANTE | Fase D |
| P13.1 | Scripts `demo_sprint2.{ps1,sh}` orfaos em `scripts/` | PARCIAL | Fase A |

Total: 1 BLOQUEANTE + 2 IMPORTANTE + 1 PARCIAL = 4 itens.