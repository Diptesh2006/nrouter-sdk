import type { ConfidenceLevel, ConfidenceThresholds, ScoredChunk } from './types.js';

/** Clamp + round a raw similarity to a clean 0..1, 3-dp number. */
function norm(s: unknown): number {
  const n = typeof s === 'number' && Number.isFinite(s) ? s : 0;
  return Math.round(Math.max(0, Math.min(1, n)) * 1000) / 1000;
}

export function scoreConfidence(chunks: ScoredChunk[], thresholds: ConfidenceThresholds): { level: ConfidenceLevel; score: number } {
  if (!chunks.length) return { level: 'low', score: 0 };
  const sims = chunks.map((c) => norm(c.similarity));
  const score = Math.max(...sims);
  const level: ConfidenceLevel = score >= thresholds.high ? 'high' : score >= thresholds.medium ? 'medium' : 'low';
  return { level, score };
}
