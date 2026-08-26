CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    source_domain TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    title TEXT NOT NULL,
    file_path TEXT,
    content_hash TEXT,
    published_at TEXT,
    fetched_at TEXT NOT NULL,
    ingested_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('nao_ingerido','ingerido','falhou'))
);

CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash);
