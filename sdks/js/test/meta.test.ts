// Case 1 + Case 2 from the review brief: unpriced is not free, and every one
// of the thirteen `x-nr-*` headers has a real parse site.
//
// Ported from sdks/go/client_test.go (TestAllThirteenHeadersAreRead,
// TestUnpricedIsNilNotZero, TestUnparseableNumericHeaderIsNilNotZero), with
// the JavaScript-specific traps the Go version gets for free from `strconv`
// added: Number('') === 0, Number('Infinity') === Infinity, parseInt('12abc')
// === 12. Each of those turns an absent or corrupt header into a confident
// number, and for `x-nr-request-cost` that number is a free request — which no
// enabled model is (Rule #28).

const { test } = require('node:test');
const assert = require('node:assert/strict');

const meta = require('../dist/meta');
const { HEADER_NAMES } = require('../dist/types');

const { metaFromHeaders, metaFromLookup, isPriced, EMPTY_META } = meta;

/**
 * One plausible value for every header the SDK claims to read.
 *
 * This object is half of a two-way agreement check with HEADER_NAMES. Adding a
 * name to HEADER_NAMES without adding it here fails; adding it here without
 * declaring it there fails too. That is what stops a header from being listed
 * as supported while nothing ever parses it.
 */
const FIXTURE: Record<string, string> = {
  'x-nr-request-id': 'nrouter-abc123',
  'x-nr-request-cost': '0.00347',
  'x-nr-cost-status': 'exact',
  'x-nr-model': 'claude-sonnet-4-5',
  'x-nr-input-tokens': '42',
  'x-nr-output-tokens': '18',
  'x-nr-total-tokens': '60',
  'x-nr-cache-read-tokens': '7',
  'x-nr-cache-write-tokens': '3',
  'x-nr-limit-source': 'key',
  'x-nr-auth-reason': 'key_blocked',
  'x-nr-response-cache': 'hit',
  'x-nr-response-cache-age': '12',
};

test('HEADER_NAMES and this test fixture agree in BOTH directions', () => {
  assert.equal(
    HEADER_NAMES.length,
    13,
    'the spec fixes thirteen response headers'
  );
  for (const name of HEADER_NAMES) {
    assert.ok(
      Object.prototype.hasOwnProperty.call(FIXTURE, name),
      `HEADER_NAMES declares ${name} but this test never sends it`
    );
  }
  for (const name of Object.keys(FIXTURE)) {
    assert.ok(
      HEADER_NAMES.includes(name as never),
      `this test sends ${name} but HEADER_NAMES does not declare it`
    );
  }
  assert.equal(HEADER_NAMES.length, Object.keys(FIXTURE).length);
});

test('meta re-exports the same HEADER_NAMES array, not a second copy', () => {
  // Two lists that can drift is the defect this file exists to prevent.
  assert.equal(meta.HEADER_NAMES, HEADER_NAMES);
});

test('every one of the thirteen headers is actually read', () => {
  const parsed = metaFromHeaders(FIXTURE);

  assert.equal(parsed.requestId, 'nrouter-abc123');
  assert.equal(parsed.cost, 0.00347);
  assert.equal(parsed.costStatus, 'exact');
  assert.equal(parsed.model, 'claude-sonnet-4-5');
  assert.equal(parsed.inputTokens, 42);
  assert.equal(parsed.outputTokens, 18);
  assert.equal(parsed.totalTokens, 60);
  assert.equal(parsed.cacheReadTokens, 7);
  assert.equal(parsed.cacheWriteTokens, 3);
  assert.equal(parsed.limitSource, 'key');
  assert.equal(parsed.authReason, 'key_blocked');
  assert.equal(parsed.responseCache, 'hit');
  assert.equal(parsed.responseCacheAge, 12);
  assert.equal(isPriced(parsed), true);

  // Nothing was invented: the parsed object has exactly the declared fields.
  assert.deepEqual(
    Object.keys(parsed).sort(),
    Object.keys(EMPTY_META).sort()
  );
});

test('each header on its own moves at least one field off EMPTY_META', () => {
  // The strong form of "all thirteen are read". A name added to HEADER_NAMES
  // with no parse site produces a meta identical to EMPTY_META, and this loop
  // is what turns that silent no-op into a failing test.
  for (const name of HEADER_NAMES) {
    const parsed = metaFromHeaders({ [name]: FIXTURE[name] }) as Record<string, unknown>;

    // `undefined` is excluded deliberately. A DELETED parse site leaves its
    // field missing, and `undefined !== null` would read as "this header moved
    // something" — the false green this loop exists to prevent.
    const moved = Object.keys(EMPTY_META).filter(
      (field) =>
        parsed[field] !== undefined &&
        parsed[field] !== (EMPTY_META as Record<string, unknown>)[field]
    );
    assert.ok(
      moved.length >= 1,
      `${name} is declared in HEADER_NAMES but has no parse site: it changed nothing`
    );
    assert.deepEqual(
      Object.keys(parsed).sort(),
      Object.keys(EMPTY_META).sort(),
      `parsing ${name} produced a meta missing a declared field`
    );
  }
});

// ---------------------------------------------------------------------------
// Case 1 — UNPRICED IS NOT FREE.
// ---------------------------------------------------------------------------

test('an ABSENT x-nr-request-cost parses to null, never 0', () => {
  const parsed = metaFromHeaders({
    'x-nr-request-id': 'nrouter-abc123',
    'x-nr-cost-status': 'unpriced',
  });
  assert.equal(parsed.cost, null, 'an absent cost header must stay null');
  assert.notEqual(parsed.cost, 0, 'reporting 0 bills the customer for a free request');
  assert.equal(isPriced(parsed), false, 'unpriced must never report as priced');
});

test('an UNPARSEABLE numeric header parses to null, never 0', () => {
  const parsed = metaFromHeaders({
    'x-nr-request-cost': 'also-not',
    'x-nr-input-tokens': 'not-a-number',
    'x-nr-total-tokens': '',
    'x-nr-response-cache-age': '12abc',
  });
  assert.equal(parsed.cost, null);
  assert.equal(parsed.inputTokens, null);
  assert.equal(parsed.totalTokens, null, "Number('') is 0 in JavaScript; that must not reach a caller");
  assert.equal(parsed.responseCacheAge, null, "parseInt('12abc') is 12; a trailing-garbage header is not a measurement");
  assert.equal(isPriced(parsed), false);
});

test('the JavaScript numeric traps all resolve to null', () => {
  for (const hostile of ['NaN', 'Infinity', '-Infinity', '0x10', '1e', '+5', '-5', '.5', '5.', ' ']) {
    const parsed = metaFromHeaders({ 'x-nr-request-cost': hostile });
    assert.equal(parsed.cost, null, `x-nr-request-cost: ${JSON.stringify(hostile)} must be null`);
  }
  for (const hostile of ['NaN', 'Infinity', '4.5', '-1', '1e3', '0x10', ' ']) {
    const parsed = metaFromHeaders({ 'x-nr-input-tokens': hostile });
    assert.equal(parsed.inputTokens, null, `x-nr-input-tokens: ${JSON.stringify(hostile)} must be null`);
  }
});

test('a cost of exactly 0 with an exact status is still reported as priced', () => {
  // The inverse guard. Null is the ONLY unpriced signal; a real zero that the
  // gateway explicitly priced is a number, not an absence, and must survive.
  const parsed = metaFromHeaders({
    'x-nr-request-cost': '0',
    'x-nr-cost-status': 'exact',
  });
  assert.equal(parsed.cost, 0);
  assert.equal(isPriced(parsed), true);
});

test('a cost WITHOUT an exact status is not priced', () => {
  // The two headers disagreeing is a contradiction; billing against it charges
  // a customer for an amount the gateway said it could not compute.
  const parsed = metaFromHeaders({
    'x-nr-request-cost': '0.5',
    'x-nr-cost-status': 'unpriced',
  });
  assert.equal(parsed.cost, 0.5);
  assert.equal(isPriced(parsed), false);
});

test('EMPTY_META is all-null and frozen', () => {
  for (const [field, value] of Object.entries(EMPTY_META)) {
    assert.equal(value, null, `EMPTY_META.${field} must be null, never a zero`);
  }
  assert.equal(Object.isFrozen(EMPTY_META), true, 'a shared singleton must not be mutable');
});

test('header names are matched case-insensitively', () => {
  // An intermediary that title-cases headers must not make a fully metered
  // response look unmetered.
  const parsed = metaFromHeaders({
    'X-NR-Request-Id': 'nrouter-upper',
    'X-Nr-Request-Cost': '1.25',
    'X-NR-COST-STATUS': 'exact',
  });
  assert.equal(parsed.requestId, 'nrouter-upper');
  assert.equal(parsed.cost, 1.25);
  assert.equal(isPriced(parsed), true);
});

test('a WHATWG Headers bag and a plain record parse identically', () => {
  const bag = new Headers(FIXTURE);
  assert.deepEqual(metaFromHeaders(bag), metaFromHeaders(FIXTURE));
});

test('a repeated header takes the first value, never a joined string', () => {
  // Node hands repeated headers back as an array. Joining "1" and "2" into
  // "1, 2" parses to null and loses a real measurement.
  const parsed = metaFromHeaders({ 'x-nr-input-tokens': ['42', '99'] });
  assert.equal(parsed.inputTokens, 42);
});

test('metaFromLookup is the primitive metaFromHeaders is written in terms of', () => {
  const viaLookup = metaFromLookup((name: string) => FIXTURE[name] ?? null);
  assert.deepEqual(viaLookup, metaFromHeaders(FIXTURE));
});

test('a response with no x-nr-* headers at all equals EMPTY_META', () => {
  assert.deepEqual(metaFromHeaders({ 'content-type': 'application/json' }), EMPTY_META);
});
