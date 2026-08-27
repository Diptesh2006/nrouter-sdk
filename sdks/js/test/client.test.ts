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

const { nRouter, isRetryable, nRouterError } = require('../dist/index');

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

// A proxy in front of the gateway can return a BARE envelope. OpenAI's
// APIError.generate keeps a nested `{"error":{…}}` body and DISCARDS a bare
// `{code,message}` one, so serializing only `err.error` lost both fields —
// and a guardrail block reclassified as a plain request error while a budget
// ceiling came back as insufficient credit. Opposite remedies, confidently
// wrong.
test('a BARE error envelope survives the vendor client and still classifies', async () => {
  const cases: [number, Record<string, string>, string][] = [
    [400, { code: 'guardrail_blocked', message: 'withheld' }, 'nRouterGuardrailBlockedError'],
    [402, { code: 'insufficient_credits', message: 'top up' }, 'nRouterCreditError'],
    [402, { message: 'budget exceeded for this team' }, 'nRouterBudgetExceededError'],
  ];
  for (const [status, body, expected] of cases) {
    const client = new nRouter({
      apiKey: TEST_KEY,
      maxRetries: 0,
      fetch: async () =>
        new Response(JSON.stringify(body), {
          status,
          headers: { 'content-type': 'application/json' },
        }),
    });
    await assert.rejects(
      () => client.nr.chat({ model: 'm', prompt: 'x' }),
      (err: unknown) => {
        assert.equal((err as Error).constructor.name, expected, `status ${status}`);
        return true;
      },
    );
  }
});

// Gateway gate 8: a retry is a second call and a second BILL. POST /videos is
// not idempotent and carries no idempotency key, so the vendor client's
// default of two retries can create and bill a second job.
test('a billed POST is sent exactly once, even on a retryable failure', async () => {
  let attempts = 0;
  const client = new nRouter({
    apiKey: TEST_KEY,
    // maxRetries deliberately NOT set: this pins the DEFAULT behaviour.
    fetch: async () => {
      attempts += 1;
      return new Response(JSON.stringify({ error: { message: 'upstream blip' } }), {
        status: 503,
        headers: { 'content-type': 'application/json' },
      });
    },
  });
  await assert.rejects(() => client.nr.chat({ model: 'm', prompt: 'x' }));
  assert.equal(attempts, 1, `a billed POST was sent ${attempts} times`);
});

// A non-JSON error has no parsed body — OpenAI keeps the response text in
// `message`. Reconstructing an empty body there discards the only signal
// present, and "the upstream response was too large to process" is the
// gateway's one PERMANENT 502. Losing it invites a retry of a billed request.
test('a text/plain error keeps its wording, so a permanent 502 stays permanent', async () => {
  const client = new nRouter({
    apiKey: TEST_KEY,
    maxRetries: 0,
    fetch: async () =>
      new Response('the upstream response was too large to process', {
        status: 502,
        headers: { 'content-type': 'text/plain' },
      }),
  });
  await assert.rejects(
    () => client.nr.chat({ model: 'm', prompt: 'x' }),
    (err: unknown) => {
      assert.match((err as Error).message, /too large/, 'the wording must survive');
      assert.equal(isRetryable(err), false, 'an oversized upstream response is permanent');
      return true;
    },
  );
});

// A socket that dies AFTER the headers arrived: the request reached the
// gateway and may have been billed, so the status and request id are the only
// correlation the caller has. Letting the body read reject raw threw both away.
test('a body-read failure keeps the status and request id', async () => {
  const client = new nRouter({
    apiKey: TEST_KEY,
    maxRetries: 0,
    fetch: async () =>
      new Response(
        new ReadableStream({
          start(controller) {
            controller.error(new Error('socket hang up'));
          },
        }),
        { status: 200, headers: { 'content-type': 'application/json', 'x-nr-request-id': 'nrouter-cut' } },
      ),
  });
  await assert.rejects(
    () => client.nr.chat({ model: 'm', prompt: 'x' }),
    (err: unknown) => {
      const e = err as { status?: number | null; requestId?: string | null; message: string };
      assert.equal(e.status, 200, 'the response DID arrive; status must not be null');
      assert.equal(e.requestId, 'nrouter-cut', 'the request id must survive');
      assert.match(e.message, /billed/);
      return true;
    },
  );
});

// MEASURED: `__binaryRequest` landed in openai 4.50.0 (absent in 4.49.0). The
// declared range was `^4.0.0`, so a consumer could resolve 4.44 — a client
// that ignores the flag and JSON.stringify's our Uint8Array bodies into
// {"0":82,…}. Every nr call would send corrupt data while THIS suite stayed
// green, because the lockfile pins 4.104.0. A test, not a comment, because a
// comment does not stop the range widening back.
test('the openai dependency floor keeps byte request bodies working', () => {
  const pkg = require('../package.json');
  const range: string = pkg.dependencies.openai;
  const floor = range.replace(/^[^0-9]*/, '');
  const [maj, min] = floor.split('.').map(Number);
  assert.equal(maj, 4, `unexpected major in ${range}`);
  assert.ok(min >= 50, `openai floor ${floor} predates __binaryRequest (4.50.0); byte bodies would be corrupted`);
});

// A BigInt or a circular reference in `extra` throws before anything is sent.
// It used to surface as a RETRYABLE transport failure, so a caller honouring
// isRetryable() looped forever on a permanent mistake in its own input.
test('an unencodable request body is permanent, not retryable', async () => {
  const client = new nRouter({ apiKey: TEST_KEY, maxRetries: 0, fetch: async () => new Response('{}') });
  const circular: Record<string, unknown> = {};
  circular.self = circular;
  for (const bad of [{ big: BigInt(1) }, circular]) {
    await assert.rejects(
      () => client.nr.chat({ model: 'm', prompt: 'x', extra: bad }),
      (err: unknown) => {
        // BOTH halves. `isRetryable` alone is not enough: it answers false for
        // any non-nRouterError too, so a RAW TypeError escaping unnormalized
        // would satisfy it and the test would pass while the SDK leaked a
        // vendor-shaped failure. That is exactly what the first version of
        // this test did — the mutation stayed green and said so.
        assert.ok(err instanceof nRouterError, 'must be inside the SDK error hierarchy');
        assert.equal((err as { kind?: string }).kind, 'configuration', 'local and permanent');
        assert.equal(isRetryable(err), false, 'nothing was sent; a retry cannot help');
        assert.match((err as Error).message, /cannot be JSON-encoded/);
        return true;
      },
    );
  }
});
