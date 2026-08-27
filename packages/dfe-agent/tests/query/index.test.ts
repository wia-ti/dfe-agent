import { test } from "node:test";
import assert from "node:assert/strict";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

// === Behavioral test (gate code-reviewer I14 + Sprint 16 Bug C) ===
// SKIP em CI: better-sqlite3 cleanup hook crasha em Node 22 Linux.
// Sprint 15: tambem skip em Windows + Node >= 22 (mesmo sintoma pre-existente).

const _NODE_MAJOR = parseInt(process.versions.node.split(".")[0], 10);
const _IS_WIN_NODE_NATIVE_BUG = process.platform === "win32" && _NODE_MAJOR >= 22;
const _SKIP_NATIVE = process.env.CI === "true"
  || process.env.DFE_AGENT_SKIP_NATIVE_TESTS === "1"
  || _IS_WIN_NODE_NATIVE_BUG;

const PKG_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

test("index.ts expoe hydrateChunks para teste (gate Bug C Sprint 16)", async () => {
  // Sem isso, hydrateChunks fica privado em index.ts e nao da' pra testar.
  const src = await import("node:fs").then((fs) =>
    fs.readFileSync(resolve(PKG_ROOT, "src/query/index.ts"), "utf8"),
  );
  assert.match(
    src,
    /export\s+(async\s+)?function\s+hydrateChunks|export\s*\{\s*[^}]*hydrateChunks/,
    "hydrateChunks deve ser exportado de query/index.ts (gate teste Sprint 16)",
  );
});

test("hydrateChunks BEHAVIORAL: usa vec_chunks (nao chunks) + JOIN documents — schema Py real (Bug C)", async (t) => {
  if (_SKIP_NATIVE) {
    t.skip();
    return;
  }
  const Database = (await import("better-sqlite3")).default;
  const indexMod = await import("../../dist/query/index.js");
  const hydrateChunks = indexMod.hydrateChunks;
  assert.ok(
    typeof hydrateChunks === "function",
    "hydrateChunks deve ser exportado (Fase 3.3 do /bug)",
  );

  const handle = new Database(":memory:");
  // Schema Py real (vec0 + documents).
  handle.exec(`
    CREATE VIRTUAL TABLE vec_chunks USING vec0(
      embedding float[4],
      document_id INTEGER,
      chunk_index INTEGER,
      text TEXT,
      source_url TEXT,
      doc_title TEXT
    );
    CREATE TABLE documents (
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
      status TEXT NOT NULL,
      nt_number TEXT,
      version TEXT,
      replaces_doc_id INTEGER,
      language TEXT
    );
    INSERT INTO documents (id, url, source_domain, doc_type, title, fetched_at, status, published_at)
      VALUES (10, 'https://ex.com/1', 'ex.com', 'NT', 'NT 2024.001', '2024-01-01', 'ingerido', '2024-01-01');
    INSERT INTO vec_chunks (embedding, document_id, chunk_index, text, source_url, doc_title) VALUES
      (zeroblob(16), 10, 0, 'nota tecnica 2024', 'https://ex.com/1', 'NT 2024.001'),
      (zeroblob(16), 10, 1, 'segundo chunk',     'https://ex.com/1', 'NT 2024.001');
  `);

  const hydrated = hydrateChunks(handle as any, [
    { chunk_id: 0, doc_id: 10, score: 0.9 },
    { chunk_id: 1, doc_id: 10, score: 0.7 },
  ]);
  assert.equal(hydrated.length, 2, `esperado 2 chunks hidratados; obtido ${hydrated.length}`);
  assert.equal(hydrated[0].text, "nota tecnica 2024");
  assert.equal(hydrated[0].url, "https://ex.com/1");
  assert.equal(hydrated[0].title, "NT 2024.001");
  assert.equal(hydrated[0].published_at, "2024-01-01");

  handle.close();
});
