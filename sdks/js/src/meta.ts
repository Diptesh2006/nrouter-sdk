// Parser for the gateway's `x-nr-*` response metadata headers.
//
// The whole file exists to defend one property: an absent header and an
// unparseable header both become `null`, and nothing here ever invents a
// number. JavaScript makes that harder than it looks — `Number('')` is 0,
// `parseFloat('1.5abc')` is 1.5, `Number('NaN')` is NaN — so every numeric
// header goes through an explicit shape check before it is allowed to become
// a value. The Go SDK gets this for free from `strconv`; here it is written
// out, and each guard below names the failure it prevents.

import { HEADER_NAMES, type ResponseMeta } from './types';

/**
 * A WHATWG-style header bag: anything exposing a case-insensitive `get`.
 *
 * This is structural rather than the DOM `Headers` type on purpose. The
 * package compiles under `lib: ["ES2020"]` with no DOM and no assumed Node
 * globals, so naming `Headers` would make the SDK depend on the caller's
 * ambient type environment. A real `Headers`, an undici `Headers`, a
 * `node-fetch` `Headers` and OpenAI's own response headers all satisfy this
 * shape, so widening it costs nothing and removes a whole class of "works in
 * my project, not in theirs" build failures.
 */
export interface HeadersLike {
  get(name: string): string | null | undefined;
}

/**
 * A Node `IncomingHttpHeaders`-style bag, or any plain object of headers.
 *
 * Values may be `string[]` because Node hands repeated headers back as arrays,
 * and `undefined` because indexing a missing key yields it.
 */
export type HeaderRecord = Record<string, string | string[] | undefined>;

/** Anything `metaFromHeaders` knows how to read. */
export type HeaderSource = HeadersLike | HeaderRecord;

/**
 * A response for which the gateway reported nothing at all.
 *
 * Frozen because it is a shared singleton: one caller stamping a field onto it
 * would silently rewrite the "no metadata" answer for every other reader in
 * the process. Callers that need a mutable object should spread it.
 */
export const EMPTY_META: ResponseMeta = Object.freeze({
  requestId: null,
  cost: null,
  costStatus: null,
  model: null,
  inputTokens: null,
  outputTokens: null,
  totalTokens: null,
  cacheReadTokens: null,
  cacheWriteTokens: null,
  limitSource: null,
  budgetWarning: null,
  authReason: null,
  responseCache: null,
  responseCacheAge: null,
});

/**
 * A whole, unsigned decimal count and nothing else — the shape every token
 * header has.
 *
 * Anchored at both ends so a partial match cannot slip through: without `^`
 * and `$` this would accept `12abc`, exactly the trailing-garbage case that
 * makes `parseInt` dangerous here. No sign is permitted because a negative
 * token count is not a measurement, it is a mangled header.
 */
const UNSIGNED_INTEGER = /^[0-9]+$/;

/**
 * A plain unsigned decimal, with optional fraction and exponent — the shape a
 * USD cost has.
 *
 * Deliberately NARROWER than `Number()` accepts. `Number('Infinity')`,
 * `Number('NaN')` and `Number('0x10')` all succeed, and a NaN or Infinity cost
 * poisons every sum a caller folds it into while still passing a `!== null`
 * check. It is also narrower than Go's `strconv.ParseFloat`, which accepts
 * "Inf" and "NaN" as valid floats; that is a genuine tightening, not a port
 * bug. No sign, because the gateway never bills a negative amount: a minus
 * sign means something upstream corrupted the value, and a negative cost
 * quietly netted against a customer's bill is worse than a missing one.
 */
const UNSIGNED_DECIMAL = /^[0-9]+(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?$/;

/**
 * Normalize a raw header value to a string, or `null` if it carries nothing.
 *
 * An empty or whitespace-only header is treated as absent. The gateway omits a
 * header it has nothing to say about, so an empty value can only come from an
 * intermediary; surfacing it as `''` would put an empty string in front of a
 * user where "the gateway did not say" is the truth. Trimming also absorbs the
 * optional surrounding whitespace HTTP permits in a field value and that not
 * every parser strips.
 */
function text(raw: string | null | undefined): string | null {
  if (raw === null || raw === undefined) return null;
  const trimmed = raw.trim();
  return trimmed === '' ? null : trimmed;
}

/**
 * Parse a token-count header, or `null`.
 *
 * The `Number.isSafeInteger` check is the last guard: past 2^53 a JS number
 * silently rounds, and a rounded count is a fabricated one. It is unreachable
 * with real token counts, which is precisely why it must be written down
 * rather than assumed.
 */
function count(raw: string | null | undefined): number | null {
  const value = text(raw);
  if (value === null) return null;
  if (!UNSIGNED_INTEGER.test(value)) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) ? parsed : null;
}

/**
 * Parse the cost header, or `null`.
 *
 * This is the single most load-bearing function in the file. `x-nr-request-cost`
 * is ABSENT when the model is unpriced — it is never sent as `0` — so any path
 * that turns absence or garbage into a number reports a free request, and no
 * enabled model is free (Rule #28). `Number.isFinite` backstops the pattern
 * check so an Infinity can never reach a caller's arithmetic.
 */
function money(raw: string | null | undefined): number | null {
  const value = text(raw);
  if (value === null) return null;
  if (!UNSIGNED_DECIMAL.test(value)) return null;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return null;
  // UNDERFLOW IS NOT ZERO. `1e-999` is syntactically a positive decimal and
  // Number() collapses it to 0 — paired with `x-nr-cost-status: exact` that
  // reports a FREE request, which is the one thing this whole function exists
  // to prevent (Rule #28). A real zero is written "0", "0.0", "0e0" — its
  // significand is zero. A zero whose significand was NOT is a value we could
  // not represent, and "could not represent" is unknown, not free.
  if (parsed === 0 && /[1-9]/.test(value)) return null;
  return parsed;
}

/**
 * Build `ResponseMeta` from any lowercase-name header lookup.
 *
 * This is the primitive the other entry point is written in terms of, and the
 * seam a caller with an exotic transport can implement directly. `get` is
 * called with the canonical lowercase names from `HEADER_NAMES`; a lookup that
 * is itself case-sensitive must therefore be fed lowercase keys, which is what
 * `metaFromHeaders` arranges.
 */
export function metaFromLookup(get: (name: string) => string | null | undefined): ResponseMeta {
  return {
    requestId: text(get('x-nr-request-id')),
    cost: money(get('x-nr-request-cost')),
    costStatus: text(get('x-nr-cost-status')),
    model: text(get('x-nr-model')),
    inputTokens: count(get('x-nr-input-tokens')),
    outputTokens: count(get('x-nr-output-tokens')),
    totalTokens: count(get('x-nr-total-tokens')),
    cacheReadTokens: count(get('x-nr-cache-read-tokens')),
    cacheWriteTokens: count(get('x-nr-cache-write-tokens')),
    limitSource: text(get('x-nr-limit-source')),
    budgetWarning: text(get('x-nr-budget-warning')),
    authReason: text(get('x-nr-auth-reason')),
    responseCache: text(get('x-nr-response-cache')),
    responseCacheAge: count(get('x-nr-response-cache-age')),
  };
}

/** Does this value expose a WHATWG-style `get`? */
function isHeadersLike(source: HeaderSource): source is HeadersLike {
  return typeof (source as HeadersLike).get === 'function';
}

/**
 * Build `ResponseMeta` from a `Headers` object or a plain header record.
 *
 * Header names are case-insensitive on the wire, so a caller handing us
 * `X-NR-Request-Id` must get the same answer as one handing us
 * `x-nr-request-id`. A `Headers` bag already guarantees that; a plain object
 * does not, so its keys are lowercased into an index first — indexing the raw
 * object would return `undefined` for correctly-spelled headers and report a
 * fully-metered response as having no metadata at all.
 *
 * Only the fourteen names in `HEADER_NAMES` are read, so the index is built
 * from the caller's keys once rather than scanned per lookup.
 */
export function metaFromHeaders(headers: HeaderSource): ResponseMeta {
  if (isHeadersLike(headers)) {
    return metaFromLookup((name) => headers.get(name));
  }

  const index = new Map<string, string>();
  for (const key of Object.keys(headers)) {
    const value = headers[key];
    if (value === undefined) continue;
    // Node reports a repeated header as an array. Take the first value, which
    // is what Go's `http.Header.Get` does: joining them would turn two counts
    // into "1, 2", which parses to null and loses a real measurement.
    const first = Array.isArray(value) ? value[0] : value;
    if (typeof first !== 'string') continue;
    index.set(key.toLowerCase(), first);
  }

  return metaFromLookup((name) => index.get(name) ?? null);
}

/**
 * Did the gateway price this request exactly?
 *
 * Deliberately not merely `cost !== null`. A cost paired with a status of
 * `unpriced` is a contradiction — the two headers disagree about whether the
 * amount means anything — and a caller must not bill against it. Requiring
 * both makes the ambiguous case fall to `false`, which costs us a billable
 * request at worst; trusting the number alone charges a customer for one the
 * gateway said it could not price.
 */
export function isPriced(meta: ResponseMeta): boolean {
  return meta.costStatus === 'exact' && meta.cost !== null;
}

/**
 * Re-exported so a caller can forward exactly the headers this parser reads —
 * into their own logging or tracing layer — without retyping the list and
 * letting the two copies drift.
 */
export { HEADER_NAMES };
