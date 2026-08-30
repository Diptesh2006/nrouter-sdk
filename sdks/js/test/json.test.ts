const { test } = require('node:test');
const assert = require('node:assert/strict');

const {
  nRouter,
  nRouterGuardrailBlockedError,
  nRouterTransportError,
} = require('../dist/index');

const TEST_KEY = 'sk-nrouter-test0000000000000abcd';
const BASE_URL = 'https://api.nrouter.ai/v1';

function jsonResponse(body, status = 200, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json', ...headers },
  });
}

async function bodyOf(init) {
  return JSON.parse(new TextDecoder().decode(init.body));
}

test('nr.responses posts through the client transport and preserves nRouter feature fields', async () => {
  let seenUrl = '';
  let seenBody = null;
  const client = new nRouter({
    apiKey: TEST_KEY,
    fetch: async (url, init) => {
      seenUrl = String(url);
      seenBody = await bodyOf(init);
      return jsonResponse(
        { id: 'resp_1', output_text: 'hello' },
        200,
        {
          'x-nr-request-id': 'req-responses',
          'x-nr-request-cost': '0.0012',
          'x-nr-cost-status': 'exact',
        },
      );
    },
  });

  const res = await client.nr.responses(
    { model: 'm', input: 'hello' },
    {
      // `guardrailIds` is deliberately absent: it is no longer a wire field.
      // The gateway reads no per-request guardrail override (0 references,
      // measured 2026-08-28), so buildExtraBody now REFUSES a non-empty list
      // rather than forwarding it to the provider. See test/options.test.ts.
      promptTemplateId: 'tpl-1',
      promptVariables: { name: 'Ada' },
      cache: false,
    },
  );

  assert.equal(seenUrl, `${BASE_URL}/responses`);
  assert.deepEqual(seenBody, {
    model: 'm',
    input: 'hello',
    nrouter_prompt_template_id: 'tpl-1',
    nrouter_prompt_variables: { name: 'Ada' },
    nrouter_cache: false,
  });
  assert.deepEqual(res.body, { id: 'resp_1', output_text: 'hello' });
  assert.equal(res.meta.requestId, 'req-responses');
  assert.equal(res.meta.cost, 0.0012);
});

test('nr.messages posts OpenAI-style messages and metadata', async () => {
  let seenUrl = '';
  let seenBody = null;
  const client = new nRouter({
    apiKey: TEST_KEY,
    fetch: async (url, init) => {
      seenUrl = String(url);
      seenBody = await bodyOf(init);
      return jsonResponse(
        { id: 'msg_1', content: [{ type: 'text', text: 'done' }] },
        200,
        { 'x-nr-request-id': 'req-messages' },
      );
    },
  });

  const res = await client.nr.messages(
    { model: 'm', messages: [{ role: 'user', content: 'hello' }] },
    { cache: false },
  );

  assert.equal(seenUrl, `${BASE_URL}/messages`);
  assert.deepEqual(seenBody, {
    model: 'm',
    messages: [{ role: 'user', content: 'hello' }],
    nrouter_cache: false,
  });
  assert.equal(res.body.id, 'msg_1');
  assert.equal(res.meta.requestId, 'req-messages');
});

test('nr.countTokens posts the caller body unchanged', async () => {
  let seenUrl = '';
  let seenBody = null;
  const client = new nRouter({
    apiKey: TEST_KEY,
    fetch: async (url, init) => {
      seenUrl = String(url);
      seenBody = await bodyOf(init);
      return jsonResponse({ input_tokens: 7 }, 200, { 'x-nr-request-id': 'req-tokens' });
    },
  });

  const body = { model: 'm', messages: [{ role: 'user', content: 'hello' }] };
  const res = await client.nr.countTokens(body);

  assert.equal(seenUrl, `${BASE_URL}/messages/count_tokens`);
  assert.deepEqual(seenBody, body);
  assert.deepEqual(res.body, { input_tokens: 7 });
  assert.equal(res.meta.requestId, 'req-tokens');
});

test('generic JSON helpers classify gateway errors', async () => {
  const client = new nRouter({
    apiKey: TEST_KEY,
    maxRetries: 0,
    fetch: async () =>
      jsonResponse(
        { error: { code: 'guardrail_blocked', message: 'blocked by policy' } },
        400,
      ),
  });

  await assert.rejects(
    () => client.nr.responses({ model: 'm', input: 'x' }),
    nRouterGuardrailBlockedError,
  );
});

// This test asserted nRouterTransportError and was PINNING THE DEFECT: it
// passed precisely because json.ts classified a billed 2xx as retryable. A
// test can be green and still be the bug's alibi. Corrected to the
// classification chat.ts and multimodal.ts have used all along; the money
// reasoning is on the regression test below.
test('generic JSON helpers reject non-JSON success bodies as a permanent misuse', async () => {
  const { nRouterConfigurationError } = require('../dist/index');
  const client = new nRouter({
    apiKey: TEST_KEY,
    maxRetries: 0,
    fetch: async () => new Response('ok', { status: 200, headers: { 'content-type': 'text/plain' } }),
  });

  await assert.rejects(
    () => client.nr.responses({ model: 'm', input: 'x' }),
    nRouterConfigurationError,
  );
});

// REGRESSION — a 2xx that is not JSON must be PERMANENT, never retryable.
//
// The response was BILLED. `nr.responses()`/`nr.messages()` returning a
// retryable error here means a caller's ordinary `while (isRetryable(e))` loop
// resends an already-charged POST, at whatever rate the loop turns. chat.ts
// (REFUSAL 1) and multimodal.ts (`requireJson`) both classify this as
// CONFIGURATION for exactly that reason — the wrong method was called for the
// endpoint, and no retry can change it. json.ts shipped it as a transport
// error, which is the same defect a reviewer already caught once in the Go
// draft.
test('a 2xx that is not JSON is permanent, not retryable — a retry re-bills it', async () => {
  const { isRetryable, nRouterConfigurationError } = require('../dist/index');
  const client = new nRouter({
    apiKey: TEST_KEY,
    fetch: async () =>
      new Response('RIFF....binary audio....', {
        status: 200,
        headers: { 'content-type': 'audio/mpeg', 'x-nr-request-id': 'req_billed_1' },
      }),
  });

  await assert.rejects(
    () => client.nr.responses({ model: 'claude-sonnet-4-5', input: 'hi' }),
    (err) => {
      assert.ok(
        err instanceof nRouterConfigurationError,
        `expected a configuration error, got ${err?.constructor?.name}`,
      );
      assert.equal(isRetryable(err), false, 'a billed 2xx must never be retryable');
      // The request id is the caller's only join key to the spend row.
      assert.equal(err.meta?.requestId, 'req_billed_1');
      assert.equal(err.status, 200);
      return true;
    },
  );
});

test('jsonRequest throws transport error on malformed JSON with 2xx application/json', async () => {
  const client = new nRouter({
    apiKey: TEST_KEY,
    fetch: async () =>
      new Response('{ invalid json', {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
  });

  await assert.rejects(
    () => client.nr.responses({ model: 'm', input: 'hi' }),
    nRouterTransportError,
  );
});

test('jsonRequest throws transport error when 2xx returns JSON that is not an object', async () => {
  const client = new nRouter({
    apiKey: TEST_KEY,
    fetch: async () =>
      new Response('["array", "not", "object"]', {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
  });

  await assert.rejects(
    () => client.nr.responses({ model: 'm', input: 'hi' }),
    nRouterTransportError,
  );
});

test('jsonRequest throws classified error when 2xx carries an error envelope', async () => {
  const client = new nRouter({
    apiKey: TEST_KEY,
    fetch: async () =>
      new Response(JSON.stringify({ error: { code: 'guardrail_blocked', message: 'blocked' } }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
  });

  await assert.rejects(
    () => client.nr.responses({ model: 'm', input: 'hi' }),
    nRouterGuardrailBlockedError,
  );
});

test('jsonRequest classifies non-JSON 500 error response', async () => {
  const client = new nRouter({
    apiKey: TEST_KEY,
    fetch: async () =>
      new Response('Internal Server Error Plain Text', {
        status: 500,
        headers: { 'content-type': 'text/plain' },
      }),
  });

  await assert.rejects(
    () => client.nr.responses({ model: 'm', input: 'hi' }),
    (err) => {
      assert.equal(err.status, 500);
      assert.ok(err.message.contains ? err.message.contains('Internal Server Error') : err.message.includes('Internal Server Error'));
      return true;
    },
  );
});
