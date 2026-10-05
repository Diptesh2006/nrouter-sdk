import type { ResolvedConfig, ScoredChunk } from './types.js';
import { embed } from './client.js';

/** Embed the question with the store's model/dimensions and search. Empty question → []. */
export async function retrieve(
  cfg: ResolvedConfig,
  question: string,
  opts?: { audiences?: string[]; signal?: AbortSignal },
): Promise<ScoredChunk[]> {
  const q = question.trim();
  if (!q) {
    return [];
  }
  const vecs = await embed(
    cfg.client,
    cfg.store.embeddingModel,
    [q],
    cfg.store.dimensions,
    opts?.signal
  );
  if (!vecs || vecs.length === 0 || !vecs[0]) return [];
  return cfg.store.search(vecs[0], { topK: cfg.topK, audiences: opts?.audiences });
}
