# Aprendizados -- feature code-reviewer hardening -- 2026-08-26

> Origem: /feature "garanta que o agente @code-reviewer esta funcionando em todos os cenarios necessarios"
> Plano: PLAN_SPRINT9.md
> Relatorio final do code-reviewer: **0 BLOQUEANTE** + **0 IMPORTANTE** + **2 SUGESTAO** (ambas resolvidas na Fase 5; redundancia residual aceita por invariantes ortogonais; duplicacao entre `.opencode/agents/` e `.claude/agents/` registrada como follow-up de Sprint 10+).
> Iteracoes do loop corretivo: 2 (1a: 3 IMPORTANTE + 4 SUGESTAO; 2a: 0 + 2 SUGESTAO resolvidas).

## Bugs resolvidos com causa raiz

- **Typo "blqueia" em `.opencode/agents/code-reviewer.md:194`** (SUGESTAO Fase 5 #2). Sem impacto de teste (nenhum regex capturava), mas reduzia a qualidade do documento canonico que o proprio reviewer le. Fix: substituicao literal. Licao: nenhum linter automatizado no CI captura typos em markdown; considerar adicionar uma verificacao textual no `test_code_reviewer_definition.py` (SUGESTAO Sprint 10+).

- **Duplicacao textual entre `.opencode/agents/code-reviewer.md:3` e `.claude/agents/code-reviewer.md:3`** (SUGESTAO Fase 5 #4). As duas definicoes ja' divergiam no `description`. Fix: sincronizou para a versao completa ("Reviewer read-only do DFe-Agent focado em aderencia ao SPEC.md e PLAN.md..."). Licao: qualquer agente que exista em 2 paths (.opencode/.claude) deve ser sincronizado periodicamente ou consolidado.

- **Teste tautologico `test_detect_agent_with_env_var_code_reviewer`** (IMPORTANTE Fase 4 #1). Docstring dizia "Replica em subprocesso Python a logica do plugin TS" mas o eval_script so' fazia `os.environ.get()` — duplicava `test_agent_dispatch.py:32-56` sem adicionar cobertura real. Fix: removido. Licao: testes com docstring prometendo mais do que o codigo exercita sao red flag em code review (regra "resposta cita fonte" do `.claude/rules/convencoes-gerais.md`).

- **Redundancia entre `test_code_reviewer_profile_has_no_post_tool_use` e `test_plugin_emits_no_stop_event_handler_for_code_reviewer_profile`** (IMPORTANTE Fase 4 #3). Dois testes cobriam a mesma invariante. Fix: o segundo foi refatorado para focar em word-boundary (`\bpostToolUse\b`) — invariante ortogonal a substring — e renomeado para `test_code_reviewer_profile_post_tool_use_word_boundary`. Licao: dois testes sobre a mesma string podem coexistir se o metodo de captura for ortogonal (substring vs regex word-boundary vs anchor).

- **Cobertura nula de `pre_tool_use_bash.py`** (gap pre-existente). So' existia demonstracao manual (`.claude/scripts/demo_agent_hooks.py`). Fix: 58 testes parametrizados cobrindo 9 BLOCK + 11 ALLOW + 5 edge cases. Licao: smoke scripts manuais nao substituem pytest; converter para testes automatizados e' sempre ganho liquido.

## Decisoes de arquitetura e o porque

- **Estrategia "testes de smoke manual NAO contam como cobertura"**: o `demo_agent_hooks.py` existia mas nao era pytest. Decidimos que cada BLOCK/ALLOW pattern merece um teste pytest parametrizado. Custo: 58 testes em 1 arquivo. Beneficio: regressoes detectaveis em CI; o demo manual continua existindo para consulta humana rapida.

- **Plugin dispatch via regex no source TS em vez de runtime mock**: os testes de Fase C (plugin dispatch) usam inspecao do source do `agent-hooks.ts` via regex em vez de carregar o modulo via `tsx` e mockar `runPython`. Decisao: regex e' estavel, deterministic, e roda em <1s; mock TS e' fragil e adiciona dependencia de runtime. Licao: quando o codigo TS e' simples (if/return), inspecao textual e' mais robusta que execucao.

- **Estrategia "Fase D acoplada em Fase C"**: os 2 testes da Fase D.1 (`feature.md` referencia `subagent_type: code-reviewer`) foram adicionados em `test_code_reviewer_plugin_dispatch.py` em vez de novo arquivo `test_feature_phase4_invokes_code_reviewer.py`. Decisao: evitar proliferacao; os testes sao "plugin-related sanity" e nao justificam arquivo separado. Custo: nome do arquivo nao cobre Fase D. Beneficio: 1 arquivo a menos para manter.

- **Type hints em funcoes de teste**: mantidos em 100% (precedente `.claude/rules/tests.md`). Convenção `def test_foo() -> None:` em todos os 96 testes novos, alem de fixtures e helpers tipados.

## Padroes adotados pelo time

- **Convencao de teste para agentes**: espelhar o teste do dfe-agent (`test_dfe_agent_definition.py`) para cada novo agent. Aplicado nesta sprint para code-reviewer (13 testes em `test_code_reviewer_definition.py`). Proposta para Sprint 10+: aplicar mesmo template a `ml-engineer`, `qa-engineer`, etc.

- **Convencao "subprocess.run([sys.executable, ...])" para hooks Python**: substitui `import` direto quando o hook tem side-effects (log em arquivo) ou auto-recursao (caso do guard HTTP Sprint 6). Padrao ja' usado em `test_agent_dispatch.py` e `test_domain_guard_plugin.py`; aplicado nesta sprint nos 4 testes dos hooks code-reviewer.

- **Convencao de parametrize para BLOCK/ALLOW patterns**: sempre que o codigo tem lista de regex, o teste deve ter `@pytest.mark.parametrize` equivalente. Aplicado em `pre_tool_use.py` (4 write-tools), `pre_tool_use_bash.py` (24 BLOCK + 26 ALLOW). Licao: parametrize reduz boilerplate e torna cada pattern visivel como teste independente no relatorio pytest.

## O que nao funcionou e por que

- **Falha ao invocar subagent code-reviewer via Task tool** na Fase 4: retorno "Model not found: MiniMax-M3/.". O subagent code-reviewer retornou erro de provider/model porque o frontmatter tem formato `model: MiniMax-M3` (sem prefixo de provider) enquanto o dfe-agent usa `model: PROVIDER/MiniMax-M3`. Workaround aplicado: invocar subagent `general` com prompt explicito pedindo template de code-reviewer. Licao: registrar formalmente como gap — Sprint 10+ deve resolver o formato canonico de `model:` no frontmatter de todos os agents.

- **Coverage tool conflito branch vs statement** durante a suite completa: 100+ arquivos `.coverage.NTANDREWS.pid*` orfaos na raiz confundiram o combine. Workaround: `--cov-branch` explicito + limpeza manual dos arquivos antes de cada run. Licao: documentar em `scripts/check_env.ps1` a rotina de limpeza pre-suite. Sugestao Sprint 10+: automatizar cleanup via `pyproject.toml` `tool.coverage.run.cleanup = true` ou gitignore dos `.coverage.*`.

- **Teste vermelho impossivel para "config-only" sprint**: a regra TDD de `.opencode/command/feature.md:139-145` foi citada mas nao exercitada nesta sprint porque todos os 4 arquivos de teste novos verificam **comportamento existente** (a config do code-reviewer). O unico "teste vermelho" plausivel seria o `test_body_references_hooks` (Task A.1) — que falhou de fato porque o `.opencode/agents/code-reviewer.md` original NAO referenciava os 2 hooks Python; corrigido adicionando a secao "Bloqueio de escrita (hooks Python complementares)". Licao: testes de definicao estrutural SAO TDD genuíno (verificam invariantes que podem regredir silenciosamente).

## Arquivos modificados

- `PLAN_SPRINT9.md` (novo, 240 linhas) — plano completo da sprint com 4 fases A-D.
- `.opencode/agents/code-reviewer.md` (modificado: adicionado secao "Bloqueio de escrita (hooks Python complementares)" + corrigido typo "blqueia" → "bloqueia").
- `.claude/agents/code-reviewer.md` (modificado: description sincronizada com `.opencode/agents/code-reviewer.md`).
- `tests/unit/test_code_reviewer_definition.py` (novo, 173 linhas, 13 testes) — validacao estrutural do frontmatter (name, mode, permission, yaml, body).
- `tests/unit/hooks/test_code_reviewer_pre_tool_use.py` (novo, 162 linhas, 15 testes) — bloqueia 4 write-tools + permite 6 read-tools + verifica log + UX de mensagem.
- `tests/unit/hooks/test_code_reviewer_pre_tool_use_bash.py` (novo, 197 linhas, 58 testes parametrizados) — bloqueia 24 comandos destrutivos + permite 26 read-only + 5 edge cases.
- `tests/integration/test_code_reviewer_plugin_dispatch.py` (novo, 207 linhas, 10 testes) — roteamento via plugin TS + sanity do `/feature` Fase 4.