# DFe-Agent

Agente local que coleta documentacao fiscal eletronica oficial (NF-e, NFC-e, CT-e, MDF-e, SPED, CONFAZ), indexa em base RAG local (SQLite + `sqlite-vec`) e responde perguntas em linguagem natural fundamentadas em notas tecnicas.

> Stack: opencode + MiniMax-M3 + Python 3.11+ + SQLite (vetorial) — 100% local.

## Estrutura

- `.opencode/` — agente, skills, hooks e rules consumidos pelo opencode.
- `src/collector` `src/parser` `src/indexer` `src/query` `src/db` `src/utils` — pacotes Python do dominio fiscal.
- `data/` — PDFs/HTML brutos baixados (nao versionado).
- `storage/` — arquivos do SQLite relacional + vetorial (nao versionado).
- `tests/` — suíte pytest (unit + integration + fixtures).

Detalhes completos em [`AGENTS.md`](./AGENTS.md) e [`SPEC.md`](./SPEC.md). Plano de execucao em [`PLAN.md`](./PLAN.md).

## Setup local

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

## Verificacao de saude (scaffold)

```bash
python main.py --health     # verifica versao do Python + importabilidade dos modulos
pytest --collect-only -q    # descobre a suíte sem executar
pytest tests/               # roda a suíte completa
```

## Comandos do dominio (implementados nas proximas fases)

```bash
python -m src.collector --once          # varredura completa dos portais oficiais
python -m src.collector --once --dry-run # descobre URLs sem baixar
python -m src.indexer.ingest             # ingere documentos pendentes no RAG
python -m src.query "pergunta em linguagem natural"  # consulta a base
```

## Agente opencode

```bash
opencode run                              # sessao interativa
opencode run "sua pergunta aqui"          # pergunta direta
```
