# Aprendizados -- sprint-8-meta-rag -- 2026-08-26

> Extraido automaticamente via pipeline summarize.ts/embed.ts apos
> implementacao do Sprint 8 (restauracao do RAG meta-cognitivo).

## Bugs resolvidos com causa raiz

- **B8.1**: O RAG meta-cognitivo (`.claude/rag.db`) nao capturava
  aprendizados desde 2026-08-25 porque a migracao dos Sprints 4-6
  substituiu os hooks que disparavam `summarize.ts + embed.ts` por
  `stop.py` que apenas rodam pytest. O pipeline de captura evaporou no
  refactor. Causa raiz: nao houve religacao do helper summarize/embed
  dentro dos novos stop.py.

- **B8.2**: O `opencode.json` raiz nao tinha campo `plugin`, e o CLI
  `opencode plugin add` gravou `.opencode/opencode.json` com path
  invalido (`{"plugin": ["list"]}`). Resultado: o plugin TS nunca foi
  carregado em runtime. Causa raiz: instalacao via CLI nao documentada
  como caminho canonico; melhor abordagem eh adicionar `"plugin"` ao
  `opencode.json` raiz manualmente.

## Decisoes de arquitetura e o porque

- **DECISION**: Criar `.claude/hooks/_lib/learning.py` como helper
  canonico para `summarize + embed async` (DRY entre os 3 stop.py).
  Antes cada stop.py teria que duplicar a logica; agora todos chamam
  `learning.spawn_summarize_then_embed`.

- **DECISION**: Marker de idempotencia composto `(agent_slug,
  session_id)` em vez de apenas `agent_slug`. Sessoes diferentes do
  mesmo agent NAO devem ser colapsadas em uma unica entrada.

- **DECISION**: Gate de escopo `tool_writes_count > 0`. Sessoes apenas
  de leitura (consulta pura) NAO devem poluir o RAG. Plugin TS conta
  writes via `Map<sessionID, number>`.

- **DECISION**: Hook `stop.py` chama `learning.spawn_summarize_then_embed`
  apenas apos pytest passar (gate de qualidade) E payload conter
  `tool_writes_count > 0` (gate de escopo). Falha em qualquer um =
  skip silencioso + log.

## Padroes adotados pelo time

- **TEAM_PATTERN**: Helper compartilhado em `_lib/` quando logica
  identica aparece em 3+ arquivos. Foi o caso de
  `resolve_transcript`, `payload_has_edits`, `marker_path`,
  `should_record`. Centralizou e removeu 60 linhas de duplicacao.

- **TEAM_PATTERN**: Fire-and-forget via `subprocess.Popen detached` em
  Windows (DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP). Embed do modelo
  ONNX pode levar minutos na primeira execucao; NAO pode bloquear o
  encerramento do agent.

- **TEAM_PATTERN**: Defesa em profundidade em testes de guard:
  `uninstall_http_guard() ; install_http_guard()` em vez de apenas
  `install_http_guard()`. O flag `_guards_installed` pode ficar True
  enquanto mocker ja' restaurou `requests.get` para o original, criando
  inconsistencia entre flag e estado real.

## O que nao funcionou e por que

- **DIDNT_WORK**: Tentar carregar o plugin TS via `opencode plugin add
  .opencode/plugin/agent-hooks.ts`. O CLI gravou apenas `{"plugin":
  ["list"]}` no `.opencode/opencode.json` (subproduto), path invalido.
  Solucao: adicionar `"plugin"` manualmente em `opencode.json` raiz.

- **DIDNT_WORK**: Testar `install_http_guard()` como idempotente puro
  via flag `_guards_installed`. O flag assume que a instalacao anterior
  deixou `requests.get = safe_get`. Se outro teste usar `mocker.patch`
  para reverter `requests.get`, o flag fica mentiroso. Solucao: sempre
  fazer `uninstall + install` em testes sensiveis.
