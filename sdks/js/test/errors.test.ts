// The error contract: the nine spec codes, the codeless dispatch the gateway
// actually uses, retryability, Retry-After, and the rule that no thrown error
// may ever carry the API key.
//
// Ported from sdks/go/client_test.go — TestEachGatewayCodeMapsToItsKind,
// TestCodelessResponsesAreClassifiedByStatusAndMessage,
// TestUnknownCodeIsNeverReclassified, TestOnlyTransientConditionsAreRetryable,
// TestCodeless502IsATransientServiceFailure, TestOversized502IsNotRetryable,
// TestContextCancellationIsPreservedAndNotRetryable,
// TestParseRetryAfterAcceptsBothRFC9110Forms.
//
// The nine-code table is read FROM THE SPEC FILE, never retyped here: a
// hand-copied table proves the SDK agrees with the test author, not with the
// gateway (Rule #14).

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const errors = require('../dist/errors');
const {
  nRouterError,
  classifyError,
  classifyErrorClass,
  createError,
  isRetryable,
  parseErrorBody,
  parseRetryAfter,
  computeJitteredBackoff,
  ERROR_CLASS_BY_CODE,
  ERROR_STATUS_BY_CODE,
} = errors;

/** spec/nrouter-sdk-spec.json — the Rule #14 source of truth, four levels up. */
const SPEC_PATH = path.resolve(__dirname, '..', '..', '..', 'spec', 'nrouter-sdk-spec.json');
const SPEC = JSON.parse(fs.readFileSync(SPEC_PATH, 'utf8')) as {
  errors: Record<string, { http: number; class: string; description: string }>;
};

// ---------------------------------------------------------------------------
// Case 3 — the nine spec codes, asserted against the spec file.
// ---------------------------------------------------------------------------

test('the spec still declares exactly nine error codes', () => {
  // If the gateway grows a tenth, this fails and every table below is revisited
  // deliberately rather than silently under-covering the new one.
  assert.equal(Object.keys(SPEC.errors).length, 9);
});

test('every spec code maps to the class the spec names, at the status it names', () => {
  for (const [code, declared] of Object.entries(SPEC.errors)) {
    const Cls = classifyErrorClass(code, declared.description, declared.http);
    assert.equal(
      Cls.name,
      declared.class,
      `spec code ${code} must classify as ${declared.class}, got ${Cls.name}`
    );

    // The class the spec names must actually be exported under that name — a
    // caller writes `catch (e) { if (e instanceof nRouterCreditError) }`.
    assert.equal(
      typeof errors[declared.class],
      'function',
      `${declared.class} is named by the spec but not exported`
    );
    assert.equal(errors[declared.class], Cls);

    // An instance really is of that class and preserves what it was told.
    const instance = createError('refused', { code, status: declared.http });
    assert.ok(instance instanceof nRouterError);
    assert.ok(instance instanceof Cls, `${code} did not produce a ${declared.class}`);
    assert.equal(instance.code, code, 'the gateway code must be preserved');
    assert.equal(instance.status, declared.http, 'the status must be preserved');
    assert.equal(instance.name, declared.class, 'the stack trace must name the subclass');

    assert.equal(
      ERROR_STATUS_BY_CODE[code],
      declared.http,
      `ERROR_STATUS_BY_CODE disagrees with the spec for ${code}`
    );
  }
});

test('classifyError and classifyErrorClass never disagree', () => {
  // Two entry points, one decision. They drifted apart once already — chat.ts
  // and stream.ts threw the CLASS instead of an instance, and `err.name` read
  // correctly off a constructor, so several assertions passed for the wrong
  // reason. Pin them together.
  const probes: [string | null, string, number][] = [
    ['guardrail_blocked', 'denied', 400],
    [null, 'budget exceeded for this team', 402],
    [null, 'the upstream response was too large to process', 502],
    ['some_future_code', 'new', 400],
    [null, 'teapot', 418],
  ];
  for (const [code, message, status] of probes) {
    const Cls = classifyErrorClass(code, message, status);
    const instance = classifyError(code, message, status);
    assert.ok(
      instance instanceof nRouterError,
      `classifyError must return an INSTANCE, got ${Object.prototype.toString.call(instance)}`
    );
    assert.ok(instance instanceof Cls, `${code ?? status} disagreed: ${instance.name} vs ${Cls.name}`);
    assert.equal(instance.status, status ?? null);
  }
});

test('the SDK code table and the spec agree in BOTH directions', () => {
  const specCodes = Object.keys(SPEC.errors).sort();
  assert.deepEqual(Object.keys(ERROR_CLASS_BY_CODE).sort(), specCodes,
    'ERROR_CLASS_BY_CODE must hold exactly the spec codes');
  assert.deepEqual(Object.keys(ERROR_STATUS_BY_CODE).sort(), specCodes,
    'ERROR_STATUS_BY_CODE must hold exactly the spec codes');
});

// ---------------------------------------------------------------------------
// Case 4 — codeless dispatch. The gateway's MAIN error path sends
// {"error":{"type":"gateway_error","message":…}} with NO code, so this is the
// ordinary route, not a fallback.
// ---------------------------------------------------------------------------

const CODELESS: [string, number, string, string, boolean][] = [
  // name                       status  message                                     class                            retryable
  ['400 default',                400,   'malformed body',                           'nRouterRequestError',            false],
  ['400 guardrail',              400,   'Guardrail rule denied this request',       'nRouterGuardrailBlockedError',   false],
  ['401',                        401,   'unauthorized',                             'nRouterAuthenticationError',     false],
  ['402 shortfall',              402,   'insufficient credit balance',              'nRouterCreditError',             false],
  ['402 budget',                 402,   'budget exceeded for this team',            'nRouterBudgetExceededError',     false],
  ['404 model',                  404,   'model gpt-9 not found',                    'nRouterNotFoundError',           false],
  ['404 other',                  404,   'video job not found',                      'nRouterError',                   false],
  ['429',                        429,   'slow down',                                'nRouterRateLimitError',          true],
  ['502 transient',              502,   'upstream service failed',                  'nRouterServiceError',            true],
  ['502 too large',              502,   'the upstream response was too large to process', 'nRouterError',             false],
  ['503',                        503,   'upstream unavailable',                     'nRouterServiceError',            true],
  ['418 unknown status',         418,   'teapot',                                   'nRouterError',                   false],
];

for (const [name, status, message, className, retryable] of CODELESS) {
  test(`codeless dispatch: ${name}`, () => {
    const Cls = classifyErrorClass(null, message, status);
    assert.equal(Cls.name, className, `${status} "${message}" must classify as ${className}`);

    const err = createError(message, { status });
    assert.equal(err.name, className);
    assert.equal(err.code, null, 'no code was sent, so none may be invented');
    assert.equal(err.status, status);
    assert.equal(
      isRetryable(err),
      retryable,
      `${name} retryability is wrong; a retry loop acts on this`
    );
  });
}

test('a 502 that is NOT the oversized case stays retryable, and the oversized one does not', () => {
  // The two share a status and are told apart only by the gateway's wording.
  // Getting this backwards either hammers a deterministic failure forever or
  // gives up on a provider blip that would have cleared.
  assert.equal(isRetryable(createError('upstream service failed', { status: 502 })), true);
  assert.equal(
    isRetryable(createError('the upstream response was too large to process', { status: 502 })),
    false
  );
});

// ---------------------------------------------------------------------------
// Case 5 — an unknown CODE is preserved, never reclassified.
// ---------------------------------------------------------------------------

test('an unknown code stays the base class and is preserved verbatim', () => {
  const Cls = classifyErrorClass('some_future_code', 'new', 400);
  assert.equal(
    Cls.name,
    'nRouterError',
    'an unrecognised code must NOT be guessed into a neighbouring class'
  );

  const err = createError('new', { code: 'some_future_code', status: 400 });
  assert.equal(err.code, 'some_future_code', 'the unknown code must reach the caller');
  assert.equal(err.kind, 'other');
  assert.equal(err.status, 400);
});

test('a present code beats the status, even when they disagree', () => {
  // The code is the only thing separating rate_limit_exceeded from
  // tpm_limit_exceeded, so it has to outrank a status that would blur them.
  const err = createError('tpm', { code: 'tpm_limit_exceeded', status: 429 });
  assert.equal(err.name, 'nRouterRateLimitError');
  const odd = createError('weird', { code: 'insufficient_credits', status: 500 });
  assert.equal(odd.name, 'nRouterCreditError', 'the code, not the status, decides');
});

// ---------------------------------------------------------------------------
// Case 6 — isRetryable is true for exactly three kinds, and never for an abort.
// ---------------------------------------------------------------------------

const RETRYABLE_BY_KIND: Record<string, boolean> = {
  rate_limit: true,
  service: true,
  transport: true,
  request: false,
  guardrail_blocked: false,
  authentication: false,
  credit: false,
  budget_exceeded: false,
  not_found: false,
  other: false,
  configuration: false,
};

test('every declared error kind is covered by this table', () => {
  // Gathered from the exported classes rather than retyped, so a new subclass
  // with a new kind fails here instead of quietly defaulting to non-retryable.
  const kinds = new Set<string>();
  for (const value of Object.values(errors)) {
    if (typeof value === 'function' && value.prototype instanceof nRouterError) {
      kinds.add((value as { kind: string }).kind);
    }
  }
  kinds.add(nRouterError.kind);
  assert.deepEqual(
    [...kinds].sort(),
    Object.keys(RETRYABLE_BY_KIND).sort(),
    'a kind exists that this retryability table does not cover'
  );
});

test('isRetryable is true ONLY for rate-limit, service and transport', () => {
  for (const [kind, want] of Object.entries(RETRYABLE_BY_KIND)) {
    const Cls = [...Object.values(errors)].find(
      (v) => typeof v === 'function' && (v === nRouterError || v.prototype instanceof nRouterError) &&
        (v as { kind?: string }).kind === kind
    ) as (new (m: string) => { kind: string; retryable: boolean }) | undefined;
    assert.ok(Cls, `no exported class produces kind ${kind}`);
    const err = new Cls('x');
    assert.equal(isRetryable(err), want, `kind ${kind}: isRetryable should be ${want}`);
    assert.equal(err.retryable, want, `kind ${kind}: the .retryable getter must agree`);
  }
});

test('an ABORTED request is never retryable, whatever its kind', () => {
  // The caller asked to stop. A loop that retries past its own deadline is
  // ignoring them, and on a billed endpoint it is a second charge.
  for (const abortName of ['AbortError', 'TimeoutError', 'APIUserAbortError']) {
    const cause = new Error('aborted');
    cause.name = abortName;
    const err = createError('the request did not reach the gateway', { status: 0, cause });
    assert.equal(err.kind, 'other');
    // A transport-kind error carrying an abort is the realistic shape.
    const transport = new errors.nRouterTransportError('aborted mid-flight', { cause });
    assert.equal(transport.kind, 'transport');
    assert.equal(
      isRetryable(transport),
      false,
      `a ${abortName} cause must defeat transport retryability`
    );
  }
});

test('a non-nRouterError is reported non-retryable', () => {
  // Guessing "retry" on a failure this SDK did not classify is the expensive
  // direction to be wrong in.
  assert.equal(isRetryable(new Error('boom')), false);
  assert.equal(isRetryable(null), false);
  assert.equal(isRetryable(undefined), false);
  assert.equal(isRetryable({ kind: 'rate_limit' }), false);
});

test('instanceof survives the compiled CommonJS Error-subclass trap', () => {
  // Downlevelled `class X extends Error` can return a fresh Error, making every
  // typed catch in the SDK silently stop matching.
  const err = createError('slow', { code: 'rate_limit_exceeded', status: 429 });
  assert.ok(err instanceof errors.nRouterRateLimitError);
  assert.ok(err instanceof nRouterError);
  assert.ok(err instanceof Error);
});

// ---------------------------------------------------------------------------
// Case 11 (unit half) — status and request id reach the error.
// ---------------------------------------------------------------------------

test('meta fills requestId, limitSource and authReason onto the error', () => {
  const { metaFromHeaders } = require('../dist/meta');
  const meta = metaFromHeaders({
    'x-nr-request-id': 'nrouter-xyz',
    'x-nr-limit-source': 'budget',
    'x-nr-auth-reason': 'key_blocked',
  });
  const err = createError('slow', { code: 'rate_limit_exceeded', status: 429, meta });
  assert.equal(err.requestId, 'nrouter-xyz');
  assert.equal(err.limitSource, 'budget');
  assert.equal(err.authReason, 'key_blocked');
  assert.equal(err.status, 429, 'status 0 means "never reached the gateway"; this one did');
});

test('an explicit field beats the one meta would supply', () => {
  const err = createError('x', {
    status: 429,
    requestId: 'explicit',
    meta: { ...require('../dist/meta').EMPTY_META, requestId: 'from-meta' },
  });
  assert.equal(err.requestId, 'explicit');
});

// ---------------------------------------------------------------------------
// Case 12 — Retry-After in BOTH RFC 9110 forms.
// ---------------------------------------------------------------------------

test('parseRetryAfter accepts delta-seconds and HTTP-date', () => {
  const now = Date.parse('Thu, 27 Aug 2026 12:00:00 GMT');
  const httpDate = (offsetSeconds: number) =>
    new Date(now + offsetSeconds * 1000).toUTCString();

  const cases: [string, string | null | undefined, number | null][] = [
    ['absent (undefined)', undefined, null],
    ['absent (null)', null, null],
    ['empty', '', null],
    ['delta seconds', '30', 30],
    ['delta seconds padded', '  45  ', 45],
    ['delta seconds zero', '0', 0],
    ['http date in the future', httpDate(90), 90],
    ['http date in the past clamps to 0', httpDate(-3600), 0],
    ['garbage', 'soon-ish', null],
    // FINDING (open at the time of writing): JavaScript's `Date.parse` is far
    // more permissive than Go's `http.ParseTime`, which is what the ported
    // implementation assumes. `Date.parse('12.5')` yields 5 Dec 2001 — a date
    // in the past — which the clamp turns into 0, i.e. "retry immediately".
    // A malformed Retry-After therefore converts a 429 backoff into a hot
    // retry loop against a limit that is already tripped. Neither RFC 9110
    // form accepts "12.5", so the correct answer is null (no guidance).
    ['float is not delta-seconds', '12.5', null],
  ];

  for (const [name, raw, want] of cases) {
    assert.equal(parseRetryAfter(raw, now), want, `Retry-After ${name}`);
  }
});

test('a parsed Retry-After reaches the error object', () => {
  const err = createError('slow', { code: 'rate_limit_exceeded', status: 429, retryAfter: 30 });
  assert.equal(err.retryAfter, 30);
  assert.equal(createError('slow', { status: 429 }).retryAfter, null,
    'an absent Retry-After must be null, never a 0-second "retry now"');
});

test('computeJitteredBackoff adheres to bounds, clamps attempts, and prioritizes Retry-After', () => {
  // Base delay without retry-after
  const delay0 = computeJitteredBackoff({ attempt: 0, baseDelayMs: 1000, maxDelayMs: 10000, jitterFactor: 0 });
  assert.equal(delay0, 1000);

  const delay2 = computeJitteredBackoff({ attempt: 2, baseDelayMs: 1000, maxDelayMs: 10000, jitterFactor: 0 });
  assert.equal(delay2, 4000);

  // Attempt clamp prevents overflow
  const delayHuge = computeJitteredBackoff({ attempt: 100, baseDelayMs: 1000, maxDelayMs: 8000, jitterFactor: 0 });
  assert.equal(delayHuge, 8000);

  // Negative attempt handled safely
  const delayNeg = computeJitteredBackoff({ attempt: -5, baseDelayMs: 500, jitterFactor: 0 });
  assert.equal(delayNeg, 500);

  // Retry-After prioritization
  const delayRetry = computeJitteredBackoff({ attempt: 0, retryAfterSeconds: 5, maxDelayMs: 10000, jitterFactor: 0 });
  assert.equal(delayRetry, 5000);

  // Retry-After capped by maxDelayMs
  const delayRetryCapped = computeJitteredBackoff({ attempt: 0, retryAfterSeconds: 20, maxDelayMs: 10000, jitterFactor: 0 });
  assert.equal(delayRetryCapped, 10000);

  // Jitter distribution produces value within [min, max]
  const jittered = computeJitteredBackoff({ attempt: 1, baseDelayMs: 1000, jitterFactor: 0.4 });
  assert.ok(jittered >= 1200 && jittered <= 2000, `jittered ${jittered} should be within [1200, 2000]`);
});

// ---------------------------------------------------------------------------
// parseErrorBody — both envelope shapes the wire actually carries.
// ---------------------------------------------------------------------------

test('parseErrorBody reads the nested envelope, the bare one, and a codeless type', () => {
  assert.deepEqual(
    parseErrorBody({ error: { code: 'insufficient_credits', message: 'top up' } }),
    { code: 'insufficient_credits', message: 'top up' }
  );
  // A proxy that flattened the envelope must still produce a typed error.
  assert.deepEqual(
    parseErrorBody({ code: 'insufficient_credits', message: 'top up' }),
    { code: 'insufficient_credits', message: 'top up' }
  );
  // The MAIN gateway path: a `type` that is not one of the nine codes must NOT
  // be promoted into `code`, or every response manufactures an unknown code.
  assert.deepEqual(
    parseErrorBody({ error: { type: 'gateway_error', message: 'upstream failed' } }),
    { code: null, message: 'upstream failed' }
  );
  // ...but a `type` that IS one of the nine is the code, arriving under the
  // wrong key. This is how guardrail_blocked reaches the caller at all.
  assert.deepEqual(
    parseErrorBody({ error: { type: 'guardrail_blocked', message: 'denied' } }),
    { code: 'guardrail_blocked', message: 'denied' }
  );
});

// ---------------------------------------------------------------------------
// Case 15 — the API key never appears in a message or a JSON serialization.
// ---------------------------------------------------------------------------

const SECRET = 'sk-nrouter-live-9f3ab7c2e1d40556aa';

test('a key echoed into an error message is redacted', () => {
  const err = createError(`key ${SECRET} was refused`, { code: 'invalid_api_key', status: 401 });
  assert.ok(!err.message.includes(SECRET), `the message leaked the key: ${err.message}`);
  assert.ok(
    err.message.includes('sk-nrouter-'),
    'the prefix stays so "must start with sk-nrouter-" still reads correctly'
  );
});

test('no serialization of an error carries the key', () => {
  const cause = new Error(`fetch failed for Authorization: Bearer ${SECRET}`);
  const err = createError(`upstream said ${SECRET}`, {
    code: 'invalid_api_key',
    status: 401,
    requestId: 'nrouter-1',
    cause,
  });

  for (const rendered of [
    JSON.stringify(err),
    JSON.stringify(err.toJSON()),
    String(err),
    err.message,
    err.stack ?? '',
  ]) {
    assert.ok(!rendered.includes(SECRET), `a key leaked: ${rendered.slice(0, 200)}`);
  }

  // `cause` and `stack` must be absent from toJSON: a fetch failure can carry
  // the originating Request, whose headers hold the key.
  const json = err.toJSON();
  assert.equal('cause' in json, false, 'toJSON must never serialize the cause');
  assert.equal('stack' in json, false, 'toJSON must never serialize the stack');
});

test('a key inside a gateway error BODY is redacted before it becomes a message', () => {
  const parsed = parseErrorBody({ error: { message: `bad key ${SECRET}` } });
  assert.ok(!String(parsed.message).includes(SECRET), `parseErrorBody leaked: ${parsed.message}`);
});

test('a bare sk- key (not ours) is redacted too', () => {
  const foreign = 'sk-proj-AAAAAAAAAAAAAAAAAAAAAA';
  const err = createError(`rejected ${foreign}`, { status: 401 });
  assert.ok(!err.message.includes(foreign), `a foreign key leaked: ${err.message}`);
});

// ---------------------------------------------------------------------------
// Case 17 — a NESTED abort is still an abort (gate 8: a retry is a second bill).
// ---------------------------------------------------------------------------

test('a NESTED abort cause defeats retryability, not only a top-level one', () => {
  // The realistic shape, and the one the depth-8 walk in `wasAborted` exists
  // for: Node's fetch/undici reports a cancelled request as
  // `TypeError: fetch failed` whose `.cause` is the DOMException named
  // AbortError, and the vendor client wraps that again as an
  // APIConnectionError. `isAbortLike` only inspects the TOP of that chain, so
  // the chain walk is the only thing that can see the cancellation.
  //
  // If the constructor's cause sanitizer flattens the chain to one node, the
  // walk has nothing to walk: a cancelled POST — which may already have been
  // billed — is reported RETRYABLE and a `while (isRetryable(e))` loop resends
  // it.
  const abort = new Error('This operation was aborted');
  abort.name = 'AbortError';
  const fetchFailed = new Error('fetch failed');
  fetchFailed.name = 'TypeError';
  (fetchFailed as Error & { cause?: unknown }).cause = abort;
  const vendor = new Error('Connection error.');
  vendor.name = 'APIConnectionError';
  (vendor as Error & { cause?: unknown }).cause = fetchFailed;

  const depth2 = new errors.nRouterTransportError('cancelled mid-flight', { cause: fetchFailed });
  assert.equal(isRetryable(depth2), false, 'an abort one level down must defeat retryability');

  const depth3 = new errors.nRouterTransportError('cancelled mid-flight', { cause: vendor });
  assert.equal(isRetryable(depth3), false, 'an abort two levels down must defeat retryability');
});

test('sanitizing a cause chain still carries no key at any depth', () => {
  // The chain must survive for the abort walk, but sanitization is what keeps
  // the Authorization header out of `util.inspect` — both properties, one fix.
  const inner = new Error(`upstream rejected ${SECRET}`);
  inner.name = 'AbortError';
  (inner as Error & { request?: unknown }).request = {
    headers: { authorization: `Bearer ${SECRET}` },
  };
  const outer = new Error('fetch failed');
  (outer as Error & { cause?: unknown }).cause = inner;

  const err = new errors.nRouterTransportError('cancelled', { cause: outer });
  assert.equal(isRetryable(err), false, 'the nested abort must still be visible');

  const util = require('node:util');
  const rendered = `${util.inspect(err, { depth: 12 })}${JSON.stringify(err.toJSON())}${err.stack}`;
  assert.ok(!rendered.includes(SECRET), `a key leaked through the cause chain: ${rendered}`);
  assert.ok(
    !rendered.includes('authorization'),
    'the originating Request must never survive sanitization'
  );
});

test('a cause CYCLE cannot hang the sanitizer', () => {
  const a = new Error('a');
  const b = new Error('b');
  (a as Error & { cause?: unknown }).cause = b;
  (b as Error & { cause?: unknown }).cause = a;
  const err = new errors.nRouterTransportError('looping', { cause: a });
  assert.equal(isRetryable(err), true, 'a non-abort cycle is still an ordinary transport failure');
});

// ---------------------------------------------------------------------------
// Case 18 — an ABSURD Retry-After is a hot retry in JavaScript, not a long wait.
// ---------------------------------------------------------------------------

test('an absurd Retry-After is capped, because setTimeout turns it into a HOT retry', () => {
  // THIS IS A JAVASCRIPT-SPECIFIC HAZARD and the reason this SDK caps where the
  // Go port does not. `setTimeout` stores its delay in a 32-bit signed int:
  // any delay over 2147483647 ms overflows and the timer fires on the NEXT
  // TICK. So the natural caller —
  //   `await new Promise(r => setTimeout(r, err.retryAfter * 1000))`
  // — sleeps ~1 ms for a Retry-After of ten years and hammers a limit that
  // just refused it. Sleeping in Go for the same value is a real ten-year
  // sleep, so the port inherited a bound it did not need and lost one it did.
  const { MAX_RETRY_AFTER_SECONDS } = errors;
  assert.equal(typeof MAX_RETRY_AFTER_SECONDS, 'number');
  assert.ok(
    MAX_RETRY_AFTER_SECONDS * 1000 <= 2 ** 31 - 1,
    'the cap must keep retryAfter * 1000 inside setTimeout\'s 32-bit delay'
  );

  const now = Date.parse('Thu, 27 Aug 2026 12:00:00 GMT');
  const tenYears = 10 * 365 * 24 * 3600;
  assert.equal(parseRetryAfter(String(tenYears), now), MAX_RETRY_AFTER_SECONDS,
    'a ten-year delta-seconds must be capped, not passed through');
  assert.equal(parseRetryAfter('99999999999999999999', now), MAX_RETRY_AFTER_SECONDS,
    'a value past 2^53 must be capped, not handed over as a rounded float');
  assert.equal(
    parseRetryAfter(new Date(now + tenYears * 1000).toUTCString(), now),
    MAX_RETRY_AFTER_SECONDS,
    'the HTTP-date form must be capped by the same ceiling as delta-seconds'
  );

  // The cap must not disturb any realistic value.
  assert.equal(parseRetryAfter('30', now), 30);
  assert.equal(parseRetryAfter('0', now), 0);
  assert.equal(parseRetryAfter(String(MAX_RETRY_AFTER_SECONDS), now), MAX_RETRY_AFTER_SECONDS);
});
