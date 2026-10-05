// Node-only entry: "@nrouter_ai/support-agent/node".
import { promises as fs } from 'node:fs';
import path from 'node:path';
import type { KnowledgeIndex, SourceDoc } from './types.js';
import { validateIndex } from './knowledge/validate.js';

export async function loadKnowledgeIndex(filepath: string): Promise<KnowledgeIndex> {
  const data = await fs.readFile(filepath, 'utf-8');
  return validateIndex(JSON.parse(data));
}

export async function saveKnowledgeIndex(filepath: string, index: KnowledgeIndex): Promise<void> {
  const tmp = filepath + '.' + Math.random().toString(36).slice(2) + '.tmp';
  await fs.writeFile(tmp, JSON.stringify(index), 'utf-8');
  await fs.rename(tmp, filepath);
}

/** Read .md/.mdx/.txt files recursively; frontmatter `title` and `audiences` are honoured. */
export async function readDocsDir(dir: string, baseUrl?: string): Promise<SourceDoc[]> {
  const docs: SourceDoc[] = [];
  
  async function walk(currentDir: string) {
    const entries = await fs.readdir(currentDir, { withFileTypes: true });
    for (const entry of entries) {
      const full = path.join(currentDir, entry.name);
      if (entry.isDirectory()) {
        await walk(full);
      } else if (entry.isFile() && /\.(md|mdx|txt)$/.test(entry.name)) {
        const rel = path.relative(dir, full);
        const content = await fs.readFile(full, 'utf-8');
        
        let text = content;
        let title = '';
        let audiences: string[] | undefined;
        
        if (text.startsWith('---\n') || text.startsWith('---\r\n')) {
          const end = text.indexOf('\n---', 3);
          if (end !== -1) {
            const fm = text.slice(3, end);
            text = text.slice(end + 4).trimStart();
            
            const titleMatch = fm.match(/^title:\s*(.*)$/m);
            if (titleMatch) {
              title = titleMatch[1]!.replace(/^['"](.*)['"]$/, '$1').trim();
            }
            
            const audMatch = fm.match(/^audiences:\s*\[(.*?)\]/m);
            if (audMatch) {
              audiences = audMatch[1]!.split(',').map(s => s.replace(/^['"\s]+|['"\s]+$/g, '')).filter(Boolean);
            }
          }
        }
        
        const relNoExt = rel.replace(/\.[^.]+$/, '');
        const relUnix = relNoExt.split(path.sep).join('/');
        
        const url = baseUrl ? (baseUrl.endsWith('/') ? baseUrl + relUnix : baseUrl + '/' + relUnix) : 'file://' + relUnix;
        
        docs.push({
          title: title || entry.name,
          url,
          content: text,
          ...(audiences && audiences.length > 0 ? { audiences } : {})
        });
      }
    }
  }
  
  await walk(dir);
  docs.sort((a, b) => a.url.localeCompare(b.url));
  return docs;
}
