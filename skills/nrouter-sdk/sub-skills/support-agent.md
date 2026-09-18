# Sub-skill: Customer Support Agent (@nrouter_ai/support-agent)

Skill `nrouter-sdk`, sub-skill `support-agent`. Open it when developing, configuring, or testing the public `@nrouter_ai/support-agent` package located at `agents/customer-support-agent/`.

The customer support agent is a streaming, in-process assistant library built directly on `@nrouter_ai/sdk`. It provides document-grounded retrieval over static markdown docs or index files, cosine similarity search, tools, confidence scoring, citation generation, PII masking, and SSE streaming.

## Core Properties

1. **Zero Database Dependency**: All retrieval happens in-memory over pre-computed chunk embeddings (typically loaded from a static `kb.json` index), eliminating database, vector extension, and microservice dependencies.
2. **SDK Dogfooding**: The only runtime dependency is `@nrouter_ai/sdk` (`nRouter` universal client).
3. **SSE Streaming Contract**: `chatSSE(req, context)` returns an asynchronous `ReadableStream` of Server-Sent Event lines, each carrying an `nrouter_event` discriminator (`confidence`, `citations`, `token`, `cost`, `done` — derive from `src/sse.ts`). A `cost` frame carries `status: 'exact'` with a `costUsd`, or `status: 'unpriced'` with **no** amount — never a `0`, which would report a free request (Rule #28).
4. **Offline by Default**: Like the rest of `nrouter-sdk`, all default unit and contract tests run completely offline with zero network, zero gateway, and zero credentials.

## Package Structure

Derive it rather than trusting a tree that goes stale: `ls agents/customer-support-agent/src
agents/customer-support-agent/src/knowledge agents/customer-support-agent/test`. The entry points
that matter: `src/agent.ts` (the `createSupportAgent` factory), `src/client.ts` (the SDK wrapper),
`src/retrieval.ts` (cosine ranking), `src/pii.ts` (masking), `src/sse.ts` (the SSE formatter),
`src/node.ts` (file-system helpers: `readDocsDir`, `saveKnowledgeIndex`, `loadKnowledgeIndex`),
`src/knowledge/` (the index build pipeline: fetch, chunk, build, validate, store) and
`bin/support-agent.mjs` (the `build-kb` CLI). Every `src/*.ts` has a matching `test/*.test.ts`.

## CLI Usage: Building Knowledge Base Index

**The key is read from `NROUTER_API_KEY` in the environment; there is no `--api-key` flag**, so a key
never lands in shell history or the process table. `--base-url` is optional and defaults to the
SDK's own base URL. Derive the flag list rather than trusting this block — the CLI prints it:

```bash
export NROUTER_API_KEY="sk-nrouter-..."
npx @nrouter_ai/support-agent help
npx @nrouter_ai/support-agent build-kb --docs <docs-directory> --out kb.json \
  --model text-embedding-3-small --dimensions 768
```

## Host Application Integration

Any Node.js/Next.js/Express server imports `@nrouter_ai/support-agent` in-process:

```typescript
import { createSupportAgent } from '@nrouter_ai/support-agent';
import { loadKnowledgeIndex } from '@nrouter_ai/support-agent/node';

const knowledge = await loadKnowledgeIndex('./data/support-agent-kb.json');
const agent = createSupportAgent({
  apiKey: process.env.NROUTER_API_KEY,   // a virtual key; baseURL defaults to the public gateway
  model: 'claude-haiku-4-5-20251001',
  knowledge,
  maskPii: true,
});

const sseStream = agent.chatSSE(
  { messages: [{ role: 'user', content: 'How do I create a virtual key?' }] },
  { audiences: ['public'] }
);
```

## Test Commands

Run from `agents/customer-support-agent/`:

```bash
npm test           # vitest run — the offline suite; derive the count, do not pin it
npm run typecheck  # tsc --noEmit
npm run build      # compiles to dist/
npm run e2e        # builds, then playwright — needs a key and a browser; never a default path
```

This package uses **npm** (`package-lock.json`), not pnpm. Derive the scripts rather than trusting
this block: `python3 -c "import json;print(json.load(open('agents/customer-support-agent/package.json'))['scripts'])"`.

## Host integration is the host's concern

This package is a library: it takes a key, a model and a knowledge index, and returns a stream. It
knows nothing about any particular host, and this sub-skill deliberately documents no host's
routes, deployments or verification scripts — those live with the host, not in the public SDK repo.
