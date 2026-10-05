import type { ChatTurn } from './types.js';

const MAX_Q = 500;

export function normalizeQuestion(q: string): string {
  return q
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, MAX_Q);
}

/** The last user turn's content, trimmed; '' when there is none. */
export function latestQuestion(messages: ChatTurn[]): string {
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i];
    if (msg && msg.role === 'user') {
      return msg.content ? msg.content.trim() : '';
    }
  }
  return '';
}
