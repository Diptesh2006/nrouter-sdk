// Follow-up suggestions: related retrieved topics, built deterministically. No model call.
import type { ScoredChunk } from './types.js';

const MAX_QUESTION_CHARS = 80;

/** Titles are untrusted text: drop control/format characters and markdown/HTML metacharacters. */
function cleanTitle(title: unknown): string {
  if (typeof title !== 'string') return '';
  return title
    .replace(/[\p{Cc}\p{Cf}]/gu, ' ')
    .replace(/[<>[\]()`]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Up to `max` follow-up questions from the titles of retrieved chunks, in
 * retrieval order. The top hit is what the answer was about, so its title is
 * skipped; the rest are de-duplicated case-insensitively.
 */
export function buildSuggestions(chunks: ScoredChunk[], max: number): string[] {
  const questions: string[] = [];
  if (!Array.isArray(chunks) || chunks.length === 0) return questions;

  const seen = new Set<string>([cleanTitle(chunks[0]?.title).toLowerCase()]);
  for (const chunk of chunks.slice(1)) {
    if (questions.length >= max) break;
    const title = cleanTitle(chunk?.title);
    const key = title.toLowerCase();
    if (!title || seen.has(key)) continue;
    seen.add(key);
    const question = (title.endsWith('?') ? title : `Tell me about ${title}`).slice(0, MAX_QUESTION_CHARS).trim();
    if (question) questions.push(question);
  }
  return questions;
}
