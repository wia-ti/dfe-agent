# Deployment -- --base -- 2026-10-01

> Origem: /deploy --base
> Agent: @deployer (nota gravada pelo @dev a partir do relatorio do deployer)

## Comando(s) executado(s)

- `python -m src.ragctl export` (@dev, exit 0): o `storage/dfe.db.gz` nao estava no disco e foi regerado. O export e' deterministico: sha256 `e9f7b1c67e6fcdd18f1a739fd0d24786a484609eadaa4fe1be8c03229fc39acc`, identico ao `.sha256` ja' commitado em 49668d2, entao nao houve commit novo e o working tree ficou limpo.
- `gh release view rag-base` -> "release not found" (primeiro deploy do fluxo Sprint 20).
- `gh release create rag-base --title "Base RAG (rolante)" --latest=false --notes ...` (exit 0).
- `gh release upload rag-base storage/dfe.db.gz storage/dfe.db.gz.sha256 --clobber` (exit 0): `dfe.db.gz` 67741979 bytes; o digest do asset calculado pelo GitHub bate com o sha versionado.
- `git push -u origin main` (exit 0): `2d89a0e..49668d2`, 2 commits (feat(release) + fix(rag)); disparou o workflow `release` (run 36875721506).

## Validacao

- `gh release view rag-base`: assets `dfe.db.gz` e `dfe.db.gz.sha256`; URL https://github.com/wia-ti/dfe-agent/releases/tag/rag-base.
- `git log origin/main --oneline -1`: `49668d2 fix(rag): publicar base RAG na release rag-base`.

## O que nao funcionou e por que

- O `search.ts` do RAG antes (Fase 0.5) falhou no shutdown do Node no Windows com `Assertion failed: (env) != nullptr` em `node::RemoveEnvironmentCleanupHook`, sem devolver resultados. A causa provavel e' uma extensao nativa (sqlite-vec / onnxruntime) desmontada no encerramento do processo. O deploy seguiu sem os aprendizados anteriores.
- A Fase 4 (RAG depois) falhou porque o deployer nao tem `Write`/`Edit` e o hook bloqueia redirecionamento `>`, entao ele nunca conseguiu gravar a nota. Nenhuma nota `*-deployer-*` existia ate' esta.

## Decisao de arquitetura

- Optamos por mover a Fase 4 do `/deploy` para o @dev (sessao principal): o deployer devolve o relatorio e o @dev grava `.claude/rag/knowledge/<data>-deployer-<contexto>.md` e roda `embed.ts --agent deployer`. O motivo e' manter o deployer sem `Write`/`Edit` (seria backdoor), que e' a regra de seguranca do agent.
