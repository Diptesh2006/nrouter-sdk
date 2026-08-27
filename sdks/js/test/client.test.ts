// The connection contract, ported from the old test/smoke.js (which is now the
// runner entry point) and from sdks/go/client_test.go's TestResolveAPIKey /
// TestDefaultBaseURLIsTheGateway / TestClientNeverPrintsTheKey.
//
// Case 15 lives here too, at the surface where it actually bites: a client
// holds the key, and `console.log(client)` or an error thrown out of a failed
// request must never render it.

const { test } = require('node:test');
const assert = require('node:assert/strict');
const util = require('node:util');

const { nRouter } = require('../dist/index');

const KEY_PREFIX = 'sk-nrouter-';
const ENV_KEY = 'NROUTER_API_KEY';
const BASE_URL = 'https://api.nrouter.ai/v1';
const TEST_KEY = `${KEY_PREFIX}test0000000000000abcd`;

/** Read the Authorization header out of whatever shape the SDK passed. */
function authOf(init: any): string | undefined {
  const h = init && init.headers;
  if (!h) return undefined;
  if (typeof h.get === 'function') return h.get('authorization');
  return h.Authorization ?? h.authorization;
}

/**
 * Render a value the way a careless log line would, without letting an
 * incidental circular reference mask a real leak.
 */
function safeJSON(value: unknown): string {
  const seen = new WeakSet<object>();
  try {
    return JSON.stringify(value, (_k, v) => {
      if (typeof v === 'object' && v !== null) {
        if (seen.has(v)) return '[circular]';
        seen.add(v);
      }
      return v;
    }) ?? '';
  } catch {
    return '';
  }
}

function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json', ...headers },
  });
}

test('a key without the nRouter prefix is refused LOCALLY, before any request', () => {
  // A foreign key (an OpenAI `sk-proj-…`) reaching the gateway is a round trip
  // and a 401 for something decidable here.
  for (const bad of ['bad-key', 'sk-proj-anopenaikey', 'sk-ant-something']) {
    assert.throws(() => new nRouter({ apiKey: bad }), new RegExp(KEY_PREFIX), `accepted ${bad}`);
  }
});

test('a missing key names the environment variable that supplies it', () => {
  const saved = process.env[ENV_KEY];
  delete process.env[ENV_KEY];
  try {
    assert.throws(() => new nRouter({}), new RegExp(ENV_KEY));
  } finally {
    if (saved !== undefined) process.env[ENV_KEY] = saved;
  }
});

test('an explicit key wins over the environment', async () => {
  const saved = process.env[ENV_KEY];
  process.env[ENV_KEY] = `${KEY_PREFIX}from-env`;
  try {
    let seenAuth = '';
    const client = new nRouter({
      apiKey: TEST_KEY,
      fetch: async (_url: unknown, init: unknown) => {
        seenAuth = authOf(init) ?? '';
        return jsonResponse({ object: 'list', data: [] });
      },
    });
    await client.nrouterModels.list();
    assert.equal(seenAuth, `Bearer ${TEST_KEY}`);
  } finally {
    if (saved === undefined) delete process.env[ENV_KEY];
    else process.env[ENV_KEY] = saved;
  }
});

test('the key falls back to the environment', async () => {
  const saved = process.env[ENV_KEY];
  process.env[ENV_KEY] = TEST_KEY;
  try {
    let seenAuth = '';
    const client = new nRouter({
      fetch: async (_url: unknown, init: unknown) => {
        seenAuth = authOf(init) ?? '';
        return jsonResponse({ object: 'list', data: [] });
      },
    });
    await client.nrouterModels.list();
    assert.equal(seenAuth, `Bearer ${TEST_KEY}`);
  } finally {
    if (saved === undefined) delete process.env[ENV_KEY];
    else process.env[ENV_KEY] = saved;
  }
});

test('the default base URL is the gateway, and /v1 is not repeated', async () => {
  // `/v1` is not ours to rename: OpenAI's SDK appends `/chat/completions` to
  // base_url, and `/api/v1/*` 404s at the gateway.
  let seenUrl = '';
  const client = new nRouter({
    apiKey: TEST_KEY,
    fetch: async (url: unknown) => {
      seenUrl = String(url);
      return jsonResponse({ object: 'list', data: [] });
    },
  });
  await client.nrouterModels.list();
  assert.equal(seenUrl, `${BASE_URL}/models`);
  assert.equal(seenUrl.includes('/v1/v1'), false);
  assert.equal(seenUrl.includes('/api/v1'), false);
});

test("model discovery travels the CLIENT'S transport, not a global fetch", async () => {
  // Going through the configured pipeline is what keeps a caller's fetch
  // override, timeout, retries, proxy and default headers applied to it.
  const savedFetch = globalThis.fetch;
  (globalThis as any).fetch = async () => {
    throw new Error('global fetch must not be used when a transport is configured');
  };
  try {
    let calls = 0;
    const client = new nRouter({
      apiKey: TEST_KEY,
      fetch: async () => {
        calls += 1;
        return jsonResponse({
          object: 'list',
          data: [{ id: 'claude-haiku', object: 'model', owned_by: 'nrouter' }],
        });
      },
    });
    const models = await client.nrouterModels.list();
    assert.equal(calls, 1);
    assert.equal(models.data.length, 1);
    assert.equal(models.data[0].id, 'claude-haiku');
  } finally {
    (globalThis as any).fetch = savedFetch;
  }
});

test('the snake_case alias is the same object, not a second instance', () => {
  const client = new nRouter({ apiKey: TEST_KEY });
  assert.equal(client.nrouter_models, client.nrouterModels);
});

// ---------------------------------------------------------------------------
// Case 15 — the key never renders.
// ---------------------------------------------------------------------------

test('no rendering of the client prints the API key', () => {
  const client = new nRouter({ apiKey: TEST_KEY });
  const renderings = [
    String(client),
    `${client}`,
    safeJSON(client),
    util.inspect(client, { depth: 4 }),
    util.inspect({ wrapped: client }, { depth: 5 }),
  ];
  for (const rendered of renderings) {
    assert.equal(
      rendered.includes(TEST_KEY),
      false,
      `a rendering leaked the api key: ${rendered.slice(0, 200)}`
    );
  }
});

test('an error thrown out of a failed request never carries the key', async () => {
  const client = new nRouter({
    apiKey: TEST_KEY,
    maxRetries: 0,
    fetch: async () =>
      jsonResponse(
        { error: { code: 'invalid_api_key', message: `key ${TEST_KEY} refused` } },
        401
      ),
  });

  let thrown: any;
  try {
    await client.nrouterModels.list();
  } catch (err) {
    thrown = err;
  }
  assert.ok(thrown, 'a 401 must raise');

  for (const rendered of [
    String(thrown),
    thrown.message ?? '',
    thrown.stack ?? '',
    safeJSON(thrown),
    util.inspect(thrown, { depth: 3 }),
  ]) {
    assert.equal(
      rendered.includes(TEST_KEY),
      false,
      `a thrown error leaked the api key: ${rendered.slice(0, 300)}`
    );
  }
});
