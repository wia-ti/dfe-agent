---
description: Pipeline de deployment do DFe-Agent — push commits, criar tags, publicar npm e/ou criar GitHub Release. Substitui o CI (removido em Sprint 18). Invoca agent `deployer` (unico autorizado a fazer git push/npm publish/gh release). Gate humano explicito antes de cada acao destrutiva.
agent: deployer
model: PROVIDER/MiniMax-M3
---

# /deploy — Pipeline de deployment do DFe-Agent

Voce disparou o pipeline canonico de deployment do DFe-Agent. Sua tarefa
NAO e' responder a pergunta do usuario: e' **executar uma acao de
deployment** descrita em `$ARGUMENTS` (modo bare, `--tag <vX.Y.Z>`,
`--npm`, ou `--release <tag> [notas]`) ate que esteja pronta para
entrega humana. O usuario (humano) e' o arbitro final do gate
destrutivo — voce NAO publica npm, NAO cria release, NAO deleta tag
remota sem confirmacao explicita via Fase 4.

> O CI do projeto foi descontinuado em 2026-08-27 (Sprint 18). Antes
> da Sprint 18, os 3 workflows em `.github/workflows/` falhavam
> consistentemente (3 jobs `if: false`, 22+ runs FAILURE consecutivos).
> Toda publicacao agora passa por este comando e pelo agent
> `@deployer`.

---

## Fase 0 — Briefing obrigatorio (ler tudo ANTES de planejar)

| # | Acao | Comando / tool |
|---|---|---|
| 0.1 | Confirmar cwd do projeto | `bash: pwd && ls AGENTS.md SPEC.md PLAN.md .opencode/ 2>/dev/null` |
| 0.2 | Estado do git | `bash: git rev-parse --is-inside-work-tree && git status --short && git log --oneline -5` |
| 0.3 | Ler AGENTS.md secao Sprint 18 | `read: AGENTS.md > Decisoes resolvidas (Sprint 18)` |
| 0.4 | Ler definition do agent Deployer | `read: .opencode/agent/deployer.md` |
| 0.5 | Recuperar aprendizados anteriores do RAG meta-cognitivo (top-5 do agent `deployer`) | `bash: npx --prefix .opencode tsx .opencode/rag/search.ts -q "$ARGUMENTS" -a deployer --top-k 5` |
| 0.6 | Sintetizar em 3 bullets: (a) o que sera' deployed, (b) working tree status, (c) gate humano pendente | interno |

> **Gate 0**: se algum dos arquivos de 0.3/0.4 estiver ausente, ABORTE
> com "Este diretorio nao parece ser o root do DFe-Agent (faltam
> AGENTS.md ou .opencode/agent/deployer.md)."

---

## Fase 1 — Detectar modo

O comando `/deploy` aceita 4 modos (mutuamente exclusivos):

| Modo | Sintaxe | Acoes |
|---|---|---|
| **Bare** | `/deploy` | Apenas `git push`. |
| **Tag** | `/deploy --tag <vX.Y.Z>` | `git push` + `git tag <vX.Y.Z>` + `git push origin <vX.Y.Z>`. |
| **NPM** | `/deploy --npm` | `git push` + tag `v0.0.1-sprint<N>` + `npm publish --access public --provenance` em `packages/dfe-agent/`. |
| **Release** | `/deploy --release <tag> [notas]` | `git push` + tag + `gh release create <tag> --notes <notas>` (substitui workflow `publish-base.yml` removido). |

Comandos compostos (executados na ordem):
- `/deploy --tag v0.1.6 --npm`: push + tag + npm publish.
- `/deploy --tag v1.2.5 --release`: push + tag + gh release.

---

## Fase 2 — Verificar working tree (gate canonico)

Antes de qualquer acao destrutiva, validar:

```bash
git status --short
```

- **Working tree limpo** (sem saida): prosseguir.
- **Working tree com arquivos nao-rastreados OU modificados**: ABORTAR
  com mensagem clara apontando o que precisa ser commitado antes.
  Deployer NAO faz commit (gate em `pre_tool_use.py`).

```bash
git log origin/main..HEAD --oneline  # commits locais nao-pushed
```

- **Sem commits locais**: prosseguir (working tree estava limpo).
- **Com commits locais**: prosseguir (esses serao pushed).

```bash
git fetch origin && git status
```

- **Sem divergencia**: prosseguir.
- **Com divergencia** (`Your branch is behind`, ou seja, origin tem
  commits que local nao tem): rodar `git pull --rebase` (allow list)
  e re-validar.

### Gate 1 (passa para Fase 3)

- Working tree limpo (sem untracked ou modified).
- Sem divergencia com origin.
- Log em `storage/agent_hooks.log` (modo detectado).

---

## Fase 3 — Executar acao (conforme modo)

### 3.1 — Bare (`/deploy`)

```bash
git push
```

Se houver tags locais: `git push --tags` (allow list).

### 3.2 — Tag (`/deploy --tag <vX.Y.Z>`)

```bash
git push
git tag <vX.Y.Z>
git push origin <vX.Y.Z>
```

### 3.3 — NPM (`/deploy --npm`)

```bash
git push
git tag v0.0.1-sprint<N>  # N = sprint atual (ver AGENTS.md > Decisoes resolvidas (Sprint N))
git push origin v0.0.1-sprint<N>
cd packages/dfe-agent && npm publish --access public --provenance
cd ../..
```

> **Pre-condicao NPM**: `npm whoami` deve retornar usuario valido.
> Se falhar, ABORTAR e instruir usuario a rodar `npm login` antes.

### 3.4 — Release (`/deploy --release <tag> [notas]`)

```bash
git push
git tag <tag>
git push origin <tag>
gh release create <tag> --notes <notas>
```

Substitui o workflow `publish-base.yml` removido. Para upload de
assets (ex.: `dfe.db.gz`):

```bash
gh release upload <tag> storage/dfe.db.gz storage/dfe.db.gz.sha256
```

### Gate 2 (passa para Fase 3.5 — gate humano)

Acoes destrutivas exigem confirmacao explicita antes de executar:

| Acao | Por que e' destrutiva |
|---|---|
| `--npm` | Publica no registry npm (visivel publicamente; `npm unpublish` tem janela de 72h). |
| `--release` | Cria GitHub Release (visivel publicamente; URL estavel). |
| `--tag <vX.Y.Z>` (especialmente com overwrite de tag existente) | Cria tag pushed; pode quebrar consumers. |
| `git push --force` | Reescreve historico; colaboradores perdem commits. |
| `git push origin :refs/tags/<tag>` | Deleta tag remota; perde o historico do release. |

Formato do gate humano (imprimir ANTES de executar a acao destrutiva):

```
============================================
ACAO DESTRUTIVA DETECTADA
============================================
Modo: --npm
Tag que sera criada: v0.0.1-sprint18
Pacote npm a ser publicado: @wiati/dfe-agent versao 0.1.5
URL do registry: https://registry.npmjs.org/@wiati/dfe-agent
Consequencia: publicacao visivel em https://www.npmjs.com/package/@wiati/dfe-agent
============================================
Confirma execucao? Responda "sim, executar" para prosseguir ou
qualquer outra coisa para abortar.
============================================
```

Aguardar resposta do humano. Se NAO for "sim, executar": abortar
com mensagem "abortado pelo humano na Fase 3" e NAO prosseguir.

### 3.5 — Validar publicacao (apos gate humano)

Para `--npm`:
```bash
npm view @wiati/dfe-agent version
```

Para `--release`:
```bash
gh release view <tag>
```

### Gate 3 (passa para Fase 4)

- Comando executou com exit 0.
- Validacao confirma que o efeito desejado aconteceu (versao npm
  publicada OU release criada).

---

## Fase 4 — RAG depois (sincrono)

Gravar `.opencode/rag/knowledge/<date>-deployer-<contexto>.md` com:

```markdown
# Deployment -- <modo> -- <YYYY-MM-DD>

> Origem: /deploy $ARGUMENTS
> Agent: @deployer
> Contexto: <descricao curta do que foi deployed>

## Comando(s) executado(s)
- <lista de comandos bash executados, com exit code>

## Validacao
- <resultado de `npm view` ou `gh release view` ou `git log --oneline -1`>

## Decisao arquitetural (se houver)
- <mudanca de decisao D<N>.x>

## Padroes adotados
- <padroes novos observados>

## Arquivos modificados
- <paths tocados, se houver>
```

Depois, **sincronamente**:

```bash
npx --prefix .opencode tsx .opencode/rag/embed.ts --file .opencode/rag/knowledge/<arquivo>.md
```

### Gate 4

- Arquivo `.opencode/rag/knowledge/<...>.md` criado.
- `embed.ts --file` retornou 0.
- `npx --prefix .opencode tsx .opencode/rag/search.ts -q "deployer <modo>" -a deployer --top-k 3` retorna >=1 hit (sanity check).

---

## Fase 5 — Finalizacao e entrega ao humano

### 5.1 — Checklist de saida

- [ ] Working tree verificado na Fase 2.
- [ ] Comando (ou comandos) executado(s) na Fase 3.
- [ ] Gate humano respeitado (se modo destrutivo).
- [ ] Validacao na Fase 3.5 confirma o efeito.
- [ ] RAG knowledge file criado e embedado na Fase 4.

### 5.2 — Relatorio final (impresso ao humano)

```markdown
## Deployment -- <modo> -- <YYYY-MM-DD>

**Argumento original**: `$ARGUMENTS`
**Agent**: `@deployer`
**Plano**: este comando

### Comando(s) executado(s)
<N> comando(s) bash (todos com exit 0)

### Validacao
- npm view / gh release view / git log (especifico do modo)

### Working tree
- antes: <estado inicial>
- depois: <estado final>

### RAG
- .opencode/rag/knowledge/<arquivo>.md criado e embedado
- search sanity: <N> hits para "<query>"

### Proxima acao humana
- Confirmar efeito no destino (npm registry / GitHub Releases / origin).
- Se necessario, rodar `git fetch --tags` em outras maquinas.
```

### 5.3 — Gate 5 (entrega ao humano)

Imprimir o relatorio 5.2 e parar. NAO fazer novas acoes de deployment
sem novo `/deploy`.

---

## Guardrails inegociaveis (valem em qualquer fase)

- **Gate humano**: acoes destrutivas (`--npm`, `--release`, `--tag`,
  `--force`, delete de tag) exigem confirmacao explicita "sim,
  executar". Sem confirmacao = abortar.
- **Sem edicao de arquivos**: deployer tem `permission.edit: deny` e
  hook BLOQUEIA Write/Edit. NAO tentar bypass.
- **Sem commit**: `git commit` exige `--allow-empty` (gate em
  `pre_tool_use.py`). NAO escrever historico.
- **Sem recriar CI**: gate anti-regressao em
  `tests/integration/test_no_legacy_ci.py` impede ressurreicao dos
  3 workflows removidos.
- **Sem npm unpublish**: politica npm 2024+ proibe exceto dentro de
  72h apos publish. NAO tentar.

## Quando abortar (e reportar ao humano)

| Sintoma | Acao |
|---|---|
| `git rev-parse` falha ou AGENTS.md ausente | Abortar — nao e' o repo do DFe-Agent |
| Working tree com arquivos untracked/modified | Abortar e instruir usuario a commitar antes |
| `npm whoami` falha em `--npm` | Abortar e instruir usuario a rodar `npm login` |
| Humano NAO responde "sim, executar" no gate | Abortar com mensagem "abortado pelo humano na Fase 3" |
| `npm publish` retorna erro de versao ja' publicada | Bump `packages/dfe-agent/package.json` e re-rodar `/deploy --npm` |
| Hook `deployer/pre_tool_use.py` BLOQUEIA comando | Reportar como incidente; sugerir usar `@dev` para tarefas de codigo |

## Para debugar este command

- `opencode command list` deve listar `/deploy`.
- `opencode agent list` deve listar `deployer` como primary.
- Logs de hooks em `storage/agent_hooks.log` (linhas com `[deployer]`).
- Validar dispatch: `DFE_ACTIVE_AGENT=deployer npx --prefix .opencode tsx .opencode/rag/search.ts -q "deployer" -a deployer --top-k 3`.