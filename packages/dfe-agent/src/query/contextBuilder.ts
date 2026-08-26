/**
 * contextBuilder.ts — monta o contexto final (answer + sources).
 *
 * @see PLAN_SPRINT14.md Task E.5
 *
 * Constante NO_EVIDENCE_MESSAGE canonica em `src/query/index.ts` (mesma
 * string em src/query/context_builder.py do Py). NUNCA duplique o literal
 * em outro arquivo — gate dfe-rules.md #4 + convencoes-gerais.md.
 */

import { NO_EVIDENCE_MESSAGE, type Source } from "./index.js";

export interface HydratedChunk {
  chunk_id: number;
  doc_id: number;
  text: string;
  url: string;
  title: string;
  score: number;
}

export interface ContextResult {
  answer: string;
  sources: Source[];
}

export const MIN_RELEVANCE_SCORE = 0.3;
export const MIN_SOURCES = 1;

/**
 * Heuristica de evidencia suficiente:
 * - >=1 chunk hidratado E
 * - max score >= MIN_RELEVANCE_SCORE
 */
export function hasSufficientEvidence(chunks: HydratedChunk[]): boolean {
  if (chunks.length < MIN_SOURCES) return false;
  const maxScore = Math.max(...chunks.map((c) => c.score));
  return maxScore >= MIN_RELEVANCE_SCORE;
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