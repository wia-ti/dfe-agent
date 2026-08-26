/**
 * hybrid.ts — Reciprocal Rank Fusion (RRF) entre vector search e FTS5.
 *
 * @see PLAN_SPRINT14.md Task E.3
 *
 * Algoritmo RRF canonico (Cormack et al., 2009):
 *   rrf_score(d) = sum_modes (1 / (k0 + rank_m(d)))
 * Onde k0 = 60 e rank_m(d) e' o rank do doc `d` no modo `m` (1-indexed).
 *
 * Documentos que aparecem em ambos os modos (vector + fts) recebem score
 * somado, naturalmente subindo no ranking final.
 */

import type { VectorHit } from "./vectorSearch.js";
import type { FtsHit } from "./ftsSearch.js";

export interface HybridHit {
  chunk_id: number;
  doc_id: number;
  score: number;
  sources: Array<"vector" | "fts">;
}

const RRF_K0 = 60;

/**
 * Fonde resultados de vector + FTS via RRF.
 *
 * @param vectorHits Top-K do vector search (ordenado por distance)
 * @param ftsHits Top-K do FTS5 (ordenado por bm25)
 * @param k Tamanho final do ranking
 * @returns Array de hits ordenados por score decrescente
 */
export function rrf(
  vectorHits: VectorHit[],
  ftsHits: FtsHit[],
  k: number,
  k0: number = RRF_K0,
): HybridHit[] {
  const scoreMap = new Map<number, { chunk_id: number; doc_id: number; score: number; sources: Set<"vector" | "fts"> }>();

  vectorHits.forEach((hit, i) => {
    const existing = scoreMap.get(hit.chunk_id);
    const rankScore = 1 / (k0 + i + 1);
    if (existing) {
      existing.score += rankScore;
      existing.sources.add("vector");
    } else {
      scoreMap.set(hit.chunk_id, {
        chunk_id: hit.chunk_id,
        doc_id: hit.doc_id,
        score: rankScore,
        sources: new Set<"vector" | "fts">(["vector"]),
      });
    }
  });

  ftsHits.forEach((hit, i) => {
    const existing = scoreMap.get(hit.chunk_id);
    const rankScore = 1 / (k0 + i + 1);
    if (existing) {
      existing.score += rankScore;
      existing.sources.add("fts");
    } else {
      scoreMap.set(hit.chunk_id, {
        chunk_id: hit.chunk_id,
        doc_id: hit.doc_id,
        score: rankScore,
        sources: new Set<"vector" | "fts">(["fts"]),
      });
    }
  });

  return Array.from(scoreMap.values())
    .sort((a, b) => b.score - a.score)
    .slice(0, k)
    .map((entry) => ({
      chunk_id: entry.chunk_id,
      doc_id: entry.doc_id,
      score: entry.score,
      sources: Array.from(entry.sources),
    }));
}

export const RRF_K0_CANONICAL = RRF_K0;