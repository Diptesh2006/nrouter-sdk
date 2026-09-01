// BILLED acceptance probes. Every test here reaches a real gateway, a real
// provider and a real credit balance.
//
// # Why the gate is node:test's own `skip` and not an early `return`
//
// An early `return` inside the test body is a PASS to the runner, so a machine
// with no key, no gateway and no credits would print these probes as passing —
// release evidence that cannot distinguish a probe that ran from one that never
// executed a line. `{ skip }` is decided BEFORE the body runs, so the TAP output
// says `# SKIP` with its reason. Non-execution can be skipped or a failure; it
// can never be a pass.
//
//   npm test                       # every probe reports SKIP
//   NROUTER_LIVE=1 npm test        # runs them; needs the env below
//
// # And why a missing per-wire variable is a THROW, not a skip
//
// Once NROUTER_LIVE=1 is set the caller has asked for the billed probes. A
// missing variable at that point is a misconfigured live run, not a reason to
// report success — so `required()` throws and names the variable.
//
// # The route-family matrix
//
// Claude-through-/v1/messages was the only live acceptance here, so the wires
// customers actually reported broken — OpenAI chat completions, /v1/responses,
// and an opaque alias whose provider is not inferable from its name — were
// outside live evidence entirely. They are separate tests with separate model
// variables because a model is servable on the wires ITS provider declares and
// no others: one model cannot certify the matrix, and a single test that tried
// would fail for a reason that is not a defect.

const { test } = require('node:test');
const assert = require('node:assert/strict');

const { nRouter } = require('../dist/index');

const skip =
  process.env.NROUTER_LIVE === '1'
    ? false
    : 'billed: set NROUTER_LIVE=1, NROUTER_API_KEY and the per-wire model variables';

/**
 * The value of `name`, or a throw naming it. Reached only under
 * NROUTER_LIVE=1, where the caller has already asked for a billed run.
 */
function required(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(
      `${name} is required for a live probe. Set NROUTER_LIVE=1, NROUTER_API_KEY, ` +
        'and the per-wire model variables, then run `NROUTER_LIVE=1 npm test`.',
    );
  }
  return value;
}

/** A client pointed at the gateway under test. */
function liveClient() {
  return new nRouter({
    apiKey: process.env.NROUTER_API_KEY,
    baseURL: process.env.NROUTER_BASE_URL ?? 'http://127.0.0.1:4000/v1',
    maxRetries: 0,
  });
}

/**
 * Every response must carry `x-nr-request-id`: it is the only handle a customer
 * has at support, and the join key for the spend row this call just wrote.
 */
function assertCorrelatable(meta: any, wire: string) {
  assert.ok(meta.requestId, `${wire} answered without x-nr-request-id`);
}

/**
 * Unpriced is not free (Rule #28, gateway gate 3). `x-nr-request-cost` is
 * ABSENT when the model is unpriced — never a zero — so the honest states are
 * exactly two, and a reported cost of 0 is a defect on either.
 */
function assertHonestCost(meta: any, wire: string) {
  if (meta.costStatus === undefined || meta.costStatus === null) return;
  assert.ok(
    meta.costStatus === 'exact' || meta.costStatus === 'unpriced',
    `${wire} reported x-nr-cost-status ${meta.costStatus}`,
  );
  if (meta.costStatus === 'exact') {
    assert.ok(
      meta.cost !== null && meta.cost !== undefined && meta.cost > 0,
      `${wire} claimed an exact cost that was not above zero`,
    );
  } else {
    assert.equal(meta.cost, null, `${wire} priced an unpriced response`);
  }
}

/**
 * The `/v1` paths `GET /v1/models` says this alias can be called on.
 *
 * The gateway renders `nrouter_endpoints` from the provider's own endpoint
 * declaration, so this is the discovery answer an SDK is supposed to use
 * instead of guessing a wire from the model name.
 */
function advertisedEndpoints(catalogue: any, model: string): string[] {
  assert.ok(
    Array.isArray(catalogue.data) && catalogue.data.length > 0,
    'GET /v1/models returned an empty catalogue',
  );
  const entry = catalogue.data.find((item: any) => item.id === model);
  assert.ok(entry, `${model} is not in this key's catalogue`);
  assert.ok(
    Array.isArray(entry.nrouter_endpoints),
    `${model} carries no nrouter_endpoints`,
  );
  return entry.nrouter_endpoints;
}

/** A raw POST plus the `x-nr-*` metadata the gateway reported for it. */
async function post(client: any, path: string, body: Record<string, unknown>) {
  const res = await client.nr.request(path, body);
  assert.equal(res.status, 200, `${path} answered ${res.status}: ${res.text}`);
  return { body: JSON.parse(res.text), meta: client.nr.meta(res.headers) };
}

test('live Claude Messages request returns billing metadata', { skip }, async () => {
  const client = liveClient();
  const response = await client.nr.messages({
    model: process.env.NROUTER_LIVE_MESSAGES_MODEL ?? 'claude-haiku-4-5-20251001',
    max_tokens: 2,
    messages: [{ role: 'user', content: 'Reply OK' }],
  });

  assert.ok(Array.isArray(response.body.content));
  assertCorrelatable(response.meta, '/v1/messages');
  assert.equal(response.meta.costStatus, 'exact');
  assert.ok(response.meta.cost !== null && response.meta.cost > 0);
});

test('live OpenAI chat completions wire answers', { skip }, async () => {
  const client = liveClient();
  const { body, meta } = await post(client, '/chat/completions', {
    model: required('NROUTER_LIVE_CHAT_MODEL'),
    max_tokens: 2,
    messages: [{ role: 'user', content: 'Reply OK' }],
  });

  assert.ok(Array.isArray(body.choices), '/v1/chat/completions returned no choices array');
  assertCorrelatable(meta, '/v1/chat/completions');
  assertHonestCost(meta, '/v1/chat/completions');
});

test('live Responses wire answers', { skip }, async () => {
  const client = liveClient();
  const response = await client.nr.responses({
    model: required('NROUTER_LIVE_RESPONSES_MODEL'),
    input: 'Reply OK',
    max_output_tokens: 16,
  });

  assert.ok(
    response.body && Object.keys(response.body).length > 0,
    '/v1/responses returned an empty document',
  );
  assertCorrelatable(response.meta, '/v1/responses');
  assertHonestCost(response.meta, '/v1/responses');
});

// An alias whose provider a client cannot infer from the name — a Bedrock GLM
// or a Gemma alias — must still be callable, and the wire must come from
// discovery rather than from a guess.
//
// This is the one probe that proves the matrix is DERIVABLE: it reads the
// endpoints out of GET /v1/models and then calls the wire it was told about.
// An alias listed with an endpoint it cannot serve fails here.
test('live opaque alias is callable on the wire discovery advertises', { skip }, async () => {
  const client = liveClient();
  const model = required('NROUTER_LIVE_OPAQUE_MODEL');
  const endpoints = advertisedEndpoints(await client.nr.models.list(), model);
  assert.ok(
    endpoints.length > 0,
    `${model} is listed with an empty nrouter_endpoints — the catalogue advertises a name no wire serves`,
  );

  const path = endpoints.includes('/v1/chat/completions')
    ? '/chat/completions'
    : endpoints.includes('/v1/messages')
      ? '/messages'
      : null;
  assert.ok(path, `${model} advertises no text wire: ${JSON.stringify(endpoints)}`);

  const { meta } = await post(client, path as string, {
    model,
    max_tokens: 2,
    messages: [{ role: 'user', content: 'Reply OK' }],
  });
  assertCorrelatable(meta, 'the discovered text wire');
  assertHonestCost(meta, 'the discovered text wire');
});
