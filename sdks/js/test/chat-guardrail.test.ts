// SDK-GW-AUDIT-20260831-099 / -095 — the guardrail-block wire contract.
//
// DERIVED FROM THE GATEWAY, not from the SDK's own comments. What this pins,
// and where each fact comes from in nrouter-rust-gateway:
//
//   * `PostCallVerdict::client_status` (src/http/postcall.rs:224-231) turns a
//     BLOCKED verdict over a SUCCESSFUL upstream response into 400, and leaves
//     any other upstream status alone. Every buffered handler applies it before
//     building the response (chat_completions.rs:545, messages.rs:514,
//     responses.rs:595, completions.rs:585, multimodal.rs:1528, audio.rs:1406,
//     response_cache.rs:407), so a post-call block NEVER reaches a caller as a
//     2xx on a buffered route.
//   * `blocked_body()` (src/http/postcall.rs:234-241) is
//     {"error":{"type":"guardrail_blocked","message":"the response was withheld
//     by an output guardrail"}} — note `type`, and note there is no `code`.
//   * A PRE-call block is a different document: `GatewayError::into_response`
//     (src/errors.rs:445-450) renders EVERY variant with the literal
//     `"type": "gateway_error"`, so the 400 for `GuardrailBlocked`
//     (src/errors.rs:264) carries `gateway_error` and the message
//     "request blocked by a guardrail: ..." (src/errors.rs:127).
//
// The consequence, and the reason both arms below are separate tests: a client
// keying on `error.code` sees NOTHING on either path, and a client keying only
// on `error.type` misses the pre-call half. That is the exact gap the audit
// findings describe — a policy refusal that reads as a generic bad request.

const { test } = require('node:test');
const assert = require('node:assert/strict');

const { chat } = require('../dist/chat');
const { nRouterError } = require('../dist/errors');

type RunnerResponse = {
  status: number;
  headers: Record<string, string>;
  text: string;
  contentType: string;
};

function fakeRunner(response: Partial<RunnerResponse>) {
  return {
    request() {
      return Promise.resolve({
        status: 200,
        headers: {},
        text: '{}',
        contentType: 'application/json',
        ...response,
      });
    },
  };
}

async function rejection(promise: Promise<unknown>): Promise<any> {
  try {
    await promise;
  } catch (err) {
    return err;
  }
  throw new Error('expected a rejection, got a resolved value');
}

// ---------------------------------------------------------------------------
// POST-CALL: the withheld response, as the gateway actually sends it today.
// ---------------------------------------------------------------------------

test('a post-call guardrail block (400 + type guardrail_blocked) is typed, not generic', async () => {
  const runner = fakeRunner({
    status: 400,
    contentType: 'application/json',
    headers: { 'x-nr-request-id': 'req_gw_1' },
    // Byte-for-byte the gateway's `blocked_body()`.
    text: JSON.stringify({
      error: {
        type: 'guardrail_blocked',
        message: 'the response was withheld by an output guardrail',
      },
    }),
  });
  const err = await rejection(chat(runner, { model: 'm', prompt: 'hi' }));

  assert.ok(err instanceof nRouterError);
  assert.equal(
    err.name,
    'nRouterGuardrailBlockedError',
    'the gateway ships the stable code in `type`; reading only `code` leaves this a plain 400'
  );
  assert.equal(err.code, 'guardrail_blocked', 'the stable code must survive onto the error');
  assert.equal(err.status, 400);
  assert.equal(
    err.requestId,
    'req_gw_1',
    'x-nr-request-id is the only join key between the refusal and its request record'
  );
});

// ---------------------------------------------------------------------------
// PRE-CALL: the SAME customer-visible event, a DIFFERENT document.
// ---------------------------------------------------------------------------

test('a pre-call guardrail block (400 + type gateway_error) is still typed as a guardrail block', async () => {
  const runner = fakeRunner({
    status: 400,
    contentType: 'application/json',
    headers: { 'x-nr-request-id': 'req_gw_2' },
    // `GatewayError::into_response` stamps `gateway_error` on EVERY variant.
    text: JSON.stringify({
      error: { type: 'gateway_error', message: 'request blocked by a guardrail: pii' },
    }),
  });
  const err = await rejection(chat(runner, { model: 'm', prompt: 'hi' }));

  assert.equal(
    err.name,
    'nRouterGuardrailBlockedError',
    'a pre-call block carries no distinguishing type, so the message is the only discriminator'
  );
  assert.equal(err.status, 400);
  assert.equal(err.requestId, 'req_gw_2');
});

// ---------------------------------------------------------------------------
// A 400 that is NOT a guardrail must not be swallowed into the guardrail class.
// ---------------------------------------------------------------------------

test('an ordinary 400 is NOT reported as a guardrail block', async () => {
  const runner = fakeRunner({
    status: 400,
    contentType: 'application/json',
    text: JSON.stringify({
      error: { type: 'gateway_error', message: 'unsupported parameter: frequency_penalty' },
    }),
  });
  const err = await rejection(chat(runner, { model: 'm', prompt: 'hi' }));
  assert.equal(
    err.name,
    'nRouterRequestError',
    'widening the guardrail arm to every 400 sends a caller to the wrong dashboard page'
  );
});

// ---------------------------------------------------------------------------
// The 2xx envelope guard, re-justified. Not the gateway's guardrail path any
// more — a provider-origin document the gateway passes through UNTOUCHED on
// `PostCallVerdict::Clean` (src/http/postcall.rs:187-192).
// ---------------------------------------------------------------------------

test('a 2xx carrying an error envelope is refused, not handed back as an empty completion', async () => {
  const runner = fakeRunner({
    status: 200,
    contentType: 'application/json',
    headers: { 'x-nr-request-id': 'req_gw_3' },
    text: JSON.stringify({ error: { type: 'provider_error', message: 'upstream refused' } }),
  });
  const err = await rejection(chat(runner, { model: 'm', prompt: 'hi' }));

  assert.ok(err instanceof nRouterError);
  assert.equal(err.status, 200, 'the response context must survive onto the error');
  assert.equal(err.requestId, 'req_gw_3');
  assert.match(err.message, /upstream refused/);
});

test('a real completion that merely mentions an error is NOT refused', async () => {
  const runner = fakeRunner({
    status: 200,
    contentType: 'application/json',
    text: JSON.stringify({
      id: 'cmpl_1',
      object: 'chat.completion',
      choices: [{ index: 0, message: { role: 'assistant', content: 'the error was a typo' } }],
      error: { message: 'not a refusal' },
    }),
  });
  const out = await chat(runner, { model: 'm', prompt: 'hi' });
  assert.equal(
    out.body.choices[0].message.content,
    'the error was a typo',
    'the 2xx envelope guard must not swallow a completion-shaped reply'
  );
});
