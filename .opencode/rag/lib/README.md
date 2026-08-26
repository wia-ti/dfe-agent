# `.opencode/rag/lib/`

Modulos TypeScript compartilhados pelo pipeline de RAG meta-cognitivo
(`.opencode/rag/`). Cada modulo encapsula uma responsabilidade
unica e e' importado pelos entry-points (`init_db.ts`, `summarize.ts`,
`embed.ts`, `search.ts`, `smoke_test.ts`) via `npx tsx`.

> **Sprint 12 (B12.4)**: diretorio movido para ``.opencode/rag/lib/``
> (unificacao do harness em ``.opencode/``; antes vivia em outro path).

## Modulos

### `db.ts`

Wrapper minimalista sobre `better-sqlite3` para o SQLite usado pelo
RAG meta (`rag.db`). Centraliza:

- O path canonico do banco (`.opencode/rag/rag.db`).
- O carregamento sincrono da extensao `sqlite-vec` (vec0).
- Helpers de `exec` / `query` que retornam linhas como `unknown[]`
  para que o caller projete o tipo.

Usado por: `init_db.ts`, `embed.ts`, `search.ts`, `smoke_test.ts`.

### `chunker.ts`

Chunker sentence-aware para o transcript consolidado da sessao
(`.md` gerado por `summarize.ts`). Limites:

- 200-300 tokens por chunk (default 256).
- Overlap de 50 tokens entre chunks consecutivos (preserva contexto
  cross-boundary).
- Fronteiras de sentenca quando possivel (regex `(?<=[.!?])\s+`).

Nao usa LLM — puramente deterministico. Performance: ~1000 chunks/s
em hardware de referencia.

Usado por: `embed.ts`.

### `embedder.ts`

Wrapper sobre `@xenova/transformers` (ONNX em Node) que carrega o
modelo `all-MiniLM-L6-v2` (384 dim, ~25 MB ONNX). Suporta:

- `embed(text: string): Promise<Float32Array>` — embedding unitario.
- `embedBatch(texts: string[]): Promise<Float32Array[]>` — batch com
  `tokenizer.encode_batch` (5x speedup vs. loop).
- LRU cache local para evitar re-encoding de queries repetidas.

Carregamento lazy: o modelo e' instanciado na primeira chamada de
`embed`, nao no import do modulo. Permite que `classifier.ts` (sem
necessidade de embedding) importe o modulo sem custo de RAM.

Usado por: `embed.ts`, `search.ts`.

### `classifier.ts`

Heuristica de categorizacao do conhecimento extraido da sessao.
Categorias validas (4):

- `bug_root_cause` — quando o transcript contem marcadores como
  `"DIDNT_WORK"`, `"falhou porque"`, `"stack trace"`, etc.
- `architecture_decision` — quando ha termos `"decidi"`,
  `"escolhi"`, `"arquitetura"`, `"porque"`.
- `team_pattern` — quando ha `"convencao"`, `"padrao"`, `"sempre
  fazemos"`.
- `what_didnt_work` — fallback explicito quando so' ha `"nao
  funcionou"`, `"bug"`, `"erro"`.

Por que heuristica (e nao LLM)? Os hooks `Stop` disparam em
background; chamar LLM para classificar adicionaria latencia +
custo. Heuristicas cobrem ~80% dos casos; o `.md` resultante pode ser
revisado manualmente.

Usado por: `summarize.ts`.

## Convencoes

- Cada modulo expoe apenas o necessario (sem barrel `index.ts` —
  imports vao direto no modulo especifico).
- Tipos de dominio em `@/types/knowledge.ts` (nao neste diretorio).
- Estilo: TypeScript estrito (`"strict": true` no `tsconfig.json`),
  sem `any` implícito.

## Adicionar novo modulo

1. Criar `lib/<nome>.ts` com responsabilidade unica.
2. Adicionar secao acima com descricao e quem usa.
3. Cobrir com smoke test em `.opencode/rag/smoke_test.ts`.
4. Nao importar de `src/` (sao universos separados — Python vs
   TypeScript; comunicacao so' via `.opencode/rag/rag.db`).
