#!/usr/bin/env node
'use strict';

const assert = require('node:assert/strict');
const { nRouter, NRouterModels, NRouterSurface, nRouterConfigurationError } = require('../dist/index.js');

const MODEL = process.env.NROUTER_DEMO_MODEL || 'claude-haiku-4-5-20251001';

function loadRootEnv() {
  const fs = require('node:fs');
  const path = require('node:path');
  const envPath = path.resolve(__dirname, '..', '..', '..', '.env');
  if (!fs.existsSync(envPath)) return;
  for (const rawLine of fs.readFileSync(envPath, 'utf8').split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;
    const eq = line.indexOf('=');
    if (eq <= 0) continue;
    const key = line.slice(0, eq).trim();
    const value = line.slice(eq + 1).trim().replace(/^['"]|['"]$/g, '');
    if (!(key in process.env)) process.env[key] = value;
  }
}

function fakeFetch() {
  const calls = [];
  async function bodyText(body) {
    if (!body) return '';
    if (typeof body === 'string') return body;
    if (body instanceof Uint8Array) return new TextDecoder().decode(body);
    if (body instanceof ArrayBuffer) return new TextDecoder().decode(new Uint8Array(body));
    if (typeof body.text === 'function') return body.text();
    if (Symbol.asyncIterator in Object(body)) {
      const chunks = [];
      for await (const chunk of body) {
        chunks.push(typeof chunk === 'string' ? new TextEncoder().encode(chunk) : chunk);
      }
      const size = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
      const merged = new Uint8Array(size);
      let offset = 0;
      for (const chunk of chunks) {
        merged.set(chunk, offset);
        offset += chunk.length;
      }
      return new TextDecoder().decode(merged);
    }
    return String(body);
  }
  async function fetch(url, init = {}) {
    let body = {};
    try {
      const rawBody = await bodyText(init.body);
      body = rawBody ? JSON.parse(rawBody) : {};
      calls.push({ url: String(url), body });
    } catch (error) {
      throw new Error(`demo transport could not decode request body for ${String(url)}: ${error.message}`);
    }

    const pathname = new URL(String(url)).pathname;

    if (pathname.endsWith('/models')) {
      return Response.json({ object: 'list', data: [{ id: MODEL, owned_by: 'nrouter' }] });
    }

    if (pathname.endsWith('/messages')) {
      return Response.json(
        {
          id: 'msg_demo',
          type: 'message',
          role: 'assistant',
          model: body.model,
          content: [{ type: 'text', text: 'Demo agent OK' }],
          stop_reason: 'end_turn',
          usage: { input_tokens: 8, output_tokens: 4 },
        },
        {
          headers: {
            'x-nr-request-id': 'req_demo',
            'x-nr-model': body.model,
            'x-nr-request-cost': '0.000001',
            'x-nr-cost-status': 'exact',
          },
        },
      );
    }

    return Response.json({ error: { type: 'not_found', message: 'unexpected path' } }, { status: 404 });
  }
  return { fetch, calls };
}

function fakeRequester() {
  const transport = fakeFetch();
  const requester = {
    get(path) {
      return {
        asResponse: async () => transport.fetch(`https://api.nrouter.ai/v1${path}`, { method: 'GET' }),
      };
    },
    post(path, options = {}) {
      return {
        asResponse: async () =>
          transport.fetch(`https://api.nrouter.ai/v1${path}`, {
            method: 'POST',
            headers: options.headers,
            body: options.body,
            signal: options.signal,
          }),
      };
    },
  };
  return {
    calls: transport.calls,
    client: {
      nrouterModels: new NRouterModels(requester),
      nr: new NRouterSurface(requester),
    },
  };
}

async function runAgent(client, mode) {
  const models = await client.nrouterModels.list();
  assert.ok(Array.isArray(models.data), 'model list should return data array');
  assert.ok(models.data.some((model) => model.id === MODEL), `model list should include ${MODEL}`);

  const result =
    mode === 'live'
      ? await client.nr.chat({
          model: MODEL,
          systemPrompt: 'You are a concise SDK demo agent.',
          prompt: 'Reply with exactly: Demo agent OK',
          maxTokens: 16,
          cache: false,
        })
      : await client.nr.messages({
          model: MODEL,
          max_tokens: 16,
          system: 'You are a concise SDK demo agent.',
          messages: [{ role: 'user', content: 'Reply with exactly: Demo agent OK' }],
        });

  const text =
    client.nr.text(result).trim() ||
    (Array.isArray(result.body.content)
      ? result.body.content
          .map((part) => (part && typeof part.text === 'string' ? part.text : ''))
          .join('')
          .trim()
      : '');
  assert.ok(text.length > 0, 'chat response should contain text');
  assert.ok(result.meta.requestId, 'response should include request metadata');
  assert.ok(result.meta.cost === null || result.meta.cost >= 0, 'cost should be null or a non-negative number');

  await assert.rejects(
    () =>
      client.nr.chat({
        model: MODEL,
        prompt: 'This must not reach the network',
        guardrailIds: ['demo-guardrail'],
      }),
    nRouterConfigurationError,
  );

  return { text, meta: result.meta };
}

async function main() {
  const mode = process.argv.includes('--live') ? 'live' : 'dry-run';

  let transport;
  let client;
  if (mode === 'live') {
    loadRootEnv();
    client = new nRouter({
      apiKey: process.env.NROUTER_API_KEY,
      baseURL: process.env.NROUTER_BASE_URL || 'https://api.nrouter.ai/v1',
      maxRetries: 0,
    });
  } else {
    const fake = fakeRequester();
    transport = fake;
    client = fake.client;
  }

  let text;
  let meta;
  try {
    ({ text, meta } = await runAgent(client, mode));
    if (transport) {
      assert.equal(transport.calls.length, 2, 'dry-run should call models and chat only');
      assert.ok(new URL(transport.calls[1].url).pathname.endsWith('/messages'), 'Claude demo model should use the Messages endpoint');
    }
  } catch (error) {
    if (transport) console.error(JSON.stringify({ calls: transport.calls }, null, 2));
    throw error;
  }

  console.log(JSON.stringify({ mode, model: MODEL, text, requestId: meta.requestId, costStatus: meta.costStatus }, null, 2));
}

main().catch((error) => {
  console.error(error && error.stack ? error.stack : error && error.message ? error.message : error);
  process.exit(1);
});
