---
paths: tests/**/*.py
---

# Testes (`tests/**/*.py`) — DFe-Agent

- **Stack de teste**: `pytest` + `pytest-mock` + `pytest-cov`. Não introduzir
  `unittest.TestCase` em paralelo nem frameworks alternativos.
- **Estrutura espelha `src/`**: `tests/unit/<submod>/test_<arquivo>.py` para
  cada módulo; integração em `tests/integration/`, smoke E2E em
  `tests/test_smoke.py`.
- **Fixtures**: PDFs/HTML em `tests/fixtures/` (`sample_nt.pdf`,
  `fake_portal/<dominio>/...`); `eval_set.json` é a fonte para
  `python -m src.ragctl benchmark` (Fase 16) — não duplicar perguntas em código.
- **Sem rede em integração**: `tests/integration/` usa `fake_portal/` via
  `monkeypatch`. Nenhum teste em `tests/` faz request real aos portais.
- **DB isolada em teste**: testes não escrevem em `storage/dfe.db`. Usar
  `tmp_path` + fixture que monkeypatcha `DB_PATH`/`SQLITE_PATH`.
- **Cobertura é gate**: `--cov-fail-under=80` global; 100% em `src/parser/`;
  95% em `src/indexer/`. Falha abaixo = CI bloqueado.
- **Idempotência de migration**: cada `_apply_vN` tem teste rodando duas vezes
  sem erro e validando upgrade `v1→vN` sem perda
  (`tests/unit/db/test_*v2.py`).
- **Cache de query**: `test_embedding_cache.py` valida HIT na 2a chamada idêntica
  sem nova invocação do modelo.
- **Críticos do AGENTS.md**: cada item de "Testes críticos deste projeto" tem
  teste; sem isso `code-reviewer` classifica como IMPORTANTE.
- **Domínio no guard**: `test_domain_guard.py` valida a allow-list; adicionar
  domínio em `allowed_domains.py` exige atualizar o teste no mesmo commit.
