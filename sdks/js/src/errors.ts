// The typed error hierarchy for the nRouter SDK.
//
// Ported from sdks/go/errors.go so the two SDKs classify the SAME refusal the
// same way. Every non-obvious branch below exists because the naive version of
// it hands a caller a confidently wrong remedy — each one names the failure it
// prevents rather than restating the code.
//
// The class names come from the `class` values in spec/nrouter-sdk-spec.json
// (Rule #14). They are the contract; do not rename one to suit local style.

import type { ResponseMeta } from './types';

/**
 * Why a request failed. One value per entry in the spec `errors` block, plus
 * the three conditions that never reach the gateway or that no code names.
 *
 * `kind` is a plain string rather than a class check on purpose: it survives a
 * duplicated copy of this package in a dependency tree, where `instanceof`
 * silently stops matching because the two copies have different prototypes.
 */
export type nRouterErrorKind =
  | 'request'
  | 'guardrail_blocked'
  | 'authentication'
  | 'credit'
  | 'budget_exceeded'
  | 'not_found'
  | 'rate_limit'
  | 'service'
  | 'other'
  | 'transport'
  | 'configuration';

/** Everything the transport can hand the error layer about one failure. */
export interface nRouterErrorOptions {
  /**
   * The gateway's stable error code when it sent one.
   *
   * The gateway's MAIN error path sends `{"error":{"type","message"}}` with NO
   * code at all, so an absent code is the ordinary case rather than an
   * anomaly, and status dispatch is the ordinary route rather than a fallback.
   */
  code?: string | null;
  /** HTTP status. Null/absent when the request never reached the gateway. */
  status?: number | null;
  /** Joins this failure to a gateway spend row or log line (`x-nr-request-id`). */
  requestId?: string | null;
  /** Which limit measured a 429 (`x-nr-limit-source`). Null means the gateway did not say — never guess. */
  limitSource?: string | null;
  /** The gateway's stable reason for refusing a virtual key on a 401 (`x-nr-auth-reason`). */
  authReason?: string | null;
  /** `Retry-After` in whole seconds, already parsed. See `parseRetryAfter`. */
  retryAfter?: number | null;
  /**
   * The underlying failure when one exists — an `AbortError`, a DNS or TLS
   * error, a parse error. Kept for diagnosis and NEVER serialized: a fetch
   * failure can carry the originating Request, whose headers hold the API key.
   */
  cause?: unknown;
  /**
   * Response metadata parsed from the `x-nr-*` headers. When supplied, it
   * fills `requestId` / `limitSource` / `authReason` unless those were passed
   * explicitly, so the transport does not have to unpack it twice.
   */
  meta?: ResponseMeta | null;
}

/**
 * Redact any API key that reached a message string.
 *
 * Rule #5: no message, property, or `toJSON` may ever contain a key. The
 * gateway should never echo one, but a message is assembled from a body we do
 * not control, and a key printed once into a log aggregator is a key rotated.
 *
 * The prefix is preserved and only the secret TAIL is replaced, so a
 * configuration message that legitimately says "must start with sk-nrouter-"
 * still reads correctly.
 *
 * That property is the whole reason this is two passes and not one. The single
 * expression `/(sk-(?:nrouter-)?)[A-Za-z0-9._-]{6,}/` backtracks: on the literal
 * text `sk-nrouter-` it matches the group as `sk-` and the tail as `nrouter-`,
 * producing "must start with sk-***" — hiding the one thing the reader needs.
 * It was also NOT IDEMPOTENT: `sk-nrouter-<secret>` redacted twice became
 * `sk-******`, because after the first pass `nrouter-` was again a valid tail.
 * Nothing leaked either way — it over-redacts — but a redactor that mangles its
 * own output cannot be run defensively at more than one layer, and this one is
 * (parseErrorBody redacts, then the constructor redacts again).
 *
 * Pass 1 handles a real customer key. Pass 2 catches any other `sk-` credential
 * a body might echo, and refuses to touch the branded prefix. `*` is outside
 * the tail character class, so neither pass can match its own output.
 */
export function redactKeys(message: string): string {
  return message
    .replace(/(sk-nrouter-)[A-Za-z0-9._-]{6,}/g, '$1***')
    .replace(/(sk-)(?!nrouter-)[A-Za-z0-9._-]{6,}/g, '$1***');
}

/**
 * The base of every error this SDK throws. Catch this to catch all of them;
 * catch a subclass, or switch on `kind`, to act on one condition.
 *
 * It is also the concrete class for the `other` kind: a code this SDK version
 * does not recognise is PRESERVED on `code` and never reclassified into a
 * neighbouring class, because guessing a stable code onto an unknown condition
 * is how a caller ends up handling the wrong failure forever.
 */
export class nRouterError extends Error {
  /** The kind a `new` of this class produces. Read through `new.target` below. */
  static readonly kind: nRouterErrorKind = 'other';

  readonly kind: nRouterErrorKind;
  readonly code: string | null;
  status: number | null;
  requestId: string | null;
  limitSource: string | null;
  authReason: string | null;
  retryAfter: number | null;
  /** Never serialized — see `nRouterErrorOptions.cause`. */
  cause?: unknown;
  /** Response headers as parsed metadata, when the failure carried any. */
  readonly meta: ResponseMeta | null;

  constructor(message: string, options: nRouterErrorOptions = {}) {
    super(redactKeys(message));

    // THE COMPILED-CommonJS TRAP, and it is real, not theoretical.
    //
    // With `target` below ES2015 (and in several bundler/`__extends` emits at
    // ES2020) TypeScript downlevels `class X extends Error` into a function
    // that calls `Error.call(this)`. `Error` is exotic: called that way it
    // ALLOCATES AND RETURNS A FRESH OBJECT rather than initialising `this`, so
    // the instance the caller receives has `Error.prototype` and
    // `err instanceof nRouterRateLimitError` is FALSE — every typed catch in
    // the SDK silently stops matching while nothing looks broken.
    //
    // Re-pinning the prototype to `new.target.prototype` restores it, and
    // `new.target` (not a hardcoded class) keeps it correct for every subclass
    // and for anyone subclassing ours. Each subclass repeats this so the guard
    // survives someone later giving it a constructor of its own.
    Object.setPrototypeOf(this, new.target.prototype);

    const self = new.target as typeof nRouterError;
    this.kind = self.kind;
    // Name the subclass, so a stack trace says nRouterRateLimitError.
    this.name = new.target.name;

    const meta = options.meta ?? null;
    this.code = options.code ?? null;
    this.status = options.status ?? null;
    this.requestId = options.requestId ?? meta?.requestId ?? null;
    this.limitSource = options.limitSource ?? meta?.limitSource ?? null;
    this.authReason = options.authReason ?? meta?.authReason ?? null;
    this.retryAfter = options.retryAfter ?? null;
    this.meta = meta;
    if (options.cause !== undefined) {
      // SANITIZED, never the raw object. A fetch/undici failure commonly holds
      // a reference to the originating Request — headers included — so
      // `console.error(err)` and `util.inspect(err)` traverse `cause` and print
      // the whole `Authorization` value. Neither `toJSON()` nor message
      // redaction covers that path, and it is the single most common way an
      // error reaches a log (Rule #5).
      //
      // The NAME is preserved because that is what the abort walk below reads,
      // so `AbortError` and `TimeoutError` are still recognised and still
      // report non-retryable.
      //
      // Declared as a property rather than passed to `super(msg, {cause})`:
      // the ES2020 lib this package compiles against has no Error `cause`.
      this.cause = sanitizeCause(options.cause);
    }

    // Keep the SDK frame out of the trace where the runtime supports it.
    const captureStackTrace = (
      Error as unknown as { captureStackTrace?: (target: object, ctor?: Function) => void }
    ).captureStackTrace;
    if (typeof captureStackTrace === 'function') {
      captureStackTrace(this, new.target);
    }
  }

  /** True when retrying the identical request could plausibly succeed. */
  get retryable(): boolean {
    return isRetryable(this);
  }

  /**
   * A log-safe, structured view of the failure.
   *
   * `cause` and `stack` are deliberately absent. A transport `cause` can hold
   * the originating Request — and therefore the `Authorization` header — so
   * serializing it would write the API key into whatever consumed this
   * (Rule #5). `meta` is omitted for the same shape of reason: callers that
   * want it read `err.meta` explicitly rather than getting it by accident.
   */
  toJSON(): Record<string, unknown> {
    return {
      name: this.name,
      kind: this.kind,
      message: this.message,
      code: this.code,
      status: this.status,
      requestId: this.requestId,
      limitSource: this.limitSource,
      authReason: this.authReason,
      retryAfter: this.retryAfter,
    };
  }
}

/** `invalid_request` (400) — invalid JSON or request shape. Permanent. */
export class nRouterRequestError extends nRouterError {
  static readonly kind: nRouterErrorKind = 'request';
  constructor(message: string, options: nRouterErrorOptions = {}) {
    super(message, options);
    Object.setPrototypeOf(this, new.target.prototype); // see the base constructor
  }
}

/** `guardrail_blocked` (400) — a guardrail rule denied it. The body was not the problem. */
export class nRouterGuardrailBlockedError extends nRouterError {
  static readonly kind: nRouterErrorKind = 'guardrail_blocked';
  constructor(message: string, options: nRouterErrorOptions = {}) {
    super(message, options);
    Object.setPrototypeOf(this, new.target.prototype); // see the base constructor
  }
}

/** `invalid_api_key` (401) — virtual-key auth refused; see `authReason`. */
export class nRouterAuthenticationError extends nRouterError {
  static readonly kind: nRouterErrorKind = 'authentication';
  constructor(message: string, options: nRouterErrorOptions = {}) {
    super(message, options);
    Object.setPrototypeOf(this, new.target.prototype); // see the base constructor
  }
}

/** `insufficient_credits` (402) — the reserve failed, nothing was spent. Remedy: top up. */
export class nRouterCreditError extends nRouterError {
  static readonly kind: nRouterErrorKind = 'credit';
  constructor(message: string, options: nRouterErrorOptions = {}) {
    super(message, options);
    Object.setPrototypeOf(this, new.target.prototype); // see the base constructor
  }
}

/**
 * A BUDGET ceiling (402), not a shortfall. Remedy: raise the budget.
 *
 * Two conditions share 402 and their fixes are OPPOSITE. Telling a customer
 * whose budget is exhausted to add money is a wrong answer delivered
 * confidently — they pay us more and the next request fails identically.
 */
export class nRouterBudgetExceededError extends nRouterError {
  static readonly kind: nRouterErrorKind = 'budget_exceeded';
  constructor(message: string, options: nRouterErrorOptions = {}) {
    super(message, options);
    Object.setPrototypeOf(this, new.target.prototype); // see the base constructor
  }
}

/** `model_not_found` (404) — alias absent or not visible to this key. */
export class nRouterNotFoundError extends nRouterError {
  static readonly kind: nRouterErrorKind = 'not_found';
  constructor(message: string, options: nRouterErrorOptions = {}) {
    super(message, options);
    Object.setPrototypeOf(this, new.target.prototype); // see the base constructor
  }
}

/** `rate_limit_exceeded` / `tpm_limit_exceeded` (429) — see `limitSource` and `retryAfter`. */
export class nRouterRateLimitError extends nRouterError {
  static readonly kind: nRouterErrorKind = 'rate_limit';
  constructor(message: string, options: nRouterErrorOptions = {}) {
    super(message, options);
    Object.setPrototypeOf(this, new.target.prototype); // see the base constructor
  }
}

/** `credit_check_failed` / `service_unavailable` (503), and transient upstream 502/504. */
export class nRouterServiceError extends nRouterError {
  static readonly kind: nRouterErrorKind = 'service';
  constructor(message: string, options: nRouterErrorOptions = {}) {
    super(message, options);
    Object.setPrototypeOf(this, new.target.prototype); // see the base constructor
  }
}

/**
 * The request left this process and got no usable answer — DNS, TLS, a dropped
 * connection, a timeout. Retryable: the same request may well succeed.
 */
export class nRouterTransportError extends nRouterError {
  static readonly kind: nRouterErrorKind = 'transport';
  constructor(message: string, options: nRouterErrorOptions = {}) {
    super(message, options);
    Object.setPrototypeOf(this, new.target.prototype); // see the base constructor
  }
}

/**
 * The SDK refused before sending anything: no key, or a key not shaped like an
 * nRouter key.
 *
 * Separate from `nRouterTransportError` on purpose. Both are raised locally,
 * but this one is PERMANENT — a caller retrying on `isRetryable` would spin
 * forever without ever making a request.
 */
export class nRouterConfigurationError extends nRouterError {
  static readonly kind: nRouterErrorKind = 'configuration';
  constructor(message: string, options: nRouterErrorOptions = {}) {
    super(message, options);
    Object.setPrototypeOf(this, new.target.prototype); // see the base constructor
  }
}

/**
 * The nine spec codes to their classes, verbatim from
 * spec/nrouter-sdk-spec.json. Exported as data so a test can assert the table
 * against the spec instead of re-typing it.
 */
export const ERROR_CLASS_BY_CODE: Readonly<Record<string, typeof nRouterError>> = Object.freeze({
  invalid_request: nRouterRequestError,
  guardrail_blocked: nRouterGuardrailBlockedError,
  invalid_api_key: nRouterAuthenticationError,
  insufficient_credits: nRouterCreditError,
  model_not_found: nRouterNotFoundError,
  rate_limit_exceeded: nRouterRateLimitError,
  tpm_limit_exceeded: nRouterRateLimitError,
  credit_check_failed: nRouterServiceError,
  service_unavailable: nRouterServiceError,
});

/** The HTTP status the spec pairs with each code. */
export const ERROR_STATUS_BY_CODE: Readonly<Record<string, number>> = Object.freeze({
  invalid_request: 400,
  guardrail_blocked: 400,
  invalid_api_key: 401,
  insufficient_credits: 402,
  model_not_found: 404,
  rate_limit_exceeded: 429,
  tpm_limit_exceeded: 429,
  credit_check_failed: 503,
  service_unavailable: 503,
});

/**
 * Pick the class for one gateway refusal.
 *
 * THREE signals, in this order, because no single one is sufficient:
 *
 *  1. The `code`, when present — it is the ONLY thing separating
 *     `rate_limit_exceeded` from `tpm_limit_exceeded`, and an unrecognised one
 *     is preserved as the base class rather than guessed into a neighbour.
 *  2. The HTTP status otherwise. The gateway's main error path emits no code
 *     at all, so this is the ORDINARY route, not the fallback it looks like.
 *  3. The message, to split the two 400s and the two 402s. Classifying every
 *     400 as a request error makes nRouterGuardrailBlockedError UNREACHABLE,
 *     telling a caller to fix a body that was never the problem.
 */
export function classifyErrorClass(
  code?: string | null,
  message?: string | null,
  status?: number | null,
): typeof nRouterError {
  if (code) {
    const known = ERROR_CLASS_BY_CODE[code];
    // An unknown code is preserved on the instance, never reclassified.
    return known ?? nRouterError;
  }

  const lower = (message ?? '').toLowerCase();

  switch (status) {
    case 400:
      return lower.includes('guardrail') ? nRouterGuardrailBlockedError : nRouterRequestError;
    case 401:
      return nRouterAuthenticationError;
    case 402:
      // The gateway's own wording is the only discriminator it gives us, and
      // it is stable: GatewayError::{BudgetExceeded, ScopedBudgetExceeded}
      // both begin their Display with "budget".
      return lower.trimStart().startsWith('budget')
        ? nRouterBudgetExceededError
        : nRouterCreditError;
    case 404:
      // Scoped to MODELS. A 404 is also a missing video job, an unknown MCP
      // server or an unknown agent run; calling those model_not_found is a
      // wrong answer with a confident stable code on it.
      return lower.includes('model') ? nRouterNotFoundError : nRouterError;
    case 429:
      return nRouterRateLimitError;
    case 502:
    case 504:
      // The gateway's ORDINARY upstream-failure statuses. Upstream,
      // UpstreamService, Sandbox and SandboxError all map to 502, every one of
      // them transient, and leaving them unclassified made a provider blip
      // non-retryable.
      //
      // UpstreamBodyTooLarge shares that 502 and is NOT transient: the same
      // request produces the same oversized response forever. Its customer
      // message is fixed — "the upstream response was too large to process" —
      // so it is the one 502 that stays the base class.
      return lower.includes('too large') ? nRouterError : nRouterServiceError;
    case 503:
      return nRouterServiceError;
    default:
      return nRouterError;
  }
}

/** Build the right error instance for one refusal. The factory form of `classifyError`. */
export function createError(message: string, options: nRouterErrorOptions = {}): nRouterError {
  const ErrorClass = classifyErrorClass(options.code, message, options.status);
  return new ErrorClass(message, options);
}

/** The SDK refused before sending anything. Permanent — never retried. */
export function configurationError(message: string, options: nRouterErrorOptions = {}): nRouterError {
  return new nRouterConfigurationError(message, options);
}

/** The request left this process and got no usable answer. Retryable. */
export function transportError(message: string, options: nRouterErrorOptions = {}): nRouterError {
  return new nRouterTransportError(message, options);
}

/**
 * Names a runtime gives an aborted operation. `AbortError` is `AbortController`
 * and Node's `fetch`; `TimeoutError` is `AbortSignal.timeout()`;
 * `APIUserAbortError` is the `openai` client this SDK is built on.
 */
export const ABORT_NAMES = new Set(['AbortError', 'TimeoutError', 'APIUserAbortError']);

/** Walk a cause chain looking for an abort, bounded so a cycle cannot hang the caller. */
function wasAborted(err: unknown): boolean {
  let current: unknown = err;
  for (let depth = 0; depth < 8 && current !== null && current !== undefined; depth += 1) {
    if (typeof current === 'object') {
      const name = (current as { name?: unknown }).name;
      if (typeof name === 'string' && ABORT_NAMES.has(name)) return true;
      current = (current as { cause?: unknown }).cause;
      continue;
    }
    return false;
  }
  return false;
}

/**
 * Whether retrying the identical request could plausibly succeed.
 *
 * True for exactly three kinds — rate limit, service, transport. Everything
 * else names a permanent condition, and a retry there burns quota without any
 * chance of a different answer. `configuration` is the one that bites: it is
 * raised locally like `transport`, so treating them alike makes a retry loop
 * spin forever having never made a single request.
 *
 * An aborted request is never retryable whatever its kind — the caller asked
 * to stop, and a loop that retries past its own deadline is ignoring it.
 *
 * Anything that is not an nRouterError is reported non-retryable: this SDK
 * cannot reason about a failure it did not classify, and guessing "retry"
 * on an unknown error is the expensive direction to be wrong in.
 */
export function isRetryable(err: unknown): boolean {
  if (!(err instanceof nRouterError)) return false;
  if (wasAborted(err.cause) || wasAborted(err)) return false;
  return err.kind === 'rate_limit' || err.kind === 'service' || err.kind === 'transport';
}

/**
 * Pull the gateway's `code` and `message` out of a parsed error body.
 *
 * Takes the BODY only. It never accepts headers, so it cannot echo an
 * `Authorization` value into a message (Rule #5).
 *
 * `error.type` is consulted only when it exactly matches one of the nine spec
 * codes: on the main error path `type` is an OpenAI-shaped family name
 * ("invalid_request_error"), not one of our codes, and promoting it to `code`
 * would manufacture unknown codes out of a field that never carried one.
 */
export function parseErrorBody(body: unknown): { code: string | null; message: string | null } {
  if (typeof body !== 'object' || body === null) {
    return { code: null, message: typeof body === 'string' && body ? redactKeys(body) : null };
  }

  const top = body as { error?: unknown; code?: unknown; message?: unknown };
  const inner =
    typeof top.error === 'object' && top.error !== null
      ? (top.error as { code?: unknown; message?: unknown; type?: unknown })
      : {};

  const rawCode = [inner.code, top.code].find((v) => typeof v === 'string' && v) as
    | string
    | undefined;
  const typeAsCode =
    typeof inner.type === 'string' && inner.type in ERROR_CLASS_BY_CODE ? inner.type : undefined;

  const rawMessage = [inner.message, top.message].find((v) => typeof v === 'string' && v) as
    | string
    | undefined;

  return {
    code: rawCode ?? typeAsCode ?? null,
    message: rawMessage ? redactKeys(rawMessage) : null,
  };
}

/**
 * `Retry-After` in whole seconds, or null when absent or unparseable.
 *
 * Both RFC 9110 forms are accepted: delta-seconds, and an HTTP-date, which
 * upstreams do send and the gateway relays unchanged. A date already in the
 * past clamps to 0 rather than going negative — a negative sleep is either an
 * immediate hot retry or a thrown timer, depending on the caller.
 */
export function parseRetryAfter(
  value: string | null | undefined,
  now: number = Date.now(),
): number | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  if (!trimmed) return null;

  if (/^\d+$/.test(trimmed)) {
    const seconds = Number(trimmed);
    return Number.isFinite(seconds) ? seconds : null;
  }

  // Date.parse is FAR more lenient than an HTTP-date parser, and the
  // difference is dangerous rather than cosmetic. `Date.parse('12.5')` yields
  // 5 December 2001 — a date in the past, which the clamp below turns into 0,
  // i.e. "retry immediately" against a limit that just refused us. A malformed
  // Retry-After became a hot loop on a tripped rate limit.
  //
  // RFC 9110 allows three date forms; all of them carry a comma and a
  // timezone. Requiring that shape first is what keeps a bare float, a bare
  // year, or `1e3` from being read as a date at all.
  // RFC 9110 defines THREE HTTP-date forms and a recipient must accept all of
  // them. The first two carry a comma and a timezone; the obsolete asctime
  // form — `Sun Nov  6 08:49:37 1994` — carries NEITHER, so requiring both
  // rejected a valid backoff. The doc comment above claimed all three were
  // supported while the code took two, which is the sort of gap that only
  // shows up as a customer hammering a rate limit.
  const imf = /^[A-Za-z]{3,9},\s+\d/.test(trimmed) && /(GMT|UTC|[+-]\d{4})$/i.test(trimmed);
  const asctime = /^[A-Za-z]{3}\s+[A-Za-z]{3}\s+[\s\d]\d\s+\d{2}:\d{2}:\d{2}\s+\d{4}$/.test(trimmed);
  if (!imf && !asctime) {
    return null;
  }
  const at = Date.parse(trimmed);
  if (Number.isNaN(at)) return null;
  return Math.max(0, Math.ceil((at - now) / 1000));
}

/**
 * Classify a gateway refusal and RETURN THE ERROR, not its constructor.
 *
 * This is the shape every caller in this SDK wants — `throw classifyError(...)`
 * — and the one a JS developer expects from a function with this name.
 * `classifyErrorClass` remains available for the rarer case of wanting the
 * constructor itself (an `instanceof` table, a test asserting the mapping
 * against the spec).
 */
export function classifyError(
  code?: string | null,
  message?: string | null,
  status?: number | null,
  options?: Partial<nRouterErrorOptions>,
): nRouterError {
  const Cls = classifyErrorClass(code, message, status);
  return new Cls(message ?? 'nRouter request failed', {
    ...options,
    code: code ?? options?.code ?? null,
    status: status ?? options?.status ?? null,
  });
}

/**
 * Stamp what the response already told us onto a failure raised AFTER the
 * headers arrived.
 *
 * Without it `status` stays null — documented as "never reached the gateway" —
 * on a request that DID reach it and may have been billed, and the request id
 * survives only inside a message string. The Go SDK carries the same helper
 * for the same reason; a code reviewer required it there.
 */
export function withResponse(
  err: nRouterError,
  status: number | null,
  meta: ResponseMeta | null,
): nRouterError {
  if (status !== null) err.status = status;
  if (meta) {
    err.requestId = meta.requestId;
    err.limitSource = meta.limitSource;
    err.authReason = meta.authReason;
  }
  return err;
}

/**
 * Whether a string is one of the nine STABLE gateway codes.
 *
 * The gateway puts an OpenAI-shaped family name in `type` on its ordinary
 * error path — `gateway_error` — and a real stable code there only on the
 * guardrail cut. Promoting `type` unconditionally therefore hands
 * `classifyErrorClass` an unknown code, which takes precedence over the status
 * fallback and collapses every 400/401/402/429/503 into a generic error.
 */
export function isSpecErrorCode(value: unknown): value is string {
  return typeof value === 'string' && value in ERROR_CLASS_BY_CODE;
}

/**
 * A 2xx body that is really a refusal. Returns null for anything that could be
 * a genuine response — see the SDK-026 note above for why this is conservative.
 */
export function errorEnvelopeOnSuccess(
  decoded: unknown,
): { code: string | null; message: string } | null {
  if (typeof decoded !== 'object' || decoded === null || Array.isArray(decoded)) return null;
  const body = decoded as Record<string, unknown>;

  // Anything completion-shaped beside the error means this is a real response.
  for (const key of ['choices', 'data', 'content', 'output', 'id', 'object', 'usage']) {
    if (key in body) return null;
  }

  const node = body.error;
  if (typeof node !== 'object' || node === null || Array.isArray(node)) return null;
  const err = node as Record<string, unknown>;
  const message = typeof err.message === 'string' ? err.message : null;
  if (!message) return null;

  // The gateway ships the stable code in `type` here, not `code` — the same
  // asymmetry that made guardrail_blocked unreachable across these SDKs.
  const raw = typeof err.code === 'string' ? err.code : typeof err.type === 'string' ? err.type : null;
  return { code: raw, message };
}

/**
 * A cause that is safe to print.
 *
 * Keeps the name (the abort walk reads it) and a redacted message, and drops
 * every other property — which is where a fetch failure keeps the originating
 * Request and therefore the Authorization header.
 */
function sanitizeCause(cause: unknown): unknown {
  if (cause instanceof Error) {
    const safe = new Error(redactKeys(cause.message));
    safe.name = cause.name;
    // No `stack` copy: a stack can quote a URL that carries a token.
    safe.stack = `${cause.name}: ${redactKeys(cause.message)}`;
    return safe;
  }
  if (typeof cause === 'string') return redactKeys(cause);
  // An arbitrary object may hold anything at all. Its shape is not worth the
  // risk; the message above already says what happened.
  return undefined;
}
