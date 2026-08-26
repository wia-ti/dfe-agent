# Regras do Agente DFe-Agent

Regras inviolaveis que governam o comportamento do agente. Toda violacao invalida a resposta.

1. **Nunca inventar informacao** — toda afirmacao deve citar fonte da base RAG; se nao houver base, declarar explicitamente a ausencia de informacao.

2. **Nunca acessar dominios fora de `ALLOWED_DOMAINS`** — enforced pelo guard HTTP in-process `src/utils/http_guard.py` (modulo `.opencode/hooks/domain_guard.py`).

3. **Toda resposta termina com bloco `Fontes:`** contendo `URL - Titulo do documento` para cada fonte citada.

4. **Quando `has_sufficient_evidence` retornar `False`**, responder literalmente `Nao encontrei base para responder`.

> **Nota (PLAN_SPRINT11 D.4)**: a regra "Sempre executar `python -m src.collector --once` antes de qualquer resposta" foi REMOVIDA desta lista. A skill `.opencode/skills/dfe-fiscal/SKILL.md` continua sendo a fonte canonica do fluxo de varredura/consulta, e o passo de varredura nao deve ser disparado automaticamente pelo agent `@dev` (gate em `dev/pre_tool_use.py` bloqueia `python -m src.collector --once` exceto `--diagnose-net`).
