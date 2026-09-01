// Cases 10 and 11 — the billed-but-empty refusals, and the rule that a failure
// raised AFTER the headers arrived carries the response context.
//
// Ported from sdks/go/client_test.go: TestNonJSONSuccessIsRefusedNotSilentlyEmpty,
// TestUnparseableJSONSuccessIsRefused, TestPostHeaderFailuresKeepResponseContext,
// TestBareErrorEnvelopeStillTypes, TestRetryAfterHTTPDateReachesTheError.
//
// The split that matters, and it is a money property, not a style one:
//
//   * a 2xx that is NOT JSON is a real response the caller was billed for
//     (audio bytes, a video body, an SSE stream). It is PERMANENT — the wrong
//     method was called for the endpoint — so it must NOT be retryable. A
//     caller's generic `if (isRetryable(e)) retry` loop around it would repeat
//     a billed request forever.
//   * a 2xx whose JSON does not PARSE is a truncated billed response. The same
//     request can return an intact body next time, so it IS retryable.
//
// Getting either backwards costs real credits.

const { test } = require('node:test');
const assert = require('node:assert/strict');

const {
  chat,
  chatText,
  compare,
  compareError,
  COMPARE_ERROR_KEY,
  usesMessagesWire,
  toAnthropicMessagesRequest,
  toOpenAIChatCompletion,
} = require('../dist/chat');
const { nRouterError, isRetryable } = require('../dist/errors');

type RunnerResponse = {
  status: number;
  headers: Record<string, string>;
  text: string;
  contentType: string;
};

/** Stand-in for a binary body: bytes that are emphatically not JSON. */
const BINARY_BODY = 'ID3\x00\x00audio-frames';

/** A ChatRunner that answers with a canned response and records what it saw. */
function fakeRunner(response: Partial<RunnerResponse>) {
  const seen: { path?: string; body?: Record<string, unknown> } = {};
  return {
    seen,
    request(path: string, body: unknown) {
      seen.path = path;
      seen.body = body as Record<string, unknown>;
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

/** A ChatRunner that throws, standing in for a dropped socket or a DNS failure. */
function throwingRunner(err: unknown) {
  return {
    request() {
      return Promise.reject(err);
    },
  };
}

const OK_BODY = JSON.stringify({
  id: 'chatcmpl-1',
  choices: [{ message: { role: 'assistant', content: 'hello' } }],
});

/** Await a promise expected to reject, and hand back the rejection value. */
async function rejection(promise: Promise<unknown>): Promise<any> {
  try {
    await promise;
  } catch (err) {
    return err;
  }
  throw new Error('expected a rejection, got a resolved promise');
}

// ---------------------------------------------------------------------------
// The happy path, so the refusals below are known to be refusals of something.
// ---------------------------------------------------------------------------

test('a JSON 2xx resolves to the body paired with its metadata', async () => {
  // Deliberately an OPENAI-wire model. This case used to name a `claude-*`
  // model and assert `/chat/completions`, which pinned the defect rather than
  // the contract: the gateway declares `chat_completions: None` for Anthropic,
  // so that path 404s for every Claude id. The wire choice has its own cases
  // below; this one is about the runner owning the base URL.
  const runner = fakeRunner({
    text: OK_BODY,
    headers: {
      'x-nr-request-id': 'nrouter-ok',
      'x-nr-request-cost': '0.00347',
      'x-nr-cost-status': 'exact',
      'x-nr-model': 'gpt-4o-mini',
    },
  });
  const res = await chat(runner, { model: 'gpt-4o-mini', prompt: 'hi' });

  assert.equal(runner.seen.path, '/chat/completions', "the base URL is the runner's; the path is not");
  assert.equal(runner.seen.body?.model, 'gpt-4o-mini');
  assert.equal(res.meta.requestId, 'nrouter-ok');
  assert.equal(res.meta.cost, 0.00347);
  assert.equal(chatText(res), 'hello');
});

test('an UNPRICED completion reports cost null, never 0', async () => {
  const runner = fakeRunner({
    text: OK_BODY,
    headers: { 'x-nr-request-id': 'nrouter-ok', 'x-nr-cost-status': 'unpriced' },
  });
  const res = await chat(runner, { model: 'm', prompt: 'hi' });
  assert.equal(res.meta.cost, null);
  assert.notEqual(res.meta.cost, 0);
});

// ---------------------------------------------------------------------------
// Case 10 — the two billed-but-empty refusals.
// ---------------------------------------------------------------------------

test('a 2xx that is NOT JSON is refused, and the refusal is NOT retryable', async () => {
  const runner = fakeRunner({
    status: 200,
    contentType: 'audio/mpeg',
    text: BINARY_BODY,
    headers: { 'x-nr-request-id': 'nrouter-audio' },
  });
  const err = await rejection(chat(runner, { model: 'm', prompt: 'hi' }));

  assert.ok(err instanceof nRouterError, `expected an nRouterError, got ${err}`);
  assert.equal(
    isRetryable(err),
    false,
    'a retry loop around this would repeat a BILLED request forever'
  );
  assert.equal(err.kind, 'configuration', 'the wrong method was called; that is permanent');
  // The refusal must name the way out, or the caller has an error and no move.
  assert.match(err.message, /stream|bytes|binary|audio/i);
});

test('a 2xx with UNPARSEABLE JSON is refused and IS retryable', async () => {
  const runner = fakeRunner({
    status: 200,
    contentType: 'application/json',
    text: '{"truncated":',
    headers: { 'x-nr-request-id': 'nrouter-trunc' },
  });
  const err = await rejection(chat(runner, { model: 'm', prompt: 'hi' }));

  assert.ok(err instanceof nRouterError);
  assert.equal(err.kind, 'transport', 'the same request can return an intact body next time');
  assert.equal(isRetryable(err), true);
  assert.match(err.message, /billed/i, 'the refusal must say the request was billed');
});

test('a 2xx JSON body that is not an OBJECT is refused too', async () => {
  // `res.body.choices` on a `null` throws inside the caller instead of here,
  // where the request id still exists.
  for (const text of ['null', '"a string"', '[1,2,3]', '42']) {
    const runner = fakeRunner({ status: 200, contentType: 'application/json', text });
    const err = await rejection(chat(runner, { model: 'm', prompt: 'hi' }));
    assert.ok(err instanceof nRouterError, `body ${text} was not refused`);
    assert.equal(isRetryable(err), true);
  }
});

// ---------------------------------------------------------------------------
// Case 11 — status must not stay 0, and the request id must survive.
// ---------------------------------------------------------------------------

test('every post-header failure carries status AND requestId', async () => {
  const cases: [string, Partial<RunnerResponse>][] = [
    ['non json', { status: 200, contentType: 'audio/mpeg', text: BINARY_BODY }],
    ['unparseable json', { status: 200, contentType: 'application/json', text: '{"truncated":' }],
    ['non-object json', { status: 200, contentType: 'application/json', text: 'null' }],
    [
      'gateway refusal',
      {
        status: 402,
        contentType: 'application/json',
        text: JSON.stringify({ error: { code: 'insufficient_credits', message: 'top up' } }),
      },
    ],
  ];

  for (const [name, response] of cases) {
    const runner = fakeRunner({ ...response, headers: { 'x-nr-request-id': 'nrouter-ctx' } });
    const err = await rejection(chat(runner, { model: 'm', prompt: 'hi' }));
    assert.ok(err instanceof nRouterError, `${name}: not an nRouterError`);
    assert.equal(
      err.status,
      response.status,
      `${name}: status 0 means "never reached the gateway"; this response DID arrive`
    );
    assert.equal(
      err.requestId,
      'nrouter-ctx',
      `${name}: the only correlation path to the spend row was lost`
    );
  }
});

test('a 429 carries limit-source and Retry-After onto the error', async () => {
  const runner = fakeRunner({
    status: 429,
    contentType: 'application/json',
    text: JSON.stringify({ error: { code: 'rate_limit_exceeded', message: 'slow' } }),
    headers: {
      'x-nr-request-id': 'nrouter-429',
      'x-nr-limit-source': 'budget',
      'retry-after': '30',
    },
  });
  const err = await rejection(chat(runner, { model: 'm', prompt: 'hi' }));
  assert.equal(err.name, 'nRouterRateLimitError');
  assert.equal(err.limitSource, 'budget', 'sending a customer to raise the wrong limit is gate 7');
  assert.equal(err.retryAfter, 30);
  assert.equal(isRetryable(err), true);
});

test('an HTTP-date Retry-After reaches the error, not just delta-seconds', async () => {
  const runner = fakeRunner({
    status: 429,
    contentType: 'application/json',
    text: JSON.stringify({ error: { code: 'rate_limit_exceeded', message: 'slow' } }),
    headers: { 'retry-after': new Date(Date.now() + 60000).toUTCString() },
  });
  const err = await rejection(chat(runner, { model: 'm', prompt: 'hi' }));
  assert.notEqual(err.retryAfter, null, 'a date-form Retry-After must not be silently dropped');
  assert.ok(err.retryAfter >= 58 && err.retryAfter <= 60, `retryAfter was ${err.retryAfter}`);
});

// ---------------------------------------------------------------------------
// The gateway's MAIN error path sends NO code.
// ---------------------------------------------------------------------------

test('a codeless {"error":{"type","message"}} envelope still classifies', async () => {
  const runner = fakeRunner({
    status: 400,
    contentType: 'application/json',
    text: JSON.stringify({
      error: { type: 'gateway_error', message: 'Guardrail rule denied this' },
    }),
  });
  const err = await rejection(chat(runner, { model: 'm', prompt: 'hi' }));
  assert.equal(
    err.name,
    'nRouterGuardrailBlockedError',
    'classifying every 400 as a request error makes guardrail_blocked unreachable'
  );
});

test('a BARE envelope (a proxy reshaped it) still types', async () => {
  const runner = fakeRunner({
    status: 402,
    contentType: 'application/json',
    text: JSON.stringify({ code: 'insufficient_credits', message: 'top up' }),
  });
  const err = await rejection(chat(runner, { model: 'm', prompt: 'hi' }));
  assert.equal(err.name, 'nRouterCreditError');
});

test('a non-JSON error body still classifies on status alone', async () => {
  const runner = fakeRunner({
    status: 502,
    contentType: 'text/html',
    text: '<html>502 Bad Gateway</html>',
  });
  const err = await rejection(chat(runner, { model: 'm', prompt: 'hi' }));
  assert.ok(err instanceof nRouterError);
  assert.equal(isRetryable(err), true, 'a proxy 502 is transient');
});

test('a throwing runner becomes a transport error with status 0', async () => {
  const err = await rejection(
    chat(throwingRunner(new Error('ECONNRESET')), { model: 'm', prompt: 'hi' })
  );
  assert.ok(err instanceof nRouterError);
  assert.equal(err.kind, 'transport');
  // `null` is this SDK's "the request never reached the gateway" sentinel
  // (errors.ts: "Null/absent when the request never reached the gateway"),
  // where the Go port uses 0. The property under test is the same one either
  // way, and its OTHER half — a failure raised after the headers arrived must
  // NOT keep this sentinel — is pinned above.
  assert.equal(err.status, null, 'no HTTP exchange happened');
  assert.equal(isRetryable(err), true);
});

test('an ABORT out of the runner is never retryable', async () => {
  const abort = new Error('aborted');
  abort.name = 'AbortError';
  const err = await rejection(chat(throwingRunner(abort), { model: 'm', prompt: 'hi' }));
  assert.ok(err instanceof nRouterError);
  assert.equal(isRetryable(err), false, 'the caller asked to stop');
});

test('chat() refuses stream: true before a byte leaves the process', async () => {
  const runner = fakeRunner({});
  const err = await rejection(chat(runner, { model: 'm', prompt: 'hi', extra: { stream: true } }));
  assert.ok(err instanceof nRouterError);
  assert.equal(err.kind, 'configuration');
  assert.equal(runner.seen.path, undefined, 'the request must be refused BEFORE it is sent');
});

test('no thrown chat error carries the API key', async () => {
  const secret = 'sk-nrouter-live-abcdef0123456789';
  const runner = fakeRunner({
    status: 401,
    contentType: 'application/json',
    text: JSON.stringify({
      error: { code: 'invalid_api_key', message: `key ${secret} refused` },
    }),
  });
  const err = await rejection(chat(runner, { model: 'm', prompt: 'hi' }));
  for (const rendered of [err.message, String(err), JSON.stringify(err), err.stack ?? '']) {
    assert.equal(rendered.includes(secret), false, `a key leaked: ${rendered.slice(0, 160)}`);
  }
});

// ---------------------------------------------------------------------------
// chatText and compare
// ---------------------------------------------------------------------------

test('chatText returns "" rather than throwing away a response the caller paid for', () => {
  const { EMPTY_META } = require('../dist/meta');
  assert.equal(chatText({ body: {}, meta: EMPTY_META }), '');
  assert.equal(chatText({ body: { choices: [] }, meta: EMPTY_META }), '');
  assert.equal(chatText({ body: { choices: [{ message: { content: null } }] }, meta: EMPTY_META }), '');
  // Content PARTS, which several providers answer with.
  assert.equal(
    chatText({
      body: { choices: [{ message: { content: [{ text: 'a' }, { text: 'b' }] } }] },
      meta: EMPTY_META,
    }),
    'ab'
  );
});

test('compare returns results in MODEL order, never completion order', async () => {
  const runner = {
    request(_path: string, body: Record<string, unknown>) {
      const model = String(body.model);
      const delay = model === 'slow' ? 20 : 0;
      return new Promise((resolve) =>
        setTimeout(
          () =>
            resolve({
              status: 200,
              headers: { 'x-nr-model': model },
              contentType: 'application/json',
              text: JSON.stringify({ choices: [{ message: { content: model } }] }),
            }),
          delay
        )
      );
    },
  };
  const results = await compare(runner, { prompt: 'hi', model: 'placeholder' }, ['slow', 'fast']);
  assert.equal(results.length, 2);
  assert.equal(chatText(results[0]), 'slow', 'models[i] and results[i] must describe each other');
  assert.equal(chatText(results[1]), 'fast');
});

test('a failed compare arm does not discard the sibling answers that were billed', async () => {
  const runner = {
    request(_path: string, body: Record<string, unknown>) {
      if (body.model === 'typo') {
        return Promise.resolve({
          status: 404,
          headers: { 'x-nr-request-id': 'nrouter-404' },
          contentType: 'application/json',
          text: JSON.stringify({
            error: { code: 'model_not_found', message: 'model typo not found' },
          }),
        });
      }
      return Promise.resolve({
        status: 200,
        headers: {},
        contentType: 'application/json',
        text: JSON.stringify({ choices: [{ message: { content: 'ok' } }] }),
      });
    },
  };
  const results = await compare(runner, { prompt: 'hi', model: 'x' }, ['good', 'typo']);

  assert.equal(chatText(results[0]), 'ok', 'a paid answer must survive a sibling failure');
  const failure = compareError(results[1]);
  assert.ok(failure instanceof nRouterError, 'the failed arm must park a typed error, not vanish');
  assert.equal(failure.name, 'nRouterNotFoundError');
  assert.equal(compareError(results[0]), null);
  assert.ok(COMPARE_ERROR_KEY, 'the sentinel key is exported so no caller string-matches it');
});

// ---------------------------------------------------------------------------
// THE ANTHROPIC WIRE — the P0 that made every Claude and Bedrock model
// unreachable from `nr.chat()`.
//
// MEASURED, in the gateway's own source: Anthropic declares
// `chat_completions: None`
// (`nrouter-rust-gateway/src/sdk/providers/anthropic/transformation.rs:55-57`)
// and so does Bedrock (`bedrock/transformation.rs`, the `endpoints` impl —
// anchored by name, the line number has already drifted), so `transform.rs`
// answers a 404 UnknownModel reading "is not available on
// /v1/chat/completions". This SDK sent every model to that one path. The
// package advertises `claude` and `bedrock` in its own keywords, and not one
// of those models could be called.
//
// The hosted playground already solved it and is the reference
// (`nrouter-app/src/app/api/nrouter-proxy/chat/route.ts:298-336` +
// `src/lib/nrouter-proxy/anthropic-translation.ts`). Picking the PATH is only
// half the job: that route picked `/v1/messages` for a while and still sent
// the OpenAI request shape at it, which produced — its comment records the
// measurement — "a 200 in ~14s that rendered an EMPTY BOX while the tokens
// were billed". A silent success delivering no product, for real money.
// ---------------------------------------------------------------------------

/** A buffered Anthropic Messages response, exactly as `/v1/messages` answers. */
const ANTHROPIC_BODY = JSON.stringify({
  id: 'msg_01ABC',
  type: 'message',
  role: 'assistant',
  model: 'claude-sonnet-4-5',
  content: [{ type: 'text', text: 'hello from claude' }],
  stop_reason: 'end_turn',
  usage: { input_tokens: 11, cache_read_input_tokens: 4, output_tokens: 3 },
});

test('the wire predicate covers every id shape the catalogue actually serves', () => {
  for (const model of [
    'claude-sonnet-4-5',
    'claude-3-5-haiku-20241022',
    'anthropic/claude-sonnet-4-5-20250929',
    'us.anthropic.claude-opus-4-1-v1:0',
    'CLAUDE-SONNET-4-5',
  ]) {
    assert.equal(usesMessagesWire(model), true, `${model} must take /messages`);
  }
  for (const model of ['gpt-4o-mini', 'o3', 'gemini-2.5-pro', 'qwen-max', '']) {
    assert.equal(usesMessagesWire(model), false, `${model} must stay on /chat/completions`);
  }
  // A private alias that hides the family name still routes correctly when the
  // caller supplied the provider attribution it already passes to the sampling
  // policy — but ONLY for an attribution that implies the wire on its own.
  //
  // `anthropic` does: every model Anthropic serves direct is on /v1/messages.
  // `bedrock` does NOT, and that is the whole of BEDROCK_PUBLISHED_ALIASES
  // below: Bedrock is a MULTI-FAMILY catalogue whose Anthropic half is the only
  // half this gateway serves on that wire.
  assert.equal(usesMessagesWire('house-model-v2'), false);
  assert.equal(usesMessagesWire('house-model-v2', 'anthropic'), true);
  assert.equal(usesMessagesWire('house-model-v2', 'bedrock'), false);
});

// ---------------------------------------------------------------------------
// BEDROCK IS NOT ONE FAMILY, AND THE WIRE PREDICATE MUST NOT PRETEND IT IS
//
// SDK-GW-AUDIT-20260831-001..046. Measured against the LIVE served set on
// 2026-08-31 (`GET /v1/models`, 209 rows): 46 rows carry a `bedrock/` model and
// **not one of them is in the Anthropic family** — Nova, Llama, Qwen, Mistral,
// DeepSeek, Gemma, GLM, MiniMax, Nemotron, Kimi, gpt-oss.
//
// The gateway serves the Anthropic family ONLY on Bedrock:
// `require_anthropic_family` in
// `nrouter-rust-gateway/src/sdk/providers/bedrock/transformation.rs` refuses
// everything else on `/v1/messages`, because that route forwards an Anthropic
// Messages body and every other Bedrock family takes a different `InvokeModel`
// schema.
//
// So a `bedrock` ATTRIBUTION forcing the Anthropic wire was wrong for all 46.
// It also failed WORSE than the alternative: `toAnthropicMessagesRequest` runs
// first, so the body reaching the gateway had already had its OpenAI-only
// fields translated away before the refusal — a caller reading the 400 could
// not tell whether their request had survived.
//
// Both wires still fail for these ids today; that half is the gateway's and the
// catalogue's (a model that cannot be served must be ABSENT, never
// served-but-broken). What this SDK owes them is the honest wire and an
// unmangled body, so the refusal they read is about the model and not about a
// translation we chose.
// ---------------------------------------------------------------------------

/** `[public alias, upstream Bedrock model id]`, from the 2026-08-31 served set. */
const BEDROCK_PUBLISHED_ALIASES: ReadonlyArray<readonly [string, string]> = [
  ['devstral-2-123b', 'mistral.devstral-2-123b'],
  ['gemma-3-12b-it', 'google.gemma-3-12b-it'],
  ['gemma-3-27b-it', 'google.gemma-3-27b-it'],
  ['gemma-3-4b-it', 'google.gemma-3-4b-it'],
  ['glm-4.7', 'zai.glm-4.7'],
  ['glm-4.7-flash', 'zai.glm-4.7-flash'],
  ['glm-5', 'zai.glm-5'],
  ['gpt-oss-120b-1', 'openai.gpt-oss-120b-1:0'],
  ['gpt-oss-20b-1', 'openai.gpt-oss-20b-1:0'],
  ['gpt-oss-safeguard-120b', 'openai.gpt-oss-safeguard-120b'],
  ['gpt-oss-safeguard-20b', 'openai.gpt-oss-safeguard-20b'],
  ['kimi-k2-thinking', 'moonshot.kimi-k2-thinking'],
  ['kimi-k2.5', 'moonshotai.kimi-k2.5'],
  ['llama3-1-70b-instruct', 'us.meta.llama3-1-70b-instruct-v1:0'],
  ['llama3-1-8b-instruct', 'us.meta.llama3-1-8b-instruct-v1:0'],
  ['llama3-3-70b-instruct', 'meta.llama3-3-70b-instruct-v1:0'],
  ['llama4-maverick-17b-instruct', 'us.meta.llama4-maverick-17b-instruct-v1:0'],
  ['llama4-scout-17b-instruct', 'us.meta.llama4-scout-17b-instruct-v1:0'],
  ['magistral-small-2509', 'mistral.magistral-small-2509'],
  ['minimax-m2', 'minimax.minimax-m2'],
  ['minimax-m2.1', 'minimax.minimax-m2.1'],
  ['minimax-m2.5', 'minimax.minimax-m2.5'],
  ['ministral-3-14b-instruct', 'mistral.ministral-3-14b-instruct'],
  ['ministral-3-3b-instruct', 'mistral.ministral-3-3b-instruct'],
  ['ministral-3-8b-instruct', 'mistral.ministral-3-8b-instruct'],
  ['mistral-large-3-675b-instruct', 'mistral.mistral-large-3-675b-instruct'],
  ['nemotron-nano-12b-v2', 'nvidia.nemotron-nano-12b-v2'],
  ['nemotron-nano-3-30b', 'nvidia.nemotron-nano-3-30b'],
  ['nemotron-nano-9b-v2', 'nvidia.nemotron-nano-9b-v2'],
  ['nemotron-super-3-120b', 'nvidia.nemotron-super-3-120b'],
  ['nova-2-lite', 'us.amazon.nova-2-lite-v1:0'],
  ['nova-lite', 'amazon.nova-lite-v1:0'],
  ['nova-micro', 'us.amazon.nova-micro-v1:0'],
  ['nova-pro', 'us.amazon.nova-pro-v1:0'],
  ['pixtral-large-2502', 'us.mistral.pixtral-large-2502-v1:0'],
  ['qwen3-235b-a22b-2507', 'qwen.qwen3-235b-a22b-2507-v1:0'],
  ['qwen3-32b', 'qwen.qwen3-32b-v1:0'],
  ['qwen3-coder-30b-a3b', 'qwen.qwen3-coder-30b-a3b-v1:0'],
  ['qwen3-coder-480b-a35b', 'qwen.qwen3-coder-480b-a35b-v1:0'],
  ['qwen3-next-80b-a3b', 'qwen.qwen3-next-80b-a3b'],
  ['qwen3-vl-235b-a22b', 'qwen.qwen3-vl-235b-a22b'],
  ['r1', 'us.deepseek.r1-v1:0'],
  ['v3', 'deepseek.v3-v1:0'],
  ['v3.2', 'deepseek.v3.2'],
  ['voxtral-mini-3b-2507', 'mistral.voxtral-mini-3b-2507'],
  ['voxtral-small-24b-2507', 'mistral.voxtral-small-24b-2507'],
];

test('every published Bedrock alias stays OFF the Anthropic Messages wire', () => {
  assert.equal(
    BEDROCK_PUBLISHED_ALIASES.length,
    46,
    'the published bedrock alias table changed size without its count',
  );
  for (const [alias, upstream] of BEDROCK_PUBLISHED_ALIASES) {
    for (const id of [alias, upstream, `bedrock/${upstream}`]) {
      assert.equal(
        usesMessagesWire(id),
        false,
        `${id} is not Anthropic-family and must not be translated onto /messages`,
      );
      // The attribution the public catalogue itself reports for these rows.
      assert.equal(
        usesMessagesWire(id, 'AWS Bedrock'),
        false,
        `${id}: a bedrock attribution must not force the Anthropic wire`,
      );
    }
  }
});

test('a Bedrock ANTHROPIC-family id still takes the Messages wire', () => {
  // The mutation guard for the narrowing above: a predicate stubbed to `false`
  // would pass every assertion in the previous test while making every Claude
  // on Bedrock uncallable — the exact P0 this whole section was written for.
  for (const id of [
    'anthropic.claude-sonnet-4-5-20250929-v1:0',
    'us.anthropic.claude-opus-4-1-v1:0',
    'bedrock/us.anthropic.claude-3-5-haiku-20241022-v1:0',
  ]) {
    assert.equal(usesMessagesWire(id), true, `${id} is Anthropic-family`);
    assert.equal(usesMessagesWire(id, 'AWS Bedrock'), true, `${id} is Anthropic-family`);
  }
});

test('a published Bedrock alias is sent UNTRANSLATED to /chat/completions', async () => {
  const runner = fakeRunner({ text: OK_BODY });
  await chat(runner, { model: 'nova-pro', prompt: 'hi', modelProvider: 'AWS Bedrock' });
  assert.equal(runner.seen.path, '/chat/completions');
  // `model` survives, which the Anthropic translator would have kept too — but
  // `max_tokens` must NOT have been injected, because that injection is the
  // Anthropic wire's requirement and its presence is how you tell the body was
  // rewritten for a wire this model does not take.
  assert.equal(runner.seen.body?.model, 'nova-pro');
  assert.equal(runner.seen.body?.max_tokens, undefined);
});

test('a Claude model is sent to /messages, not to the path that 404s it', async () => {
  const runner = fakeRunner({ text: ANTHROPIC_BODY });
  await chat(runner, { model: 'claude-sonnet-4-5', prompt: 'hi' });
  assert.equal(runner.seen.path, '/messages');
});

test('an OpenAI model stays on /chat/completions', async () => {
  const runner = fakeRunner({ text: OK_BODY });
  await chat(runner, { model: 'gpt-4o-mini', prompt: 'hi' });
  assert.equal(runner.seen.path, '/chat/completions');
});

test('the /messages body is TRANSLATED, not the OpenAI shape at a new path', async () => {
  const runner = fakeRunner({ text: ANTHROPIC_BODY });
  await chat(runner, {
    model: 'claude-sonnet-4-5',
    systemPrompt: 'be brief',
    prompt: 'hi',
  });
  const body = runner.seen.body as Record<string, any>;

  // 1. `system` comes OUT of `messages`. Anthropic rejects role:"system" there.
  assert.equal(body.system, 'be brief');
  assert.deepEqual(
    body.messages.map((m: any) => m.role),
    ['user'],
    'no system turn may remain inside messages',
  );
  // 2. `max_tokens` is REQUIRED on this wire; absent is a hard 400.
  assert.equal(body.max_tokens, 1024);
  // 3. Nothing OpenAI-only survives.
  assert.equal(body.stream_options, undefined);
  assert.equal(body.n, undefined);
});

test('a caller max_tokens is never overwritten by the Anthropic default', async () => {
  const runner = fakeRunner({ text: ANTHROPIC_BODY });
  await chat(runner, { model: 'claude-sonnet-4-5', prompt: 'hi', maxTokens: 64 });
  assert.equal((runner.seen.body as any).max_tokens, 64);
});

test('temperature is clamped to Anthropic\'s ceiling rather than 400ing', async () => {
  const runner = fakeRunner({ text: ANTHROPIC_BODY });
  await chat(runner, {
    model: 'claude-sonnet-4-5',
    prompt: 'hi',
    advancedSampling: true,
    temperature: 1.8,
  });
  // OpenAI's range is 0–2 and Anthropic's is 0–1; 1.8 is a hard 400 upstream.
  assert.equal((runner.seen.body as any).temperature, 1);
});

test('n > 1 on the Anthropic wire is REFUSED, and nothing is sent', async () => {
  // Anthropic returns exactly one message and has no `n`. Dropping the field
  // answers an n:3 request with one choice and calls it success — the same
  // fake-success class as the empty box, but here it also bills the call.
  // Refusing BEFORE the runner is the only version that costs nothing.
  const runner = fakeRunner({ text: ANTHROPIC_BODY });
  const err = await rejection(
    chat(runner, { model: 'claude-sonnet-4-5', prompt: 'hi', extra: { n: 3 } }),
  );
  assert.equal(err.name, 'nRouterConfigurationError');
  assert.equal(isRetryable(err), false, 'a permanent request defect must not be retried');
  assert.equal(runner.seen.path, undefined, 'the refusal must precede the billed call');
});

test('an Anthropic answer is translated, so chatText is not the EMPTY BOX', async () => {
  const runner = fakeRunner({
    text: ANTHROPIC_BODY,
    headers: { 'x-nr-request-id': 'nrouter-anthropic' },
  });
  const res = await chat(runner, { model: 'claude-sonnet-4-5', prompt: 'hi' });

  assert.equal(chatText(res), 'hello from claude');
  assert.equal((res.body as any).object, 'chat.completion');
  assert.equal((res.body as any).choices[0].message.role, 'assistant');
  assert.equal((res.body as any).choices[0].finish_reason, 'stop');
  assert.equal(res.meta.requestId, 'nrouter-anthropic', 'metadata survives translation');
});

test('usage is summed from the counts Anthropic reported, and never invented', () => {
  const translated: any = toOpenAIChatCompletion(JSON.parse(ANTHROPIC_BODY));
  // input + cache_read are both prompt tokens the customer paid for.
  assert.equal(translated.usage.prompt_tokens, 15);
  assert.equal(translated.usage.completion_tokens, 3);
  assert.equal(translated.usage.total_tokens, 18);

  // Nothing countable → NO usage key at all. A zero-filled block reads as a
  // free request, which no enabled model is (Rule #28, gateway gate 3).
  //
  // BOTH shapes, because they fail at different guards and an earlier version
  // of this case only exercised the first: a usage block that is ABSENT, and
  // one that is PRESENT but holds no number we can read. The second is the one
  // that matters — the provider answered, we could not parse its counts, and
  // that is precisely when a confident `0` gets written.
  for (const doc of [
    { type: 'message', content: [{ type: 'text', text: 'x' }] },
    { type: 'message', content: [{ type: 'text', text: 'x' }], usage: {} },
    {
      type: 'message',
      content: [{ type: 'text', text: 'x' }],
      usage: { input_tokens: null, output_tokens: 'many' },
    },
  ]) {
    const translated: any = toOpenAIChatCompletion(doc);
    assert.equal('usage' in translated, false, `${JSON.stringify(doc)} must carry no usage`);
    assert.notEqual(translated.usage, 0);
  }

  // A count of literally zero output tokens IS countable and must survive —
  // omitting it would be the mirror defect, hiding a real measurement.
  const zeroOutput: any = toOpenAIChatCompletion({
    type: 'message',
    content: [],
    usage: { input_tokens: 7, output_tokens: 0 },
  });
  assert.equal(zeroOutput.usage.completion_tokens, 0);
  assert.equal(zeroOutput.usage.prompt_tokens, 7);
});

test('stop_reason max_tokens becomes finish_reason length, not a silent stop', () => {
  const truncated: any = toOpenAIChatCompletion({
    type: 'message',
    content: [{ type: 'text', text: 'half an ans' }],
    stop_reason: 'max_tokens',
  });
  // `length` is the only thing that distinguishes a truncated answer from a
  // short one; reporting `stop` hides a cut-off reply the caller paid for.
  assert.equal(truncated.choices[0].finish_reason, 'length');
});

test('an OpenAI-shaped document passes through the translator untouched', () => {
  const openai = { id: 'chatcmpl-1', choices: [{ message: { content: 'hi' } }] };
  assert.equal(toOpenAIChatCompletion(openai), openai);
});

test('tools are translated, never dropped into a normal-looking answer', async () => {
  const runner = fakeRunner({
    text: JSON.stringify({
      type: 'message',
      content: [
        { type: 'tool_use', id: 'toolu_1', name: 'get_weather', input: { city: 'Paris' } },
      ],
      stop_reason: 'tool_use',
    }),
  });
  const res = await chat(runner, {
    model: 'claude-sonnet-4-5',
    prompt: 'weather?',
    extra: {
      tools: [
        {
          type: 'function',
          function: {
            name: 'get_weather',
            description: 'look it up',
            parameters: { type: 'object', properties: { city: { type: 'string' } } },
          },
        },
      ],
      tool_choice: 'required',
    },
  });

  const sent = runner.seen.body as any;
  assert.equal(sent.tools[0].name, 'get_weather');
  assert.deepEqual(sent.tools[0].input_schema.properties, { city: { type: 'string' } });
  assert.deepEqual(sent.tool_choice, { type: 'any' });
  assert.equal(sent.functions, undefined);

  const call = (res.body as any).choices[0].message.tool_calls[0];
  assert.equal(call.function.name, 'get_weather');
  assert.equal(call.function.arguments, '{"city":"Paris"}');
  assert.equal((res.body as any).choices[0].message.content, null);
  assert.equal((res.body as any).choices[0].finish_reason, 'tool_calls');
});

test('an OpenAI tool result replays as an Anthropic tool_result turn', () => {
  const { body } = toAnthropicMessagesRequest({
    model: 'claude-sonnet-4-5',
    messages: [
      { role: 'user', content: 'weather?' },
      {
        role: 'assistant',
        content: '',
        tool_calls: [
          { id: 'toolu_1', type: 'function', function: { name: 'w', arguments: '{"c":"P"}' } },
        ],
      },
      { role: 'tool', tool_call_id: 'toolu_1', content: '18C' },
    ],
  }) as any;

  // Anthropic has no `tool` role; a dropped result makes the model answer as
  // if the tool never ran.
  assert.equal(body.messages[2].role, 'user');
  assert.equal(body.messages[2].content[0].type, 'tool_result');
  assert.equal(body.messages[2].content[0].tool_use_id, 'toolu_1');
  // An empty assistant `content` contributes NO text block, so the tool_use is
  // the first block — several providers reject a zero-length text block.
  assert.equal(body.messages[1].content[0].type, 'tool_use');
  assert.deepEqual(body.messages[1].content[0].input, { c: 'P' });
});

test('a data: image URI is split into an Anthropic base64 source', () => {
  const { body } = toAnthropicMessagesRequest({
    model: 'claude-sonnet-4-5',
    messages: [
      {
        role: 'user',
        content: [
          { type: 'text', text: 'what is this' },
          { type: 'image_url', image_url: { url: 'data:image/png;base64,AAAA' } },
        ],
      },
    ],
  }) as any;
  // Handing the whole data URI over as a URL is a hard 400 upstream.
  assert.deepEqual(body.messages[0].content[1], {
    type: 'image',
    source: { type: 'base64', media_type: 'image/png', data: 'AAAA' },
  });
});
