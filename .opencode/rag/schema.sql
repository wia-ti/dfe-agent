-- .opencode/rag/schema.sql
-- Schema do sistema de RAG meta-cognitivo do DFe-Agent.
-- Armazena aprendizados extraidos de sessoes/agents para injecao em prompts futuros.
--
-- Tabelas:
--   knowledge        -- tabela relacional (source of truth dos metadados e do texto)
--   vec_knowledge    -- tabela virtual vec0 (embeddings com busca por cosseno)
--   knowledge_meta   -- sidecar com informacoes de bookkeeping (PRAGMA user_version)
--
-- Design:
--   * knowledge e vec_knowledge se relacionam via knowledge_id (sem FK declarada
--     para que vec0 nao precise de reescrita quando a tabela relacional mudar).
--   * categoria segue o CHECK constraint abaixo; valores invalidos sao rejeitados.
--   * created_at em ISO-8601 UTC (ex: "2026-08-25T14:30:00.000Z").
--
-- Idempotente: tudo usa IF NOT EXISTS, entao pode ser aplicado multiplas vezes.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS knowledge (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    path        TEXT    NOT NULL,
    content     TEXT    NOT NULL,
    category    TEXT    NOT NULL
                    CHECK(category IN (
                        'bug_root_cause',
                        'architecture_decision',
                        'team_pattern',
                        'what_didnt_work'
                    )),
    agent       TEXT    NOT NULL,
    created_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_knowledge_category ON knowledge(category);
CREATE INDEX IF NOT EXISTS idx_knowledge_agent    ON knowledge(agent);
CREATE INDEX IF NOT EXISTS idx_knowledge_created  ON knowledge(created_at);

-- Tabela vetorial (sqlite-vec vec0). dimensao 384 = all-MiniLM-L6-v2.
-- distance_metric=cosine normalizado para que score = 1 - distance esteja em [0,1].
--
-- knowledge_id NAO eh PRIMARY KEY porque uma knowledge pode ter varios chunks
-- (1 row por chunk). A relacao com `knowledge` eh por knowledge_id (sem FK).
-- O rowid proprio do sqlite eh usado internamente.
CREATE VIRTUAL TABLE IF NOT EXISTS vec_knowledge USING vec0(
    embedding float[384] distance_metric=cosine,
    knowledge_id INTEGER
);