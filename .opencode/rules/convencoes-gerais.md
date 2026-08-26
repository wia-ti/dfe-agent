---
name: convencoes-gerais
description: Padroes transversais a qualquer agent e arquivo do workspace (nomenclatura, frontmatter obrigatorio, tipagem, NO_EVIDENCE_MESSAGE canonico, migration framework, cobertura minima, politica de comentarios).
---

# Convenções gerais — DFe-Agent

Padrões transversais a qualquer agent e a qualquer arquivo do workspace.

- **Nomenclatura**: `snake_case.py` para módulos Python (`rag_indexer.py`,
  `pdf_parser.py`); `kebab-case.md` para configs do opencode (regras em
  `.opencode/rules/<kebab>.md`); skills dedicadas em
  `.opencode/skills/<kebab>/SKILL.md`. Variáveis/funções em `snake_case`,
  classes em `PascalCase`, constantes em `UPPER_SNAKE_CASE`.
- **Frontmatter obrigatório**: agent/skill/rule/hook precisam de YAML válido
  com `name` + `description` (agent/rule/skill) ou `name` + `type` (hook).
  Frontmatter faltando ou com YAML quebrado é defeito IMPORTANTE na revisão.
- **Tipagem em `src/`**: type hints em toda função pública
  (`def f(x: int) -> str:`). Proibido `Any` implícito; se necessário,
  declare explícito com justificativa. Modelos de domínio usam
  `@dataclass` ou `pydantic.BaseModel` — nunca dict aninhado.
- **Mensagem canônica sem evidência**: a string `"Nao encontrei base para
  responder"` vive em `src/query/context_builder.py` como `NO_EVIDENCE_MESSAGE`.
  Nunca duplique literal no prompt do agente ou em mensagens de erro de CLI.
- **Resposta cita fonte**: toda saída da CLI `python -m src.query` é JSON
  `{answer, sources[]}`. Toda resposta do agente termina com bloco `Fontes:`
  listando `URL - Titulo`.
- **Migration framework**: cada `_apply_vN(conn)` em `src/db/migrations.py` é
  idempotente, controlado por `PRAGMA user_version` e aplicado via
  `apply_pending(db_path)`. Nunca criar tabela fora desse fluxo.
- **Cobertura mínima**: `--cov-fail-under=80` global em `src/`; 100% em
  `src/parser/`; >=95% em `src/indexer/`. CI falha abaixo desses limiares.
- **Comentários**: só em trechos não-óbvios. Sem comentários redundantes que
  apenas reescrevam o código em português.
