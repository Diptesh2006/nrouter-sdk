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
      promptTemplateId: 'tpl-1',
      promptVariables: { name: 'Ada' },
      guardrailIds: ['gr-1'],
      cache: false,
    },
  );

  assert.equal(seenUrl, `${BASE_URL}/responses`);
  assert.deepEqual(seenBody, {
    model: 'm',
    input: 'hello',
    nrouter_prompt_template_id: 'tpl-1',
    nrouter_prompt_variables: { name: 'Ada' },
    nrouter_guardrail_ids: ['gr-1'],
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

test('generic JSON helpers reject non-JSON success bodies as transport failures', async () => {
  const client = new nRouter({
    apiKey: TEST_KEY,
    maxRetries: 0,
    fetch: async () => new Response('ok', { status: 200, headers: { 'content-type': 'text/plain' } }),
  });

  await assert.rejects(
    () => client.nr.responses({ model: 'm', input: 'x' }),
    nRouterTransportError,
  );
});
