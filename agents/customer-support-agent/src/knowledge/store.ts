import type { KnowledgeIndex, KnowledgeStore, SearchOptions, ScoredChunk } from '../types.js';
import { SupportAgentError } from '../errors.js';
import { validateIndex } from './validate.js';

export function cosineSimilarity(a: number[], b: number[]): number {
  if (a.length !== b.length) {
    throw new SupportAgentError('invalid_index', 'Embedding dimensions mismatch');
  }
  let dot = 0;
  let normA = 0;
  let normB = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i]! * b[i]!;
    normA += a[i]! * a[i]!;
    normB += b[i]! * b[i]!;
  }
  if (normA === 0 || normB === 0) {
    return 0;
  }
  return dot / (Math.sqrt(normA) * Math.sqrt(normB));
}

/** In-memory store over a validated index. Search is cosine, audience-filtered, deterministic on ties. */
export function createMemoryKnowledgeStore(index: KnowledgeIndex): KnowledgeStore {
  validateIndex(index);

  // Precompute norms once
  const precomputed = index.chunks.map(chunk => {
    let norm = 0;
    for (let i = 0; i < chunk.embedding.length; i++) {
      norm += chunk.embedding[i]! * chunk.embedding[i]!;
    }
    return { chunk, norm: Math.sqrt(norm) };
  });

  return {
    embeddingModel: index.embeddingModel,
    dimensions: index.dimensions,
    async search(queryEmbedding: number[], opts: SearchOptions): Promise<ScoredChunk[]> {
      if (queryEmbedding.length !== index.dimensions) {
        throw new SupportAgentError('invalid_request', 'Query length must equal index dimensions');
      }
      if (!Number.isInteger(opts.topK) || opts.topK < 1 || opts.topK > 50) {
        throw new SupportAgentError('invalid_request', 'topK must be an integer between 1 and 50');
      }

      let qNormSq = 0;
      for (let i = 0; i < queryEmbedding.length; i++) {
        qNormSq += queryEmbedding[i]! * queryEmbedding[i]!;
      }
      const qNorm = Math.sqrt(qNormSq);

      const scored: ScoredChunk[] = [];
      const hasAudiencesOpt = opts.audiences !== undefined;

      for (let i = 0; i < precomputed.length; i++) {
        const { chunk, norm } = precomputed[i]!;

        let eligible = false;
        if (!chunk.audiences || chunk.audiences.length === 0) {
          eligible = true;
        } else if (hasAudiencesOpt && opts.audiences!.length > 0) {
          for (let j = 0; j < chunk.audiences.length; j++) {
            if (opts.audiences!.includes(chunk.audiences[j]!)) {
              eligible = true;
              break;
            }
          }
        }
        
        if (!eligible) {
          continue;
        }

        let dot = 0;
        for (let j = 0; j < chunk.embedding.length; j++) {
          dot += chunk.embedding[j]! * queryEmbedding[j]!;
        }

        const similarity = (norm === 0 || qNorm === 0) ? 0 : dot / (norm * qNorm);
        scored.push({
          id: chunk.id,
          title: chunk.title,
          url: chunk.url,
          content: chunk.content,
          audiences: chunk.audiences,
          similarity
        });
      }

      scored.sort((a, b) => {
        if (a.similarity !== b.similarity) {
          return b.similarity - a.similarity;
        }
        return a.id < b.id ? -1 : (a.id > b.id ? 1 : 0);
      });

      return scored.slice(0, opts.topK);
    }
  };
}
