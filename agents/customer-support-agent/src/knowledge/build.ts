import type { BuildIndexOptions, KnowledgeIndex, KnowledgeChunk } from '../types.js';
import { chunkDocs } from './chunk.js';
import { validateIndex } from './validate.js';
import { SupportAgentError, toSafeError } from '../errors.js';
import { embed } from '../client.js';

export const DEFAULT_EMBEDDING_MODEL = 'text-embedding-3-small';
export const DEFAULT_EMBEDDING_DIMENSIONS = 768;
export const DEFAULT_EMBED_BATCH = 64;

export async function buildKnowledgeIndex(opts: BuildIndexOptions): Promise<KnowledgeIndex> {
  const embeddingModel = opts.embeddingModel || DEFAULT_EMBEDDING_MODEL;
  const dimensions = opts.dimensions || DEFAULT_EMBEDDING_DIMENSIONS;
  const batchSize = opts.batchSize || DEFAULT_EMBED_BATCH;
  const maskPii = opts.maskPii;
  const skipBlocked = opts.skipBlocked ?? false;

  if (opts.docs.length === 0) {
    const emptyIndex: KnowledgeIndex = {
      version: 1,
      embeddingModel,
      dimensions,
      createdAt: new Date().toISOString(),
      chunks: []
    };
    validateIndex(emptyIndex);
    return emptyIndex;
  }

  const baseChunks = chunkDocs(opts.docs);
  let chunks: KnowledgeChunk[] = [];
  const skippedDocUrls = new Set<string>();

  for (let i = 0; i < baseChunks.length; i += batchSize) {
    if (opts.signal?.aborted) {
      throw new SupportAgentError('aborted', 'build aborted');
    }

    const rawBatch = baseChunks.slice(i, i + batchSize);
    const batch = skipBlocked ? rawBatch.filter(c => !skippedDocUrls.has(c.url)) : rawBatch;
    if (batch.length === 0) {
      continue;
    }

    const input = batch.map(c => c.content);

    let vectors: number[][];
    try {
      vectors = await embed(opts.client, embeddingModel, input, dimensions, opts.signal, { maskPii });
      for (let j = 0; j < batch.length; j++) {
        const b = batch[j]!;
        chunks.push({
          id: b.id,
          title: b.title,
          url: b.url,
          content: b.content,
          audiences: b.audiences,
          embedding: vectors[j]!
        });
      }
    } catch (error: any) {
      if (error?.name === 'AbortError' || opts.signal?.aborted) {
        throw new SupportAgentError('aborted', 'build aborted');
      }
      const safe = toSafeError(error);
      if (safe.code !== 'guardrail_blocked') {
        throw error;
      }

      // Re-embed that batch ONE chunk at a time to find the refused chunks
      const refusedInBatch = new Map<string, { title: string; url: string; reason: string }>();
      const successfulInBatch: Array<{ chunk: (typeof batch)[0]; vector: number[] }> = [];

      for (const c of batch) {
        if (opts.signal?.aborted) {
          throw new SupportAgentError('aborted', 'build aborted');
        }
        try {
          const singleVec = await embed(opts.client, embeddingModel, [c.content], dimensions, opts.signal, { maskPii });
          successfulInBatch.push({ chunk: c, vector: singleVec[0]! });
        } catch (chunkErr: any) {
          if (chunkErr?.name === 'AbortError' || opts.signal?.aborted) {
            throw new SupportAgentError('aborted', 'build aborted');
          }
          const chunkSafe = toSafeError(chunkErr);
          if (chunkSafe.code === 'guardrail_blocked') {
            if (!refusedInBatch.has(c.url)) {
              refusedInBatch.set(c.url, { title: c.title, url: c.url, reason: chunkSafe.message });
            }
          } else {
            // Other errors propagate unchanged
            throw chunkErr;
          }
        }
      }

      if (refusedInBatch.size === 0) {
        throw error;
      }

      if (!skipBlocked) {
        const uniqueUrls = Array.from(refusedInBatch.keys());
        const listed = uniqueUrls.slice(0, 10).join(', ');
        throw new SupportAgentError(
          'guardrail_blocked',
          `the gateway refused ${uniqueUrls.length} document(s) under a guardrail: ${listed}`
        );
      }

      // skipBlocked is true: drop every chunk of a refused doc, call onSkip once per doc
      for (const [url, info] of refusedInBatch) {
        if (!skippedDocUrls.has(url)) {
          skippedDocUrls.add(url);
          opts.onSkip?.(info);
        }
      }

      // Drop every chunk of a refused doc from previously accumulated chunks
      chunks = chunks.filter(c => !skippedDocUrls.has(c.url));

      // Add successful chunks from this batch whose doc was NOT refused
      for (const item of successfulInBatch) {
        if (!skippedDocUrls.has(item.chunk.url)) {
          chunks.push({
            id: item.chunk.id,
            title: item.chunk.title,
            url: item.chunk.url,
            content: item.chunk.content,
            audiences: item.chunk.audiences,
            embedding: item.vector
          });
        }
      }
    }
  }

  const index: KnowledgeIndex = {
    version: 1,
    embeddingModel,
    dimensions,
    createdAt: new Date().toISOString(),
    chunks,
  };

  validateIndex(index);
  return index;
}
