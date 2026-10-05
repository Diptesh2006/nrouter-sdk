/** Normalise untrusted page context: string only, control chars stripped except newline/tab, collapsed, capped; else null. */
export function sanitizePageContext(raw: unknown, maxChars: number): string | null {
  if (typeof raw !== 'string') return null;
  
  // Strip control chars except newline and tab
  let s = raw.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, '');
  
  // Collapse every whitespace run, newlines and tabs included, into a single space
  s = s.replace(/\s+/g, ' ').trim();
  
  if (!s) return null;
  
  s = s.slice(0, maxChars);
  
  // trim again in case slicing cut at a space
  s = s.trim();
  return s || null;
}
