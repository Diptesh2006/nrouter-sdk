import type { KnowledgeIndex } from '../types.js';
import { SupportAgentError } from '../errors.js';

/** Validate an untrusted value as a KnowledgeIndex. Throws SupportAgentError('invalid_index') with a named reason. */
export function validateIndex(value: unknown): KnowledgeIndex {
  if (!value || typeof value !== 'object') {
    throw new SupportAgentError('invalid_index', 'index must be an object');
  }

  const record = value as Record<string, unknown>;

  if (record.version !== 1) {
    throw new SupportAgentError('invalid_index', 'version must be 1');
  }
  if (typeof record.embeddingModel !== 'string' || record.embeddingModel.trim() === '') {
    throw new SupportAgentError('invalid_index', 'embeddingModel must be a non-empty string');
  }
  if (typeof record.dimensions !== 'number' || !Number.isInteger(record.dimensions) || record.dimensions < 1 || record.dimensions > 8192) {
    throw new SupportAgentError('invalid_index', 'dimensions must be an integer between 1 and 8192');
  }
  
  if (typeof record.createdAt !== 'string' || Number.isNaN(Date.parse(record.createdAt))) {
    throw new SupportAgentError('invalid_index', 'createdAt must be a parseable date string');
  }

  if (!Array.isArray(record.chunks)) {
    throw new SupportAgentError('invalid_index', 'chunks must be an array');
  }

  const dimensions = record.dimensions as number;
  const chunks = record.chunks as unknown[];
  const seenIds = new Set<string>();

  for (let i = 0; i < chunks.length; i++) {
    const chunk = chunks[i];
    if (!chunk || typeof chunk !== 'object') {
      throw new SupportAgentError('invalid_index', `chunks[${i}] must be an object`);
    }
    const c = chunk as Record<string, unknown>;

    if (typeof c.id !== 'string') {
      throw new SupportAgentError('invalid_index', `chunks[${i}].id must be a string`);
    }
    if (seenIds.has(c.id)) {
      throw new SupportAgentError('invalid_index', `chunks[${i}].id '${c.id}' is a duplicate`);
    }
    seenIds.add(c.id);

    if (typeof c.title !== 'string') {
      throw new SupportAgentError('invalid_index', `chunks[${i}].title must be a string`);
    }
    if (typeof c.url !== 'string') {
      throw new SupportAgentError('invalid_index', `chunks[${i}].url must be a string`);
    }
    if (typeof c.content !== 'string' || c.content.trim() === '') {
      throw new SupportAgentError('invalid_index', `chunks[${i}].content must be a non-empty string`);
    }

    if (c.audiences !== undefined) {
      if (!Array.isArray(c.audiences)) {
        throw new SupportAgentError('invalid_index', `chunks[${i}].audiences must be an array of strings`);
      }
      for (let j = 0; j < c.audiences.length; j++) {
        if (typeof c.audiences[j] !== 'string') {
          throw new SupportAgentError('invalid_index', `chunks[${i}].audiences[${j}] must be a string`);
        }
      }
    }

    if (!Array.isArray(c.embedding)) {
      throw new SupportAgentError('invalid_index', `chunks[${i}].embedding must be an array`);
    }
    if (c.embedding.length !== dimensions) {
      throw new SupportAgentError('invalid_index', `chunks[${i}].embedding length ${c.embedding.length} != dimensions ${dimensions}`);
    }
    for (let j = 0; j < c.embedding.length; j++) {
      if (typeof c.embedding[j] !== 'number' || !Number.isFinite(c.embedding[j])) {
        throw new SupportAgentError('invalid_index', `chunks[${i}].embedding[${j}] must be a finite number`);
      }
    }
  }

  return record as unknown as KnowledgeIndex;
}
