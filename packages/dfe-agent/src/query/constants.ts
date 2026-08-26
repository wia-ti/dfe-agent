/**
 * constants.ts — constantes canonicas do query engine.
 *
 * Separado de index.ts para evitar ciclos de import com contextBuilder.
 *
 * NO_EVIDENCE_MESSAGE: string canonica que sinaliza ausencia de chunks.
 *   - Gate dfe-rules.md #4 + convencoes-gerais.md
 *   - NUNCA duplique este literal
 *   - Espelha `src/query/context_builder.py` no Py
 *
 * SUPPORTED_MODES: union type dos modos de busca opt-in.
 */

export const NO_EVIDENCE_MESSAGE = "Nao encontrei base para responder";

export const SUPPORTED_MODES = ["semantic", "fts", "hybrid"] as const;
export type SearchMode = (typeof SUPPORTED_MODES)[number];

// Defaults alinhados com src/query/constants.py (gate paridade Py ↔Node)
export const DEFAULT_TOP_K = 5;
export const MIN_RELEVANCE_SCORE = 0.5;
export const RECENCY_WEIGHT = 0.3;
export const RECENCY_HALF_LIFE_DAYS = 180.0;