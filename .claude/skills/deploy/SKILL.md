---
name: deploy
description: Pipeline de deployment do DFe-Agent — envia os commits para o GitHub (o semantic-release no GitHub Actions gera versao, tag, CHANGELOG, GitHub Release e npm) e, com --base, publica a base RAG na release rolante `rag-base`. Roda no agent `deployer`, com gate humano (prompt de permissao) antes de cada acao destrutiva.
argument-hint: "[--base]"
disable-model-invocation: true
context: fork
agent: deployer
background: false
---
# /deploy — Pipeline de deployment do DFe-Agent

Voce disparou o pipeline canonico de deployment do DFe-Agent. Sua tarefa
NAO e' responder a pergunta do usuario: e' **executar a acao de
deployment** descrita em `$ARGUMENTS` (modo bare ou `--base`) ate' que
esteja pronta para entrega humana. O humano e' o arbitro final: cada
acao destrutiva passa pelo prompt de permissao do Claude Code.

> **Sprint 20 — versionamento automatico.** Tag `vX.Y.Z`, CHANGELOG,
> GitHub Release e `npm publish` sao do **semantic-release** no GitHub
> Actions (`.github/workflows/release.yml` + `.releaserc.json`). Ele roda
> a cada push na `main`, le os Conventional Commits e decide a versao
> (`fix` = patch, `feat` = minor, `!`/`BREAKING CHANGE` = major). Os
> modos antigos `--tag`, `--npm` e `--release` foram removidos, e o hook
> bloqueia tag `v*`, `npm publish` e release `v*` manuais.
>
> **A base RAG nao vive no git.** So' `storage/dfe.db.gz.sha256` e'
> versionado; o `dfe.db.gz` vai para a release rolante `rag-base` e o CI
> copia para cada `vX.Y.Z` (conferindo o sha versionado).

---

## Fase 0 — Briefing obrigatorio (ler tudo ANTES de planejar)

| # | Acao | Comando / tool |
|---|---|---|
| 0.1 | Confirmar cwd do projeto | `bash: ls AGENTS.md CLAUDE.md .claude/agents/deployer.md` |
| 0.2 | Estado do git | `bash: git status --short && git log --oneline -5 && git branch --show-current` |
| 0.3 | Ler AGENTS.md secao Sprint 20 | `read: AGENTS.md > Decisoes resolvidas (Sprint 20)` |
| 0.4 | Ler definition do agent Deployer | `read: .claude/agents/deployer.md` |
| 0.5 | Recuperar aprendizados anteriores do RAG meta-cognitivo (top-5 do agent `deployer`) | `bash: npx tsx .claude/rag/search.ts -q "$ARGUMENTS" -a deployer --top-k 5` |
| 0.6 | Sintetizar em 3 bullets: (a) o que sera' enviado, (b) working tree, (c) gate humano pendente | interno |

> **Gate 0**: se algum dos arquivos de 0.3/0.4 estiver ausente, ABORTE
> com "Este diretorio nao parece ser o root do DFe-Agent (faltam
> AGENTS.md ou .claude/agents/deployer.md)."

---

## Fase 1 — Detectar modo

| Modo | Sintaxe | Acoes |
|---|---|---|
| **Bare** | `/deploy` | `git push` da branch atual. Na `main`, dispara o semantic-release. |
| **Base** | `/deploy --base` | Publica `storage/dfe.db.gz` + `.sha256` na release `rag-base` e depois faz `git push`. |

### Pre-condicao do `--base` (feita ANTES pelo `@dev`, nao pelo deployer)

O deployer nao gera arquivo nem commita. Antes do `/deploy --base`, na
sessao principal:

```bash
python -m src.ragctl export            # gera storage/dfe.db.gz + storage/dfe.db.gz.sha256
git add storage/dfe.db.gz.sha256
git commit -m "fix(rag): atualizar base RAG com novas notas tecnicas"
```

O commit `fix(rag)` faz o semantic-release gerar um patch; o CI anexa a
base nova a essa release.

---

## Fase 2 — Verificar working tree (gate canonico)

```bash
git status --short
```

- **Limpo**: prosseguir.
- **Com arquivos modificados ou nao rastreados**: ABORTAR apontando o que
  precisa ser commitado antes (o commit e' do `@dev`).

```bash
git fetch origin && git status -sb
```

- **Atras do origin**: `git pull --rebase` e re-validar.

Para `--base`, validar tambem:

```bash
ls -la storage/dfe.db.gz storage/dfe.db.gz.sha256
git log origin/main..HEAD --oneline -- storage/dfe.db.gz.sha256
```

- `storage/dfe.db.gz` ausente: ABORTAR ("rode `python -m src.ragctl export` antes").
- Nenhum commit local tocando o `.sha256`: ABORTAR ("commite o sha novo antes;
  sem isso o CI recusa a base").

---

## Fase 3 — Executar acao (gate humano)

Imprimir ANTES de executar:

```
============================================
ACAO DESTRUTIVA DETECTADA
============================================
Modo: --base | bare
Branch: <branch>   Commits a enviar: <N>
Release rag-base: <sera criada | sera atualizada (--clobber)>
Consequencia: push na main dispara o semantic-release (tag + GitHub Release + npm)
============================================
```

A confirmacao real e' o **prompt de permissao** do Claude Code
(`.claude/settings.json > permissions.ask` cobre `git push` e
`gh release`). Prompt negado = abortar com "abortado pelo humano na Fase 3".

### 3.1 — Base (`--base`), sempre ANTES do push

```bash
gh release view rag-base --json tagName
# se nao existir:
gh release create rag-base --title "Base RAG (rolante)" --latest=false --notes "Base RAG do DFe-Agent. Atualizada por /deploy --base; copiada para cada vX.Y.Z pelo CI."
gh release upload rag-base storage/dfe.db.gz storage/dfe.db.gz.sha256 --clobber
```

O upload vem antes do push porque o CI confere o sha da `rag-base`
contra o sha versionado assim que o push chega.

### 3.2 — Push (bare e `--base`)

```bash
git push -u origin <branch>
```

### 3.3 — Validar

```bash
gh release view rag-base --json assets --jq ".assets[].name"   # --base
git log origin/<branch> --oneline -1
```

Na `main`, informar ao humano que o workflow `release` foi disparado e
onde acompanhar: `https://github.com/wia-ti/dfe-agent/actions`.

---

## Fase 4 — RAG depois (sincrono)

Gravar `.claude/rag/knowledge/<date>-deployer-<contexto>.md` com:

```markdown
# Deployment -- <modo> -- <YYYY-MM-DD>

> Origem: /deploy $ARGUMENTS
> Agent: @deployer

## Comando(s) executado(s)
- <lista de comandos bash executados, com exit code>

## Validacao
- <resultado de `gh release view` ou `git log --oneline -1`>
```

Depois, **sincronamente**:

```bash
npx tsx .claude/rag/embed.ts --file .claude/rag/knowledge/<arquivo>.md
```

---

## Fase 5 — Relatorio ao humano

```markdown
## Deployment -- <modo> -- <YYYY-MM-DD>

- Push: <branch> -> origin (<N> commits)
- rag-base: <sha curto> (so' em --base)
- Release: o semantic-release decide a versao no Actions (link acima)
- Proxima acao humana: acompanhar o workflow `release`
```

Imprimir o relatorio e parar.

---

## Guardrails inegociaveis

- **Gate humano**: `git push` e `gh release` passam pelo prompt de permissao.
- **Sem edicao de arquivos e sem commit**: o deployer so' envia o que o
  `@dev` ja' commitou.
- **Sem versionamento manual**: `git tag v*`, `git push --tags`,
  `npm publish`, `npm version` e `gh release create|upload|delete v*`
  sao bloqueados pelo hook (o semantic-release e' o dono).
- **Sem force push** sem pedido explicito do humano.

## Quando abortar (e reportar ao humano)

| Sintoma | Acao |
|---|---|
| AGENTS.md ausente | Abortar: nao e' o repo do DFe-Agent |
| Working tree sujo | Abortar e pedir o commit ao `@dev` |
| `--base` sem `storage/dfe.db.gz` ou sem commit do sha | Abortar e instruir `python -m src.ragctl export` + commit `fix(rag)` |
| `gh auth status` falha | Abortar e pedir `gh auth login` |
| Prompt de permissao negado | Abortar com "abortado pelo humano na Fase 3" |
| Hook bloqueia comando | Reportar como incidente |
