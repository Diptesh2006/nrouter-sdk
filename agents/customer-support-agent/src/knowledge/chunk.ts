// Pure TypeScript: no node: imports (core must run on edge runtimes).
import type { KnowledgeChunk, SourceDoc } from '../types.js';

export interface ChunkOptions {
  /** Max characters per chunk (default 1200). */
  maxChars?: number;
  /** Characters of overlap between consecutive chunks (default 150). */
  overlap?: number;
}

/** Deterministic chunking: same input, same output, always. */
export function chunkText(text: string, opts?: ChunkOptions): string[] {
  const maxChars = opts?.maxChars ?? 1200;
  const overlap = opts?.overlap ?? 150;

  const clean = text
    .replace(/\r/g, '')
    // eslint-disable-next-line no-control-regex
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .replace(/[ \t]{2,}/g, ' ')
    .trim();

  if (!clean) return [];
  if (clean.length <= maxChars) return [clean];

  const isWs = (c: string | undefined): boolean => c === ' ' || c === '\n' || c === '\t';
  const lastWsBefore = (from: number, floor: number): number => {
    for (let k = from; k > floor; k--) if (isWs(clean[k])) return k;
    return -1;
  };
  const firstWsFrom = (from: number, ceil: number): number => {
    for (let k = from; k < ceil; k++) if (isWs(clean[k])) return k;
    return -1;
  };

  const out: string[] = [];
  let i = 0;
  while (i < clean.length) {
    let end = Math.min(i + maxChars, clean.length);
    if (end < clean.length) {
      const br = lastWsBefore(end, i + Math.floor(maxChars / 2));
      if (br > i) end = br;
    }
    const piece = clean.slice(i, end).trim();
    if (piece) out.push(piece);
    if (end >= clean.length) break;

    let next = Math.max(i + 1, end - overlap);
    const fwd = firstWsFrom(next, end);
    if (fwd !== -1) next = fwd + 1;
    i = next;
  }
  return out;
}

/** Chunk documents; ids are stable (hash of url + position), identical across rebuilds. */
export function chunkDocs(docs: SourceDoc[], opts?: ChunkOptions): Array<Omit<KnowledgeChunk, 'embedding'>> {
  const result: Array<Omit<KnowledgeChunk, 'embedding'>> = [];
  for (const doc of docs) {
    if (!doc.content.trim()) continue; // skip docs with empty content
    const chunks = chunkText(doc.content, opts);
    for (let pos = 0; pos < chunks.length; pos++) {
      const content = chunks[pos] as string;
      const id = stableHash(`${doc.url}#${pos}`);
      const chunkDoc: Omit<KnowledgeChunk, 'embedding'> = {
        id,
        title: doc.title,
        url: doc.url,
        content,
      };
      if (doc.audiences && doc.audiences.length > 0) {
        chunkDoc.audiences = doc.audiences;
      }
      result.push(chunkDoc);
    }
  }
  return result;
}

/** Deterministic 64-bit FNV-1a hex hash (pure TS). */
export function stableHash(input: string): string {
  let hash = 14695981039346656037n;
  const prime = 1099511628211n;

  for (let i = 0; i < input.length; i++) {
    hash ^= BigInt(input.charCodeAt(i));
    hash = BigInt.asUintN(64, hash * prime);
  }

  return hash.toString(16).padStart(16, '0');
}
