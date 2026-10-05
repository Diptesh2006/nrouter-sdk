// Pure TypeScript + global fetch; no node: imports.
import type { SourceDoc } from '../types.js';

export function isBlockedHost(host: string): boolean {
  if (typeof host !== 'string') return true;
  const h = host.toLowerCase().replace(/^\[|\]$/g, '');
  if (!h || h === 'localhost' || h.endsWith('.localhost') || h.endsWith('.local') || h.endsWith('.internal')) return true;

  // IPv6
  if (h.includes(':')) {
    if (h === '::1' || h === '::' || h.startsWith('fe80:') || h.startsWith('fc') || h.startsWith('fd') || h.startsWith('fe9') || h.startsWith('fea') || h.startsWith('feb') || h.startsWith('::ffff:')) {
      return true;
    }
  }

  // IPv4 dot-decimal
  const parts = h.split('.');
  if (parts.length === 4 && parts.every(p => /^\d+$/.test(p))) {
    const nums = parts.map(Number);
    const a = nums[0]!;
    const b = nums[1]!;
    if (a === 0 || a === 10 || a === 127) return true;
    if (a === 169 && b === 254) return true;
    if (a === 172 && b >= 16 && b <= 31) return true;
    if (a === 192 && b === 168) return true;
    if (a === 100 && b >= 64 && b <= 127) return true;
    if (a === 192 && b === 0 && nums[2] === 0) return true;
    if (a === 198 && (b === 18 || b === 19)) return true;
    if (a >= 224 && a <= 239) return true;
    if (a >= 240 && a <= 255) return true;
  }
  return false;
}

export function isSafeUrl(raw: string): boolean {
  let u: URL;
  try {
    u = new URL(raw);
  } catch {
    return false;
  }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') return false;
  if (u.username || u.password) return false;
  return !isBlockedHost(u.hostname);
}

const NAMED_ENTITIES: Record<string, string> = {
  amp: '&', lt: '<', gt: '>', quot: '"', apos: "'",
  nbsp: ' ', mdash: '—', ndash: '–', hellip: '…',
  rsquo: '’', lsquo: '‘', rdquo: '”', ldquo: '“',
  copy: '©', reg: '®', trade: '™', middot: '·',
};

function decodeEntities(s: string): string {
  return s.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (match, body: string) => {
    const b = body.toLowerCase();
    if (b.startsWith('#x')) {
      const n = parseInt(b.slice(2), 16);
      return (Number.isFinite(n) && n >= 0 && n <= 0x10ffff && !(n >= 0xd800 && n <= 0xdfff)) ? String.fromCodePoint(n) : match;
    }
    if (b.startsWith('#')) {
      const n = Number(b.slice(1));
      return (Number.isFinite(n) && n >= 0 && n <= 0x10ffff && !(n >= 0xd800 && n <= 0xdfff)) ? String.fromCodePoint(n) : match;
    }
    return NAMED_ENTITIES[b] ?? match;
  });
}

function stripTags(s: string, tags: string[]): string {
  const set = new Set(tags.map(t => t.toLowerCase()));
  const lower = s.toLowerCase();
  const noCloserAhead = new Set<string>();
  let out = '';
  let i = 0;
  while (i < s.length) {
    const lt = s.indexOf('<', i);
    if (lt === -1) { out += s.slice(i); break; }
    out += s.slice(i, lt);
    const gt = s.indexOf('>', lt);
    if (gt === -1) { out += s.slice(lt); break; }
    const name = /^<\s*([a-z0-9]+)/i.exec(s.slice(lt, gt + 1))?.[1]?.toLowerCase();
    if (name && set.has(name)) {
      if (s[gt - 1] === '/') { out += ' '; i = gt + 1; continue; }
      if (noCloserAhead.has(name)) { i = gt + 1; continue; }
      const close = lower.indexOf(`</${name}`, gt);
      if (close === -1) { noCloserAhead.add(name); i = gt + 1; continue; }
      const closeEnd = s.indexOf('>', close);
      out += ' ';
      i = closeEnd === -1 ? s.length : closeEnd + 1;
      continue;
    }
    out += s.slice(lt, gt + 1);
    i = gt + 1;
  }
  return out;
}

export function htmlToText(html: string): { title: string; text: string } {
  const m = html.match(/<title>([^<]*)<\/title>/i);
  const title = m ? decodeEntities(m[1]!.trim()) : '';

  const CHROME = ['script', 'style', 'noscript', 'nav', 'footer'];
  let s = stripTags(html, CHROME);

  const BLOCK_TAGS = 'address|article|aside|blockquote|div|dl|dt|dd|fieldset|figure|figcaption|footer|form|h[1-6]|header|hr|li|main|nav|ol|p|pre|section|table|tbody|td|tfoot|th|thead|tr|ul';
  s = s.replace(new RegExp(`</?(?:${BLOCK_TAGS})\\b[^>]*>`, 'gi'), '\n');
  s = s.replace(/<br\s*\/?>/gi, '\n');
  s = s.replace(/<[^>]+>/g, '');
  s = decodeEntities(s)
    .replace(/[ \t]+/g, ' ')
    .replace(/\s*\n\s*/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();

  return { title, text: s };
}

export interface FetchSeedOptions {
  maxBytes?: number;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}

export async function fetchSeedPages(urls: string[], opts?: FetchSeedOptions): Promise<SourceDoc[]> {
  const fetchImpl = opts?.fetchImpl ?? globalThis.fetch;
  const timeoutMs = opts?.timeoutMs ?? 10000;
  const maxBytes = opts?.maxBytes ?? 2_000_000;
  
  const docs: SourceDoc[] = [];

  for (const url of urls) {
    if (!isSafeUrl(url)) continue;
    
    const c = new AbortController();
    const id = setTimeout(() => c.abort(), timeoutMs);

    try {
      let currentUrl = url;
      let res: Response | null = null;
      let redirects = 0;
      let finalOk = false;

      while (redirects <= 3) {
        try {
          res = await fetchImpl(currentUrl, {
            redirect: 'manual',
            signal: c.signal
          });
        } catch {
          res = null;
          break;
        }

        if (res.status >= 300 && res.status < 400) {
          const loc = res.headers.get('location');
          if (!loc) {
            res = null; break;
          }
          const nextUrl = new URL(loc, currentUrl).href;
          if (!isSafeUrl(nextUrl)) {
            res = null; break;
          }
          currentUrl = nextUrl;
          redirects++;
          continue;
        } else if (res.ok) {
          finalOk = true;
          break;
        } else {
          res = null; break; // 4xx/5xx
        }
      }

      if (!finalOk || !res || !res.body) continue;

      const ctype = res.headers.get('content-type') || '';
      if (!ctype.includes('text/html') && !ctype.includes('text/plain')) {
        continue;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let out = '';
      let bytes = 0;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        bytes += value.byteLength;
        if (bytes > maxBytes) {
          await reader.cancel().catch(() => {});
          break;
        }
        out += decoder.decode(value, { stream: true });
      }
      out += decoder.decode();

      const { title, text } = htmlToText(out);
      if (text.trim().length > 0) {
        docs.push({ title: title || currentUrl, url: currentUrl, content: text });
      }
    } catch {
      // skip failures
    } finally {
      clearTimeout(id);
    }
  }

  return docs;
}
