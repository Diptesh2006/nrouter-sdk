import { describe, it, expect } from 'vitest';
import { buildSuggestions } from '../src/suggestions.js';
import type { ScoredChunk } from '../src/types.js';

function chunk(title: string, i = 0): ScoredChunk {
  return { id: `c${i}`, title, url: `https://example.com/${i}`, content: 'body', similarity: 0.9 - i * 0.01 };
}

describe('buildSuggestions', () => {
  it('builds questions from retrieved titles, skipping the top hit', () => {
    const out = buildSuggestions([chunk('Routing', 0), chunk('Pricing', 1), chunk('API keys', 2)], 3);
    expect(out).toEqual(['Tell me about Pricing', 'Tell me about API keys']);
  });

  it('skips every chunk that shares the top hit title, case-insensitively', () => {
    const out = buildSuggestions([chunk('Routing', 0), chunk('ROUTING', 1), chunk('Pricing', 2)], 3);
    expect(out).toEqual(['Tell me about Pricing']);
  });

  it('de-duplicates case-insensitively', () => {
    const out = buildSuggestions([chunk('Top', 0), chunk('Pricing', 1), chunk('pricing', 2), chunk('Keys', 3)], 5);
    expect(out).toEqual(['Tell me about Pricing', 'Tell me about Keys']);
  });

  it('keeps a title that already ends with a question mark as-is', () => {
    const out = buildSuggestions([chunk('Top', 0), chunk('How does billing work?', 1)], 3);
    expect(out).toEqual(['How does billing work?']);
  });

  it('honours max', () => {
    const chunks = [chunk('Top', 0), chunk('A', 1), chunk('B', 2), chunk('C', 3), chunk('D', 4)];
    expect(buildSuggestions(chunks, 2)).toEqual(['Tell me about A', 'Tell me about B']);
  });

  it('strips control characters and markdown/HTML metacharacters from untrusted titles', () => {
    const out = buildSuggestions([
      chunk('Top', 0),
      chunk('<script>alert(1)</script>', 1),
      chunk('[click](https://evil.example)', 2),
      chunk('Line\none\u0000 `code`\ttab', 3),
    ], 5);
    expect(out).toEqual([
      'Tell me about scriptalert1/script',
      'Tell me about clickhttps://evil.example',
      'Tell me about Line one code tab',
    ]);
    for (const q of out) {
      expect(q).not.toMatch(/[<>\[\]()`\u0000-\u001f\u007f-\u009f]/);
    }
  });

  it('drops titles that are empty after sanitising', () => {
    const out = buildSuggestions([chunk('Top', 0), chunk('<>[]()``', 1), chunk('   ', 2), chunk('Keys', 3)], 5);
    expect(out).toEqual(['Tell me about Keys']);
  });

  it('caps each question at 80 characters', () => {
    const out = buildSuggestions([chunk('Top', 0), chunk('word '.repeat(40), 1)], 3);
    expect(out).toHaveLength(1);
    expect(out[0]!.length).toBeLessThanOrEqual(80);
    expect(out[0]!.startsWith('Tell me about word')).toBe(true);
    expect(out[0]).toBe(out[0]!.trim());
  });

  it('ignores non-string titles', () => {
    const bad = { ...chunk('x', 1), title: 42 as unknown as string };
    expect(buildSuggestions([chunk('Top', 0), bad, chunk('Keys', 2)], 3)).toEqual(['Tell me about Keys']);
  });

  it('returns [] when there is nothing beyond the top hit', () => {
    expect(buildSuggestions([], 3)).toEqual([]);
    expect(buildSuggestions([chunk('Only', 0)], 3)).toEqual([]);
  });
});
