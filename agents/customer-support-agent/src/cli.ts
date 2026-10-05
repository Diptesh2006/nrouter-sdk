import { nRouter } from '@nrouter_ai/sdk';
import { buildKnowledgeIndex } from './knowledge/build.js';
import { fetchSeedPages } from './knowledge/fetch.js';
import { readDocsDir, saveKnowledgeIndex } from './node.js';

import { redact } from './errors.js';

export interface CliDeps {
  client?: nRouter;
}

export async function runCliWith(argv: string[], env: Record<string, string | undefined>, deps: CliDeps): Promise<number> {
  if (argv.length === 0 || argv[0] === 'help') {
    console.log(`Usage: support-agent build-kb --docs <dir> [--seed-url <u>]... --out <file> [--model m] [--dimensions n] [--base-url u] [--base-docs-url u] [--skip-blocked] [--no-mask-pii]`);
    return argv[0] === 'help' ? 0 : 2;
  }

  if (argv[0] !== 'build-kb') {
    console.error('Unknown command');
    return 2;
  }

  let docsDir = '';
  let outPath = '';
  const seedUrls: string[] = [];
  let model: string | undefined;
  let dimensions: number | undefined;
  let baseUrl: string | undefined;
  let baseDocsUrl: string | undefined;
  let skipBlocked = false;
  let maskPii = true;

  for (let i = 1; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--docs') docsDir = argv[++i] ?? '';
    else if (arg === '--out') outPath = argv[++i] ?? '';
    else if (arg === '--seed-url') seedUrls.push(argv[++i] ?? '');
    else if (arg === '--model') model = argv[++i];
    else if (arg === '--dimensions') dimensions = parseInt(argv[++i] ?? '', 10);
    else if (arg === '--base-url') baseUrl = argv[++i];
    else if (arg === '--base-docs-url') baseDocsUrl = argv[++i];
    else if (arg === '--skip-blocked') skipBlocked = true;
    else if (arg === '--no-mask-pii') maskPii = false;
    else {
      console.error(`Unknown option: ${arg}`);
      return 2;
    }
  }

  if (!docsDir) {
    console.error('Missing --docs');
    return 2;
  }
  if (!outPath) {
    console.error('Missing --out');
    return 2;
  }

  const apiKey = env['NROUTER_API_KEY'];
  if (!deps.client && !apiKey) {
    console.error('Missing NROUTER_API_KEY in environment');
    return 1;
  }

  try {
    const client = deps.client || new nRouter({ apiKey, baseURL: baseUrl });

    let docs = await readDocsDir(docsDir, baseDocsUrl);
    if (seedUrls.length > 0) {
      const seedDocs = await fetchSeedPages(seedUrls);
      docs = docs.concat(seedDocs);
    }

    const index = await buildKnowledgeIndex({
      client,
      docs,
      embeddingModel: model,
      dimensions,
      maskPii,
      skipBlocked,
      onSkip(doc) {
        console.log(redact(`skipped: ${doc.url} (${doc.reason})`));
      }
    });

    await saveKnowledgeIndex(outPath, index);

    console.log(`Built index:
Docs: ${docs.length}
Chunks: ${index.chunks.length}
Model: ${index.embeddingModel}
Dims: ${index.dimensions}
Out: ${outPath}`);

    return 0;
  } catch (err: any) {
    console.error(`Error: ${redact(err.message)}`);
    return 1;
  }
}

/** Entry for `support-agent <command>`. Returns the process exit code. */
export async function runCli(argv: string[], env: Record<string, string | undefined>): Promise<number> {
  return runCliWith(argv, env, {});
}
