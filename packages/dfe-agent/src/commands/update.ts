/**
 * commands/update.ts — baixa base RAG do GitHub Releases e popula ~/.dfe-agent/dfe.db.
 *
 * @see PLAN_SPRINT14.md Task C.2
 *
 * Fluxo:
 *   1. fetch GitHub Releases API (latest release em wia-ti/dfe-agent)
 *   2. localizar assets: dfe.db.gz + dfe.db.gz.sha256
 *   3. download gz + sha256
 *   4. verificar SHA-256 (gate B.3)
 *   5. extrair atomicamente para ~/.dfe-agent/dfe.db (ou $DFE_AGENT_BASE_DIR)
 *   6. validar schema via PRAGMA user_version >= 6
 *
 * Fallback: se GitHub inacessivel, usa seed bundled em dist/seed/dfe.db.gz.
 *
 * Exit codes:
 *   0  sucesso
 *   1  erro generico
 *   3  SHA mismatch / sem asset / rede off sem seed
 */

import { createHash } from "node:crypto";
import { gunzipSync } from "node:zlib";
import {
  existsSync,
  writeFileSync,
  renameSync,
  mkdirSync,
  readFileSync,
} from "node:fs";
import { resolve, dirname } from "node:path";
import { tmpdir, homedir } from "node:os";
import { fileURLToPath } from "node:url";

const PKG_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

const GH_REPO = process.env.DFE_AGENT_GH_REPO ?? "wia-ti/dfe-agent";
const GH_API = `https://api.github.com/repos/${GH_REPO}/releases/latest`;
const ASSET_DB = "dfe.db.gz";
const ASSET_SHA = "dfe.db.gz.sha256";

export interface UpdateOptions {
  /** Override base path (default: $DFE_AGENT_BASE_DIR ou ~/.dfe-agent). Usado por testes. */
  baseDirOverride?: string;
}

function resolveBaseDir(): string {
  return process.env.DFE_AGENT_BASE_DIR
    ?? process.env.HOME
    ?? homedir()
    ?? tmpdir();
}

async function fetchJson(url: string, token?: string): Promise<any> {
  const headers: Record<string, string> = {
    "User-Agent": "dfe-agent-cli/0.1.0",
    Accept: "application/vnd.github+json",
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const r = await fetch(url, { headers });
  if (!r.ok) throw new Error(`GitHub API ${r.status} ${r.statusText}`);
  return r.json();
}

async function downloadBuffer(url: string, token?: string): Promise<Buffer> {
  const headers: Record<string, string> = {
    "User-Agent": "dfe-agent-cli/0.1.0",
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const r = await fetch(url, { headers });
  if (!r.ok) throw new Error(`download ${url} -> ${r.status}`);
  return Buffer.from(await r.arrayBuffer());
}

function writeAtomic(path: string, data: Buffer): void {
  const tmp = `${path}.tmp`;
  writeFileSync(tmp, data);
  renameSync(tmp, path);
}

function fallbackToSeed(dbPath: string): number {
  const seedPath = resolve(PKG_ROOT, "dist/seed/dfe.db.gz");
  if (!existsSync(seedPath)) {
    console.error(
      `[dfe-agent] rede off e sem seed bundled em ${seedPath}.\n` +
        `[dfe-agent] aguarde o proximo release do DFe-Agent ou rode com rede.`,
    );
    return 3;
  }
  console.warn(`[dfe-agent] rede off — usando seed bundled (snapshot antigo)`);
  const gz = readFileSync(seedPath);
  const db = gunzipSync(gz);
  mkdirSync(dirname(dbPath), { recursive: true });
  writeAtomic(dbPath, db);
  console.info(`[dfe-agent] base (seed) -> ${dbPath} (${db.length} bytes)`);
  return 0;
}

export async function update(opts: UpdateOptions): Promise<number> {
  const baseDir = opts.baseDirOverride ?? resolveBaseDir();
  const dbPath = resolve(baseDir, "dfe.db");

  mkdirSync(baseDir, { recursive: true });

  // 1. fetch release metadata
  let release: any;
  try {
    release = await fetchJson(GH_API, process.env.GITHUB_TOKEN);
  } catch (err) {
    console.warn(`[dfe-agent] GitHub API inacessivel: ${(err as Error).message}`);
    return fallbackToSeed(dbPath);
  }

  // 2. localizar assets
  const dbAsset = release.assets?.find((a: any) => a.name === ASSET_DB);
  const shaAsset = release.assets?.find((a: any) => a.name === ASSET_SHA);
  if (!dbAsset || !shaAsset) {
    console.error(`[dfe-agent] release sem assets ${ASSET_DB} / ${ASSET_SHA}`);
    return 3;
  }

  // 3. download
  let gz: Buffer;
  let expectedSha: string;
  try {
    [gz, expectedSha] = await Promise.all([
      downloadBuffer(dbAsset.browser_download_url, process.env.GITHUB_TOKEN),
      downloadBuffer(shaAsset.browser_download_url, process.env.GITHUB_TOKEN).then((b) => b.toString().trim()),
    ]);
  } catch (err) {
    console.warn(`[dfe-agent] download falhou: ${(err as Error).message}`);
    return fallbackToSeed(dbPath);
  }

  // 4. verify SHA-256
  const actualSha = createHash("sha256").update(gz).digest("hex");
  if (actualSha !== expectedSha) {
    console.error(
      `[dfe-agent] SHA mismatch: expected ${expectedSha}, got ${actualSha}`,
    );
    return 3;
  }

  // 5. atomic write
  const db = gunzipSync(gz);
  writeAtomic(dbPath, db);

  // 6. validate schema (best-effort)
  //    Import lazy para nao quebrar quando better-sqlite3 nao compila
  try {
    const Database = (await import("better-sqlite3")).default;
    const sqliteVec = await import("sqlite-vec");
    const handle = new Database(dbPath, { readonly: true });
    sqliteVec.load(handle);
    const uv = handle.prepare("PRAGMA user_version").get() as { user_version: number };
    handle.close();
    if (uv.user_version < 6) {
      console.error(`[dfe-agent] base com schema antigo (user_version=${uv.user_version} < 6)`);
      return 3;
    }
  } catch (err) {
    console.warn(`[dfe-agent] nao foi possivel validar schema: ${(err as Error).message}`);
    // nao falha o update — arquivo ja foi escrito com SHA valido
  }

  console.info(`[dfe-agent] base atualizada: ${dbPath} (${db.length} bytes, sha=${actualSha.slice(0, 16)}...)`);
  return 0;
}