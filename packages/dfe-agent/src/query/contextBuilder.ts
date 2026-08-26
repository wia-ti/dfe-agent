/**
 * contextBuilder.ts — monta o contexto final (answer + sources).
 *
 * @see PLAN_SPRINT14.md Task E.5
 *
 * Constante NO_EVIDENCE_MESSAGE canonica em `src/query/index.ts` (mesma
 * string em src/query/context_builder.py do Py). NUNCA duplique o literal
 * em outro arquivo — gate dfe-rules.md #4 + convencoes-gerais.md.
 */

import { NO_EVIDENCE_MESSAGE, MIN_RELEVANCE_SCORE } from "./constants.js";
import type { Source } from "./index.js";

export interface HydratedChunk {
  chunk_id: number;
  doc_id: number;
  text: string;
  url: string;
  title: string;
  score: number;
  published_at?: string | null;
}

export interface ContextResult {
  answer: string;
  sources: Source[];
}

/**
 * Heuristica de evidencia suficiente (gate dfe-rules.md #4 + paridade Py).
 *
 * Convencao Py (`src/query/context_builder.py:60-71`): olhamos apenas o
 * PRIMEIRO chunk (mais relevante no ranking). Se ele nao atinge o minimo,
 * qualquer outro posterior tera score menor.
 *
 * Antes da Sprint 14.1, Node usava `Math.max(...)` que retornava True em
 * cenarios com 1 chunk bom + N chunks ruins, divergindo do Py. Corrigido
 * para paridade.
 */
export function hasSufficientEvidence(chunks: HydratedChunk[]): boolean {
  if (chunks.length === 0) return false;
  return chunks[0].score >= MIN_RELEVANCE_SCORE;
}

/**
 * Constroi o contexto final: dedup por URL, ordena por score, monta answer.
 */
export function buildContext(chunks: HydratedChunk[]): ContextResult {
  if (!hasSufficientEvidence(chunks)) {
    return {
      answer: NO_EVIDENCE_MESSAGE,
      sources: [],
    };
  }

  // Dedup por URL (preferir chunk com maior score)
  const byUrl = new Map<string, HydratedChunk>();
  for (const c of chunks) {
    const existing = byUrl.get(c.url);
    if (!existing || c.score > existing.score) {
      byUrl.set(c.url, c);
    }
  }

  const sorted = Array.from(byUrl.values()).sort((a, b) => b.score - a.score);

  const sources: Source[] = sorted.map((c) => ({
    url: c.url,
    title: c.title,
    score: c.score,
  }));

  const answer = sorted.map((c) => c.text).join("\n\n---\n\n");

  return { answer, sources };
}