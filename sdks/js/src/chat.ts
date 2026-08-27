// The high-level buffered chat helper: playground parity in one call.
//
// Everything the hosted playground can set on a request is reachable through
// `NRouterCallOptions`, and every response comes back paired with the `x-nr-*`
// metadata the gateway reported for it. An option a user can toggle in our own
// UI and cannot express here is a feature that exists only inside our UI.
//
// This module takes a `ChatRunner`, not the OpenAI client. The transport stays
// the integrator's — their `fetch`, timeout, retries, proxy and headers — and
// this file owns only what happens to the bytes that come back. That seam is
// also what makes every refusal below unit-testable with no network and no
// vendor mock: a two-line fake runner reproduces a streaming response, a
// truncated body or a 429 exactly.
//
// Nothing here re-implements a cross-cutting concern that a sibling already
// owns. Error classification, key redaction, `Retry-After` parsing and error-
// envelope parsing all live in ./errors, and metadata parsing lives in ./meta.
// A second copy of any of them is how two code paths start disagreeing about
// the same header.

import { metaFromHeaders, EMPTY_META } from './meta';
import type { HeaderSource } from './meta';
import {
  nRouterError,
  createError,
  configurationError,
  transportError,
  parseErrorBody,
  parseRetryAfter,
} from './errors';
import { buildSamplingParams } from './sampling';
import { buildChatBody } from './options';
import type { NRouterCallOptions, NRouterResponse, ResponseMeta } from './types';

/** The gateway's buffered chat endpoint. Path only — the runner owns the base URL. */
const CHAT_PATH = '/chat/completions';

/** Key under which a failed `compare` arm parks its error. See `compare`. */
export const COMPARE_ERROR_KEY = 'nrouter_error';

/** One response, exactly as the transport saw it and before anything is parsed. */
export interface ChatRunnerResponse {
  status: number;
  headers: HeaderSource;
  /**
   * The body UNPARSED. Deciding whether a 2xx is even parseable is this
   * module's job — a runner that helpfully called `JSON.parse` for us would
   * have already destroyed the evidence refusal #1 depends on.
   */
  text: string;
  /** Reported separately so the JSON/not-JSON decision never depends on the body. */
  contentType: string;
}

/**
 * The transport seam. One method, deliberately: the caller wires it to the
 * `nRouter` client, to `fetch`, or to a fake in a test, and this module never
 * learns which.
 */
export interface ChatRunner {
  request(path: string, body: unknown): Promise<ChatRunnerResponse>;
}

/**
 * Run one buffered chat completion with full playground parity.
 *
 * Resolves to the decoded body paired with the gateway's per-request metadata:
 * cost, token counts, cache outcome, and the model that actually served it.
 * Cost is `null` when the model is unpriced — never `0`, because no enabled
 * model is free (Rule #28).
 *
 * Rejects with an `nRouterError` and nothing else, so one `catch` covers every
 * failure mode. Every rejection raised after the response headers arrived
 * carries that response's context.
 */
export async function chat(
  runner: ChatRunner,
  opts: NRouterCallOptions,
): Promise<NRouterResponse<Record<string, unknown>>> {
  const sampling = buildSamplingParams({
    advanced: opts.advancedSampling ?? false,
    model: opts.model,
    provider: opts.modelProvider ?? null,
    temperature: opts.temperature,
    topP: opts.topP,
  });
  const body = buildChatBody(opts, sampling);

  // REFUSAL 0 — before a single byte leaves the process.
  //
  // `buildChatBody` never sets `stream` itself, so it can only arrive through
  // `opts.extra`. Sent as-is it produces an SSE stream that this buffered
  // helper would refuse at refusal #1 — but only AFTER the provider had been
  // called and the customer already billed. Refusing at the door is the one
  // place the refusal costs nothing.
  //
  // CONFIGURATION for the same reason refusal #1 is: the wrong helper was
  // called, and that is not a condition any retry improves.
  if (body['stream'] === true) {
    throw configurationError(
      'chat() is the BUFFERED helper and cannot consume a stream; remove ' +
        '`stream: true` from `extra` or use the streaming entry point. Sent ' +
        'as-is it would bill a provider call whose body this helper cannot ' +
        'return.',
    );
  }

  const res = await send(runner, body);
  const meta = metaFromHeaders(res.headers);

  if (res.status < 200 || res.status >= 300) {
    throw gatewayFailure(res, meta);
  }

  // REFUSAL 1 — a 2xx that is not JSON is a REAL RESPONSE the caller was
  // billed for: audio from /audio/speech, a video body, or an SSE stream.
  // `JSON.parse` on it either throws or, worse, yields something empty — and
  // then the call reports success while the customer receives nothing for
  // money that is already spent.
  //
  // CONFIGURATION, deliberately, NOT transport. This was a retryable transport
  // error in the Go draft and a reviewer flagged it P1: a caller's generic
  // `if (isRetryable(e)) retry` loop would repeat a BILLED request forever,
  // burning real credits at whatever rate the loop turns. The wrong method was
  // called for this endpoint, and that condition is permanent.
  if (!res.contentType.toLowerCase().includes('json')) {
    throw configurationError(
      `gateway returned ${res.status} with content-type "${res.contentType}", ` +
        'which is not JSON. Use the raw-bytes path for binary or streaming ' +
        'endpoints (/audio/speech, /videos/{id}/content, or "stream": true) — ' +
        'parsing this as JSON would report success with an empty body for a ' +
        'request that was billed.',
      // REFUSAL 3 — the response context. Without `status` and `meta` this
      // failure would carry status null ("never reached the gateway") on a
      // request that plainly did, and the request id — the caller's only join
      // key to the spend row — would exist nowhere but a message string.
      { status: res.status, meta },
    );
  }

  // REFUSAL 2 — a 2xx whose JSON does not parse is a TRUNCATED or corrupted
  // billed response, not an empty one. Returning `{}` here hands back a
  // completion with no choices and lets the caller conclude the model said
  // nothing.
  //
  // This one IS transient: the identical request can return an intact body
  // next time, so it is a transport error and a retry loop is right to take
  // it. That is the whole reason refusals #1 and #2 are different kinds
  // despite both being "a 2xx we could not read".
  let decoded: unknown;
  try {
    decoded = JSON.parse(res.text) as unknown;
  } catch (cause) {
    throw transportError(
      `gateway returned ${res.status} with unparseable JSON ` +
        `(${describe(cause)}); the request was billed but the body did not ` +
        'arrive intact.',
      { status: res.status, meta, cause },
    );
  }

  // A JSON scalar, array or null where an object was promised is the same
  // corruption one step later: `res.body.choices` on a `null` throws inside
  // the caller's code, far from the request id that would have explained it.
  if (decoded === null || typeof decoded !== 'object' || Array.isArray(decoded)) {
    throw transportError(
      `gateway returned ${res.status} with a JSON body that is not an object; ` +
        'the request was billed but the response is not shaped like a ' +
        'completion.',
      { status: res.status, meta },
    );
  }

  return { body: decoded as Record<string, unknown>, meta };
}

/**
 * Pull the assistant's text out of a completion.
 *
 * Returns `''` rather than throwing on an unexpected shape, on purpose. The
 * body is already in the caller's hands and the metadata beside it is already
 * correct — cost, token counts and request id all survive. Throwing here would
 * destroy a response the caller PAID for over a convenience accessor, and it
 * would throw on the legitimate cases too: a guardrail-redacted turn, a
 * tool-call-only choice with `content: null`, a `finish_reason: "length"` cut
 * at zero tokens, and every provider that answers in content PARTS rather than
 * a bare string.
 *
 * `''` is honest here in a way `0` never is for cost: an empty completion is a
 * real thing a model returns, whereas a free request is not (Rule #28). A
 * caller who needs to distinguish "no text" from "unexpected shape" still has
 * the full body — this accessor takes nothing away.
 */
export function chatText(res: NRouterResponse<Record<string, unknown>>): string {
  const choices: unknown = res.body['choices'];
  if (!Array.isArray(choices) || choices.length === 0) {
    return '';
  }
  const message = pluck(pluck(choices[0], 'message'), 'content');
  if (typeof message === 'string') {
    return message;
  }
  // Content PARTS: the Anthropic-shaped and multimodal replies the gateway
  // relays through unchanged. Concatenating the text parts beats reporting
  // "no answer" for a response that plainly contains one.
  if (Array.isArray(message)) {
    let out = '';
    for (const part of message) {
      const text = pluck(part, 'text');
      if (typeof text === 'string') {
        out += text;
      }
    }
    return out;
  }
  return '';
}

/**
 * Run the same options against several models at once — the playground's
 * side-by-side compare, as one call.
 *
 * Results come back in the SAME ORDER as `models`, never in completion order,
 * so `models[i]` and `results[i]` always describe each other. Ordering by
 * whichever model answered first would silently label the fast model's answer
 * with the slow model's name on every run.
 *
 * PARTIAL FAILURE — the choice, and why:
 *
 * Concurrency is `Promise.allSettled`, not `Promise.all`. `all` rejects on the
 * FIRST failure and discards every sibling result, including the ones that
 * already succeeded and were already BILLED. Comparing four models and losing
 * three paid answers because the fourth alias was misspelled is exactly the
 * shape of loss this SDK exists to prevent.
 *
 * A failed arm therefore still occupies its slot, with its `nRouterError`
 * parked at `body[COMPARE_ERROR_KEY]` and read back through `compareError()`.
 * The two alternatives are both worse: throwing an aggregate at the end
 * collapses the whole call again, and an empty `{}` body is indistinguishable
 * from a model that answered with nothing. A sentinel key that no completion
 * carries is the only option that is at once non-lossy and unmistakable.
 *
 * The failed arm's `meta` keeps whatever the gateway managed to report before
 * failing — request id, limit source, auth reason — so the correlation path
 * survives the failure. Everything unknown stays `null` rather than being
 * filled in with a plausible zero.
 *
 * Concurrency is unbounded, matching the playground: a compare is a handful of
 * models chosen by hand, and this helper is not the place to invent a queue
 * the gateway's own RPM limiter already implements. A caller comparing dozens
 * should batch them and will get a typed `nRouterRateLimitError` per arm —
 * with `retryAfter` — rather than one collapsed failure, if they do not.
 */
export async function compare(
  runner: ChatRunner,
  opts: NRouterCallOptions,
  models: string[],
): Promise<NRouterResponse<Record<string, unknown>>[]> {
  const settled = await Promise.allSettled(
    models.map((model) => chat(runner, { ...opts, model })),
  );

  return settled.map((outcome) => {
    if (outcome.status === 'fulfilled') {
      return outcome.value;
    }
    const failure = normalize(outcome.reason);
    return {
      body: { [COMPARE_ERROR_KEY]: failure },
      meta: metaFromError(failure),
    };
  });
}

/**
 * The error from a failed `compare` arm, or `null` when that arm succeeded.
 *
 * Exported so a caller never has to string-match `COMPARE_ERROR_KEY` itself.
 * An implicit key convention is precisely the kind of contract that rots the
 * first time somebody renames it.
 */
export function compareError(
  res: NRouterResponse<Record<string, unknown>>,
): nRouterError | null {
  const parked: unknown = res.body[COMPARE_ERROR_KEY];
  return parked instanceof nRouterError ? parked : null;
}

// ---------------------------------------------------------------------------
// Internals
// ---------------------------------------------------------------------------

/**
 * Call the runner and normalize whatever it throws.
 *
 * The runner IS the transport, so a raw throw out of it is by definition a
 * transport failure — DNS, TLS, a dropped socket, an abort. Wrapping it here
 * is what lets `chat` promise it rejects with `nRouterError` and nothing else,
 * which is in turn what lets a caller write one `catch` instead of two. No
 * status is stamped: no HTTP exchange happened, and `isRetryable` already
 * declines an aborted cause, so a cancelled request is not retried as a blip.
 */
async function send(
  runner: ChatRunner,
  body: Record<string, unknown>,
): Promise<ChatRunnerResponse> {
  try {
    return await runner.request(CHAT_PATH, body);
  } catch (cause) {
    throw normalize(cause);
  }
}

/**
 * Turn a non-2xx into a typed error.
 *
 * REFUSAL 4. Classification is `createError`'s — code when the gateway sent
 * one, then status, then the message — because the gateway's MAIN error path
 * sends no `code` at all (it emits `{"error":{"type","message"}}`), so keying
 * on `code` alone makes `guardrail_blocked` unreachable and tells a caller to
 * fix a request body that was never the problem.
 *
 * `parseErrorBody` reads the envelope BOTH ways — the gateway's nested
 * `{"error":{...}}` and a bare `{code,message}` — because a proxy in front of
 * the gateway may reshape it, and reading only the nested form turns every
 * typed refusal behind such a proxy into a generic one. It also redacts any
 * key that reached the message, which is why the message is never assembled
 * here from raw response text (Rule #5).
 */
function gatewayFailure(res: ChatRunnerResponse, meta: ResponseMeta): nRouterError {
  let envelope: unknown = null;
  try {
    envelope = JSON.parse(res.text) as unknown;
  } catch {
    // An unparseable ERROR body is ordinary — a proxy's HTML 502 page, an
    // empty 504. The status alone still classifies it correctly. The raw text
    // is deliberately NOT promoted into the message: it is unbounded and
    // unredacted, and this module cannot redact it (that lives in ./errors).
  }

  const { code, message } = parseErrorBody(envelope);

  return createError(message ?? 'nRouter request failed', {
    code,
    // REFUSAL 3 — status and metadata from the response that actually
    // happened, so the failure carries the request id, the limit source that
    // explains a 429 and the auth reason that explains a 401.
    status: res.status,
    meta,
    // REFUSAL 4 — `Retry-After` in BOTH RFC 9110 forms. Upstreams do send the
    // HTTP-date form and the gateway relays it unchanged; a delta-seconds-only
    // parse yields nothing for it and the caller retries before the provider
    // said to, which on a 429 is how a backoff becomes a hammer and the limit
    // stays tripped. ./errors owns the parse; this only supplies the header.
    retryAfter: parseRetryAfter(headerValue(res.headers, 'retry-after')),
  });
}

/**
 * Read one header from either shape a runner may hand back.
 *
 * `metaFromHeaders` covers the `x-nr-*` set but not `Retry-After`, which is a
 * standard header rather than one of ours. The record form is matched
 * case-insensitively: HTTP header names are case-insensitive, a `Headers`
 * object normalizes them and a plain object does not, so an exact-key lookup
 * would find `Retry-After` from one runner and miss it from another.
 */
function headerValue(headers: HeaderSource, name: string): string | null {
  const maybe = headers as { get?: (key: string) => string | null | undefined };
  if (typeof maybe.get === 'function') {
    return maybe.get(name) ?? null;
  }
  const record = headers as Record<string, string | string[] | undefined>;
  const wanted = name.toLowerCase();
  for (const key of Object.keys(record)) {
    if (key.toLowerCase() !== wanted) {
      continue;
    }
    const value = record[key];
    if (Array.isArray(value)) {
      return value.length > 0 ? (value[0] ?? null) : null;
    }
    return value ?? null;
  }
  return null;
}

/** Coerce any rejection into the one error type this module promises. */
function normalize(reason: unknown): nRouterError {
  if (reason instanceof nRouterError) {
    return reason;
  }
  return transportError(`the request did not reach the gateway: ${describe(reason)}`, {
    cause: reason,
  });
}

/**
 * Metadata for a `compare` arm that failed.
 *
 * Only what the gateway actually reported survives. Everything else stays
 * `null` via the shared `EMPTY_META`, because a zero cost or a zero token
 * count here would be a fabricated fact about a request that may well have
 * been billed. `EMPTY_META` is a frozen singleton, so it is spread, never
 * stamped.
 */
function metaFromError(err: nRouterError): ResponseMeta {
  return (
    err.meta ?? {
      ...EMPTY_META,
      requestId: err.requestId,
      limitSource: err.limitSource,
      authReason: err.authReason,
    }
  );
}

/** Read one property off a value that may be anything at all. */
function pluck(value: unknown, key: string): unknown {
  if (value === null || typeof value !== 'object') {
    return undefined;
  }
  return (value as Record<string, unknown>)[key];
}

/**
 * Render an unknown rejection as a message.
 *
 * Never `JSON.stringify` and never `String(obj)` on an arbitrary thrown value:
 * what threw is frequently a request or client object, and serializing one is
 * how an `Authorization: Bearer sk-nrouter-…` ends up in an error message, a
 * log line and eventually a bug report. The error constructor redacts what it
 * can, but not producing the string in the first place is the stronger guard
 * (Rule #5).
 */
function describe(reason: unknown): string {
  if (reason instanceof Error) {
    return reason.message;
  }
  if (typeof reason === 'string') {
    return reason;
  }
  return 'unknown failure';
}
