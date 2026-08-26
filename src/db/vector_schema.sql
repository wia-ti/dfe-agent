-- Schema vetorial para o DFe-Agent.
--
-- A tabela `vec_chunks` usa a extensao sqlite-vec (vec0) para busca por
-- similaridade de cosseno. Como a dimensao do embedding depende do modelo
-- carregado em runtime, o DDL e gerado dinamicamente em Python a partir
-- de `dim` (substituir `N` por um inteiro). O codigo que monta e executa
-- este CREATE vive em `src/db/vector_store.py::VectorStore.init_schema`.
--
-- NUNCA incluir `chunk_idx` como coluna explicita: o sqlite-vec expoe o
-- `rowid` automaticamente e o usamos como chave primaria.
--
-- Estrutura esperada:
--   embedding    -- BLOB float32 little-endian (dim * 4 bytes)
--   document_id  -- FK para documents.id (Task 2.1)
--   chunk_index  -- posicao do chunk dentro do documento (0..N)
--   text         -- trecho bruto do chunk (sem normalizacao)
--   source_url   -- URL original do documento (citada nas respostas)
--   doc_title    -- titulo legivel do documento (citado nas respostas)

CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(
    embedding float[N],
    document_id INTEGER,
    chunk_index INTEGER,
    text TEXT,
    source_url TEXT,
    doc_title TEXT
);
