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

// Byte bodies must reach the wire as bytes. HISTORY, because the shape of this
// test changed with the dependency and the reason did not: under openai 4 the
// client JSON-stringified a Uint8Array into {"0":82,"1":73,…} unless
// `__binaryRequest: true` was passed, that flag landed in 4.50.0, and a
// declared `^4.0.0` let a consumer resolve 4.44 and send corrupt data on every
// nr call while this suite stayed green on a pinned lockfile.
//
// openai 7 removed the flag and made the behaviour the default — `buildBody`
// passes anything `ArrayBuffer.isView` verbatim. So the version assertion is
// no longer the property worth pinning; the BEHAVIOUR is. This sends real
// bytes through the real client and reads what `fetch` was handed, which
// cannot pass while a future release quietly re-encodes them.
test('a byte request body reaches fetch as bytes, not re-encoded JSON', async () => {
  let seen: unknown = null;
  const client = new nRouter({
    apiKey: TEST_KEY,
    maxRetries: 0,
    fetch: async (_url: unknown, init: any) => {
      seen = init?.body;
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    },
  });

  // `speech` is a byte path: the SDK encodes the request itself and hands the
  // transport a Uint8Array.
  await client.nr.media
    .speech({ model: 'tts-1', input: 'hi', voice: 'alloy' })
    .catch(() => undefined);

  assert.ok(seen !== null, 'nothing reached fetch');
  const isBytes = ArrayBuffer.isView(seen) || seen instanceof ArrayBuffer;
  assert.ok(
    isBytes,
    `fetch received ${Object.prototype.toString.call(seen)}; a re-encoded body corrupts every byte request`,
  );
  const view = seen as ArrayBufferView;
  const text = new TextDecoder().decode(
    new Uint8Array(view.buffer, view.byteOffset, view.byteLength),
  );
  // Proves it is OUR encoding that survived, not an object stringified into
  // something that merely happens to be bytes.
  assert.match(text, /"model"\s*:\s*"tts-1"/, 'the encoded body did not survive intact');
  assert.doesNotMatch(text, /^\s*\{\s*"0"\s*:/, 'the body was re-encoded index-by-index');
});

// The declared floor still matters — it is what a CONSUMER resolves, and this
// suite runs against a pinned lockfile that would hide a bad resolution.
test('the declared openai range cannot resolve below the byte-body behaviour', () => {
  const pkg = require('../package.json');
  const range: string = pkg.dependencies.openai;
  const floor = range.replace(/^[^0-9]*/, '');
  const [maj] = floor.split('.').map(Number);
  assert.ok(
    maj >= 7,
    `openai floor ${floor}: majors below 7 need __binaryRequest, which this SDK no longer passes, so byte bodies would be re-encoded`,
  );
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

// MEASURED: `new OpenAI.APIUserAbortError().name` is the string "Error", so a
// name-based abort check misses the vendor's own cancellation entirely. It was
// wrapped as an ordinary transport failure and reported RETRYABLE — a generic
// retry loop could resend a cancelled POST that had already been billed.
test('a cancellation before headers is never reported as retryable', async () => {
  const controller = new AbortController();
  const client = new nRouter({
    apiKey: TEST_KEY,
    maxRetries: 0,
    fetch: (_url: unknown, init: any) =>
      new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => {
          const e = new Error('aborted');
          e.name = 'AbortError';
          reject(e);
        });
      }),
  });
  setTimeout(() => controller.abort(), 5);
  await assert.rejects(
    () => client.nr.media.speech(
      { model: 'tts-1', input: 'hi', voice: 'alloy' },
      { signal: controller.signal } as never,
    ),
    (err: unknown) => {
      assert.equal(isRetryable(err), false, 'a cancelled, billed request must never be resent');
      return true;
    },
  );
});

// The vendor's abort class carries its identity on the CONSTRUCTOR, not the
// name — so the shared check must look at both.
test('isAbortLike recognises the vendor abort class despite its name', () => {
  const { isAbortLike } = require('../dist/errors');
  const OpenAI = require('openai').default;
  const vendor = new OpenAI.APIUserAbortError();
  assert.equal(vendor.name, 'Error', 'precondition: the vendor does not set name');
  assert.equal(isAbortLike(vendor), true, 'must be recognised by constructor');
});

// CREDENTIAL DISCLOSURE TO THE WRONG SERVICE. openai 7 reads
// OPENAI_CUSTOM_HEADERS, OPENAI_ORG_ID, OPENAI_PROJECT_ID and OPENAI_ADMIN_KEY
// from the environment, and merges the parsed custom headers BEFORE
// `defaultHeaders` — so they beat the auth header it derives from `apiKey`.
//
// MEASURED before the fix, with those variables set: `nr.chat()` sent
// `authorization: Bearer sk-openai-LEAKED` and `openai-organization: org-leak`
// to api.nrouter.ai. Nothing unusual is required to hit it — one process using
// both clients, one env var meant for the other one.
test('an OpenAI env credential never reaches the nRouter gateway', async () => {
  const saved = {
    h: process.env.OPENAI_CUSTOM_HEADERS,
    o: process.env.OPENAI_ORG_ID,
    p: process.env.OPENAI_PROJECT_ID,
    a: process.env.OPENAI_ADMIN_KEY,
  };
  process.env.OPENAI_CUSTOM_HEADERS =
    'Authorization: Bearer sk-openai-LEAKED\nOpenAI-Organization: org-leak';
  process.env.OPENAI_ORG_ID = 'org-env';
  process.env.OPENAI_PROJECT_ID = 'proj-env';
  process.env.OPENAI_ADMIN_KEY = 'sk-admin-LEAKED';
  try {
    let seen: Record<string, string> = {};
    const client = new nRouter({
      apiKey: TEST_KEY,
      maxRetries: 0,
      fetch: async (_url: unknown, init: any) => {
        seen = Object.fromEntries(new Headers(init.headers).entries());
        return new Response(JSON.stringify({ choices: [] }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        });
      },
    });
    await client.nr.chat({ model: 'm', prompt: 'x' }).catch(() => undefined);

    assert.equal(
      seen.authorization,
      `Bearer ${TEST_KEY}`,
      'the key on the wire must be the nRouter key that was validated, not one from the environment',
    );
    assert.doesNotMatch(JSON.stringify(seen), /LEAKED/, 'no OpenAI credential may appear in any header');
    assert.equal(seen['openai-organization'], undefined, 'OpenAI tenancy headers do not belong on a gateway call');
    assert.equal(seen['openai-project'], undefined);
  } finally {
    const restore = (k: string, v: string | undefined) =>
      v === undefined ? delete process.env[k] : (process.env[k] = v);
    restore('OPENAI_CUSTOM_HEADERS', saved.h);
    restore('OPENAI_ORG_ID', saved.o);
    restore('OPENAI_PROJECT_ID', saved.p);
    restore('OPENAI_ADMIN_KEY', saved.a);
  }
});

// `withOptions()` re-enters the constructor with the vendor's OWN branded
// header bag (`{ values: Headers, nulls: Set }`), not a plain object. Spreading
// that appends `Authorization` beside `values`, where the vendor never reads
// it — so the OLD key stays on the wire, authenticating and BILLING the wrong
// tenant on a call the caller believes re-keyed.
test('withOptions re-keys the wire, and the env cannot override it', async () => {
  const saved = process.env.OPENAI_CUSTOM_HEADERS;
  process.env.OPENAI_CUSTOM_HEADERS = 'Authorization: Bearer sk-openai-LEAKED';
  const SECOND = 'sk-nrouter-second000000000000abcd';
  try {
    let seen: Record<string, string> = {};
    const base = new nRouter({
      apiKey: TEST_KEY,
      maxRetries: 0,
      fetch: async (_url: unknown, init: any) => {
        seen = Object.fromEntries(new Headers(init.headers).entries());
        return new Response(JSON.stringify({ choices: [] }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        });
      },
    });
    await base.withOptions({ apiKey: SECOND }).nr.chat({ model: 'm', prompt: 'x' }).catch(() => undefined);
    assert.equal(seen.authorization, `Bearer ${SECOND}`, 'withOptions must actually re-key the request');
    assert.doesNotMatch(JSON.stringify(seen), /LEAKED/);
  } finally {
    if (saved === undefined) delete process.env.OPENAI_CUSTOM_HEADERS;
    else process.env.OPENAI_CUSTOM_HEADERS = saved;
  }
});

// OPENAI_CUSTOM_HEADERS is free-form: a credential can arrive under ANY name.
// Nulling only Authorization / OpenAI-Organization / OpenAI-Project forwards
// everything else to api.nrouter.ai (gateway gate 9: no provider credential in
// a customer-visible header). A header the CALLER set stays — only the
// environment's contribution is removed.
test('an env custom header under any name is stripped; the caller keeps theirs', async () => {
  const saved = process.env.OPENAI_CUSTOM_HEADERS;
  process.env.OPENAI_CUSTOM_HEADERS =
    'api-key: sk-openai-LEAKED\nX-Weird-Cred: LEAKED\nX-Kept: from-env';
  try {
    let seen: Record<string, string> = {};
    const client = new nRouter({
      apiKey: TEST_KEY,
      maxRetries: 0,
      // The caller names one of the same headers on purpose: their intent wins.
      defaultHeaders: { 'X-Kept': 'from-caller', 'User-Agent': null } as never,
      fetch: async (_url: unknown, init: any) => {
        seen = Object.fromEntries(new Headers(init.headers).entries());
        return new Response(JSON.stringify({ choices: [] }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        });
      },
    });
    await client.nr.chat({ model: 'm', prompt: 'x' }).catch(() => undefined);

    assert.doesNotMatch(JSON.stringify(seen), /LEAKED/, 'no env-supplied credential may reach the gateway');
    assert.equal(seen['api-key'], undefined);
    assert.equal(seen['x-weird-cred'], undefined);
    assert.equal(seen['x-kept'], 'from-caller', "the caller's own header must survive");
    assert.equal(seen['user-agent'], undefined, 'a null header removal must survive normalization');
  } finally {
    if (saved === undefined) delete process.env.OPENAI_CUSTOM_HEADERS;
    else process.env.OPENAI_CUSTOM_HEADERS = saved;
  }
});

// `'toString' in {}` is TRUE. A plain object keyed by environment-supplied
// header names reports inherited members as already-present, so a credential
// smuggled as `toString: …` looked like one the caller had set and was
// forwarded. Header names are also case-insensitive, so an env `AUTHORIZATION`
// must not read as a different header from a caller's `Authorization`.
test('a prototype-named or differently-cased env header is still stripped', async () => {
  const saved = process.env.OPENAI_CUSTOM_HEADERS;
  process.env.OPENAI_CUSTOM_HEADERS =
    'toString: sk-openai-LEAKED\nconstructor: LEAKED\nhasOwnProperty: LEAKED\nAUTHORIZATION: Bearer sk-openai-LEAKED';
  try {
    let seen: Record<string, string> = {};
    const client = new nRouter({
      apiKey: TEST_KEY,
      maxRetries: 0,
      fetch: async (_url: unknown, init: any) => {
        seen = Object.fromEntries(new Headers(init.headers).entries());
        return new Response(JSON.stringify({ choices: [] }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        });
      },
    });
    await client.nr.chat({ model: 'm', prompt: 'x' }).catch(() => undefined);
    assert.doesNotMatch(JSON.stringify(seen), /LEAKED/, 'no env-supplied value may reach the gateway');
    assert.equal(seen.authorization, `Bearer ${TEST_KEY}`);
  } finally {
    if (saved === undefined) delete process.env.OPENAI_CUSTOM_HEADERS;
    else process.env.OPENAI_CUSTOM_HEADERS = saved;
  }
});

// `HeadersLike` carries three distinct meanings and one multi-value form.
// Collapsing any of them loses something the vendor acts on: `undefined` is
// OMITTED (leave the vendor's own header alone), `null` REMOVES it, and a
// repeated name or an array value is several values of ONE header.
test('multi-value headers survive, and undefined is not treated as a removal', async () => {
  let seen: Record<string, string> = {};
  const client = new nRouter({
    apiKey: TEST_KEY,
    maxRetries: 0,
    defaultHeaders: [
      ['X-Tag', 'a'],
      ['X-Tag', 'b'],
      ['X-Undef', undefined],
    ] as never,
    fetch: async (_url: unknown, init: any) => {
      seen = Object.fromEntries(new Headers(init.headers).entries());
      return new Response(JSON.stringify({ choices: [] }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    },
  });
  await client.nr.chat({ model: 'm', prompt: 'x' }).catch(() => undefined);
  assert.match(seen['x-tag'] ?? '', /a/, 'the first value of a repeated header was dropped');
  assert.match(seen['x-tag'] ?? '', /b/, 'the second value of a repeated header was dropped');
  assert.equal(seen.authorization, `Bearer ${TEST_KEY}`);
});

// `undefined` is not an expression of intent. Registering it as caller-set
// suppressed the environment strip, so `{ 'api-key': undefined }` next to
// `OPENAI_CUSTOM_HEADERS=api-key: sk-openai-…` forwarded the credential.
test('an undefined caller header does not shield an env credential of the same name', async () => {
  const saved = process.env.OPENAI_CUSTOM_HEADERS;
  process.env.OPENAI_CUSTOM_HEADERS = 'api-key: sk-openai-LEAKED';
  try {
    let seen: Record<string, string> = {};
    const client = new nRouter({
      apiKey: TEST_KEY,
      maxRetries: 0,
      defaultHeaders: { 'api-key': undefined, 'X-Arr': ['a', undefined, 'b'] } as never,
      fetch: async (_url: unknown, init: any) => {
        seen = Object.fromEntries(new Headers(init.headers).entries());
        return new Response(JSON.stringify({ choices: [] }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        });
      },
    });
    await client.nr.chat({ model: 'm', prompt: 'x' }).catch(() => undefined);
    assert.doesNotMatch(JSON.stringify(seen), /LEAKED/, 'the env credential must still be stripped');
    assert.equal(seen['api-key'], undefined);
    // And `undefined` inside an array is skipped, never stringified.
    assert.doesNotMatch(seen['x-arr'] ?? '', /undefined/, 'literal "undefined" reached the wire');
  } finally {
    if (saved === undefined) delete process.env.OPENAI_CUSTOM_HEADERS;
    else process.env.OPENAI_CUSTOM_HEADERS = saved;
  }
});

// Header names are case-insensitive and the vendor applies entries in ORDER.
// Exact-case slots keep only the last casing, and short-circuiting on "the
// array contains a null" deletes a header the caller had just re-set.
test('repeated header names accumulate across casings, and a value after null restores it', async () => {
  let seen: Record<string, string> = {};
  const client = new nRouter({
    apiKey: TEST_KEY,
    maxRetries: 0,
    defaultHeaders: [
      ['X-Tag', 'a'],
      ['x-tag', 'b'],
      ['X-Restored', null],
      ['X-Restored', 'back'],
    ] as never,
    fetch: async (_url: unknown, init: any) => {
      seen = Object.fromEntries(new Headers(init.headers).entries());
      return new Response(JSON.stringify({ choices: [] }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    },
  });
  await client.nr.chat({ model: 'm', prompt: 'x' }).catch(() => undefined);
  assert.match(seen['x-tag'] ?? '', /a/, 'the differently-cased first value was dropped');
  assert.match(seen['x-tag'] ?? '', /b/);
  assert.equal(seen['x-restored'], 'back', 'a value after a null must restore the header');
  assert.equal(seen.authorization, `Bearer ${TEST_KEY}`);
});

// This SDK supports the browser via `dangerouslyAllowBrowser`, and browsers,
// workers and Deno have no `process`. An unguarded `process.env[...]` throws a
// ReferenceError at CONSTRUCTION — before the caller's explicit key is even
// looked at — so the whole client is unusable there.
test('the client constructs in a runtime with no `process`', async () => {
  const real = globalThis.process;
  Object.defineProperty(globalThis, 'process', { value: undefined, configurable: true });
  try {
    const client = new nRouter({
      apiKey: TEST_KEY,
      dangerouslyAllowBrowser: true,
      maxRetries: 0,
      fetch: async () =>
        new Response(JSON.stringify({ choices: [] }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
    });
    assert.ok(client, 'the constructor must not read process.env unguarded');

    // And the NO-key path, which is the one that actually reaches the env
    // lookup: it must refuse with this SDK's own configuration error, not a
    // ReferenceError from touching `process`.
    assert.throws(
      () => new nRouter({ dangerouslyAllowBrowser: true }),
      (err: unknown) => {
        assert.ok(err instanceof nRouterError, `got ${(err as Error)?.constructor?.name}`);
        assert.equal((err as { kind?: string }).kind, 'configuration');
        return true;
      },
    );
  } finally {
    Object.defineProperty(globalThis, 'process', { value: real, configurable: true });
  }
});

// An empty array, or one holding only `undefined`, contributes nothing. A slot
// created for it would be `null` — REMOVING the vendor's own header — and
// would register caller intent that suppresses the environment strip.
test('an empty header array removes nothing and shields nothing', async () => {
  const saved = process.env.OPENAI_CUSTOM_HEADERS;
  process.env.OPENAI_CUSTOM_HEADERS = 'api-key: sk-openai-LEAKED';
  try {
    let seen: Record<string, string> = {};
    const client = new nRouter({
      apiKey: TEST_KEY,
      maxRetries: 0,
      defaultHeaders: { 'User-Agent': [], 'api-key': [undefined] } as never,
      fetch: async (_url: unknown, init: any) => {
        seen = Object.fromEntries(new Headers(init.headers).entries());
        return new Response(JSON.stringify({ choices: [] }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        });
      },
    });
    await client.nr.chat({ model: 'm', prompt: 'x' }).catch(() => undefined);
    assert.ok(seen['user-agent'], 'an empty array must not remove the vendor header');
    assert.doesNotMatch(JSON.stringify(seen), /LEAKED/, 'and must not shield an env credential');
  } finally {
    if (saved === undefined) delete process.env.OPENAI_CUSTOM_HEADERS;
    else process.env.OPENAI_CUSTOM_HEADERS = saved;
  }
});

// `fetchOptions` is spread onto the request AFTER the headers this SDK builds,
// so `fetchOptions.headers` overwrote them wholesale — Authorization included.
// Same credential disclosure and wrong-tenant billing as the env channel,
// reached by a different door. Other transport settings there are kept.
test('fetchOptions.headers cannot override the pinned Authorization', async () => {
  let seen: Record<string, string> = {};
  const client = new nRouter({
    apiKey: TEST_KEY,
    maxRetries: 0,
    fetchOptions: {
      headers: { Authorization: 'Bearer sk-openai-LEAKED', 'X-Sneak': 'LEAKED' },
      keepalive: true,
    } as never,
    fetch: async (_url: unknown, init: any) => {
      seen = Object.fromEntries(new Headers(init.headers).entries());
      return new Response(JSON.stringify({ choices: [] }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    },
  });
  await client.nr.chat({ model: 'm', prompt: 'x' }).catch(() => undefined);
  assert.equal(seen.authorization, `Bearer ${TEST_KEY}`, 'fetchOptions must not re-key the request');
  assert.doesNotMatch(JSON.stringify(seen), /LEAKED/);
});

// A RECORD property is a setter; a tuple entry is a list item. `{ 'X-Tag': 'a',
// 'x-tag': 'b' }` is the same header written twice and ends as `b`, while
// `[['X-Tag','a'],['x-tag','b']]` is two values and keeps both.
test('record header properties overwrite, tuple entries accumulate', async () => {
  const send = async (defaultHeaders: unknown) => {
    let seen: Record<string, string> = {};
    const client = new nRouter({
      apiKey: TEST_KEY,
      maxRetries: 0,
      defaultHeaders: defaultHeaders as never,
      fetch: async (_url: unknown, init: any) => {
        seen = Object.fromEntries(new Headers(init.headers).entries());
        return new Response(JSON.stringify({ choices: [] }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        });
      },
    });
    await client.nr.chat({ model: 'm', prompt: 'x' }).catch(() => undefined);
    return seen;
  };
  assert.equal((await send({ 'X-Tag': 'a', 'x-tag': 'b' }))['x-tag'], 'b', 'record properties are setters');
  const tupled = (await send([['X-Tag', 'a'], ['x-tag', 'b']]))['x-tag'] ?? '';
  assert.match(tupled, /a/, 'tuple entries are a list');
  assert.match(tupled, /b/);
});

// PER-REQUEST fetchOptions. openai 7 lets an inherited resource take them as a
// second argument and spreads them onto the request LAST, so nothing the
// constructor sanitizes can reach that path. The pinned fetch wrapper is what
// covers it — the last seam before the request leaves.
test('per-request fetchOptions.headers cannot re-key an inherited resource call', async () => {
  let seen: Record<string, string> = {};
  const client = new nRouter({
    apiKey: TEST_KEY,
    maxRetries: 0,
    fetch: async (_url: unknown, init: any) => {
      seen = Object.fromEntries(new Headers(init.headers).entries());
      return new Response(JSON.stringify({ choices: [] }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    },
  });
  await client.chat.completions
    .create({ model: 'm', messages: [{ role: 'user', content: 'x' }] }, {
      fetchOptions: {
        headers: { Authorization: 'Bearer sk-openai-LEAKED', 'X-Caller-Own': 'kept' },
      },
    } as never)
    .catch(() => undefined);
  assert.equal(
    seen.authorization,
    `Bearer ${TEST_KEY}`,
    'the validated key must be the one on the wire',
  );
  // The caller's OWN header survives, and that is the correct line. This wrapper
  // pins authentication and removes another service's tenancy headers; it is not
  // a filter on what a developer deliberately sends. The leak this whole
  // sequence is about is a credential the caller never chose — from the
  // environment, or overriding the key they DID choose.
  assert.equal(seen['x-caller-own'], 'kept');
});
