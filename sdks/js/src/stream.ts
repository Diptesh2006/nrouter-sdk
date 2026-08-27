// Server-Sent Events streaming for the nRouter gateway, with the response
// metadata attached.
//
// This module deliberately does NOT own a transport. It takes a `StreamRunner`
// — anything that can turn (path, body) into a status, a header bag and a byte
// stream — so the whole SSE state machine is exercisable in a unit test with
// no socket, no `openai` client and no network. Every bug this file is written
// to prevent (a split UTF-8 character, an event straddling a chunk boundary, a
// silently truncated answer) is a bug that only reproduces under a *specific*
// byte-splitting, which is exactly what a fake runner can produce on demand
// and a live call cannot.

import type { NRouterCallOptions, ResponseMeta } from './types';
import { metaFromHeaders , type HeaderSource } from './meta';
import {
  createError,
  nRouterError,
  isSpecErrorCode,
  transportError,
  parseRetryAfter,
  isAbortLike,
} from './errors';
import { buildChatBody } from './options';
import { buildSamplingParams } from './sampling';

/**
 * The gateway's OpenAI-shaped streaming endpoint, relative to the base URL.
 *
 * The base URL already carries `/v1` (spec `base_url` =
 * `https://api.nrouter.ai/v1`), so joining is the runner's job and `/v1` must
 * NOT be repeated here — `/api/v1/*` and `/v1/v1/*` both 404 at the gateway.
 */
const CHAT_COMPLETIONS_PATH = '/chat/completions';

/**
 * How much of an error body is carried into a thrown message.
 *
 * Bounded because an upstream failure can answer with an HTML error page or a
 * multi-megabyte provider dump, and an exception message ends up in logs,
 * alerting and issue trackers.
 */
const MAX_ERROR_MESSAGE_CHARS = 500;

/**
 * SSE event separator: one blank line, in any of the three line endings the
 * spec permits. Matched as a whole so a `\r` sitting at the end of a network
 * chunk is left in the buffer rather than being mistaken for a terminator —
 * treating a trailing `\r` as a line end merges two events into one when the
 * next chunk opens with `\n`.
 */
const EVENT_SEPARATOR = /\r\n\r\n|\n\n|\r\r/;

/** Any of the three SSE line endings, for splitting a single event block. */
const LINE_SEPARATOR = /\r\n|\n|\r/;

/**
 * The transport seam.
 *
 * `open` performs the request and returns BEFORE the body is consumed — the
 * metadata headers must be readable while the stream is still in flight, which
 * is the whole reason this is not a `Promise<string>`.
 */
export interface StreamRunner {
  open(
    path: string,
    body: unknown,
    signal?: AbortSignal,
  ): Promise<{
    status: number;
    headers: HeaderSource;
    body: AsyncIterable<Uint8Array> | null;
    /** Read the whole body as text. Used only on a non-2xx, to classify it. */
    text?: () => Promise<string>;
  }>;
}

/** One parsed SSE frame. */
export interface StreamChunk {
  /**
   * The incremental text this frame carried, or `''`.
   *
   * Content-less frames (the opening role frame, the terminal `finish_reason`
   * frame, the usage frame) are yielded too, with an empty `delta`, because
   * `raw` is where the token counts and the finish reason live and dropping
   * those frames would hide a truncated answer. Filter on `chunk.delta` if all
   * you want is text.
   */
  delta: string;
  /** The frame's decoded JSON, untouched. */
  raw: Record<string, unknown>;
}

export interface StreamResult {
  /**
   * Metadata from the response headers, read ONCE before the body was touched.
   *
   * On a stream the cost headers are legitimately absent, or present saying
   * `unpriced`. That is correct and permanent for this response, not a race to
   * re-read later: the gateway cannot know the settled cost when it writes the
   * status line, and it never revises a header it already sent. The spend row
   * carries the real figure and joins on `meta.requestId`. Reporting `0` here
   * would claim a free request, which no enabled model is (Rule #28).
   */
  meta: ResponseMeta;
  /**
   * The frames, in order.
   *
   * A response body can be read once, so this yields from ONE underlying
   * iterator: a second `for await` resumes where the first stopped rather than
   * replaying from the beginning.
   */
  chunks: AsyncIterable<StreamChunk>;
  /**
   * The full text, draining whatever is left of `chunks`.
   *
   * Chosen behaviour, because "already iterated" must neither hang nor
   * double-consume:
   *  - called first, it drains the whole stream and returns everything;
   *  - called after `chunks` ran to completion, it returns the accumulated
   *    text immediately (the exhausted iterator answers `done` at once);
   *  - called after you `break` out of `chunks` early, it returns only what
   *    was consumed — an early exit cancels the body, and this does not
   *    pretend otherwise;
   *  - if the stream failed, it re-throws that failure rather than handing
   *    back a partial answer that reads as complete.
   */
  text(): Promise<string>;
}

/** Mutable state shared by the iterator and `text()`. */
interface StreamState {
  text: string;
  failure: nRouterError | Error | null;
}

/**
 * Parse a block of SSE text into its events.
 *
 * Exported because it is the piece worth testing directly: every framing bug
 * this module can have is visible here, given the right input.
 *
 * `data:` lines accumulate — an event carrying several of them joins them with
 * a newline, per the SSE spec — and exactly one leading space after the colon
 * is stripped (only one; a second space is part of the payload). Comment lines
 * (`: keep-alive`) and `id:` / `retry:` are dropped: the gateway does not
 * support stream resumption, so an id we cannot act on is noise.
 */
export function parseSSE(raw: string): { event?: string; data: string }[] {
  const { events, rest } = splitEvents(raw);
  // A server may close without the final blank line. The trailing remainder is
  // a real event when it has content — dropping it loses the last token, or
  // the `[DONE]` that says the answer is complete.
  const blocks = rest.trim().length > 0 ? events.concat(rest) : events;

  const parsed: { event?: string; data: string }[] = [];
  for (const block of blocks) {
    const one = parseEventBlock(block);
    if (one !== null) parsed.push(one);
  }
  return parsed;
}

/**
 * Stream a chat completion.
 *
 * Throws before any streaming begins when the gateway refused the request, so
 * a caller never has to distinguish "the stream ended" from "there was never a
 * stream".
 */
export async function streamChat(
  runner: StreamRunner,
  opts: NRouterCallOptions,
  signal?: AbortSignal,
): Promise<StreamResult> {
  throwIfAborted(signal);

  const sampling = buildSamplingParams({
    advanced: opts.advancedSampling === true,
    model: opts.model,
    provider: opts.modelProvider,
    temperature: opts.temperature,
    topP: opts.topP,
  });

  // `stream` is set here, not by the caller: this function's entire contract is
  // that the response is an event stream, and a body that says otherwise would
  // hand the SSE parser a single JSON document to mis-parse.
  const requestBody: Record<string, unknown> = {
    ...buildChatBody(opts, sampling),
    stream: true,
  };

  const response = await runner.open(CHAT_COMPLETIONS_PATH, requestBody, signal);

  // Read the headers ONCE, here, before anything consumes the body. A runner
  // may back its header bag with a live response object, and metadata that is
  // only extracted on the success path leaves a failed request with no
  // request id — the one value a customer needs to open a support ticket.
  const meta = metaFromHeaders(response.headers);

  if (response.status < 200 || response.status >= 300) {
    const rawBody = response.text ? await response.text().catch(() => '') : '';
    // Retry-After too. The buffered and media paths both honour it; leaving it
    // out here made every streaming nRouterRateLimitError.retryAfter null, so a
    // caller could not respect the backoff the gateway actually asked for.
    const retryAfter = parseRetryAfter(headerValue(response.headers, 'retry-after'));
    throw errorFromBody(rawBody, response.status, meta, retryAfter);
  }

  const body = response.body;
  if (body === null) {
    // A 2xx with no body is not an empty answer — the request was accepted, so
    // it may well have been billed. Failing loudly beats returning "".
    throw createError('the gateway accepted the request but returned no response body', {
      status: response.status,
      meta,
    });
  }

  const state: StreamState = { text: '', failure: null };
  const iterator = readFrames(body, state, response.status, meta, signal);

  return {
    meta,
    // One iterator, handed out every time: the body is single-use.
    chunks: { [Symbol.asyncIterator]: () => iterator },
    async text(): Promise<string> {
      for (;;) {
        const next = await iterator.next();
        if (next.done === true) break;
      }
      // A failure recorded during iteration is re-thrown on every later read.
      // A truncated answer that looks complete is worse than an error.
      if (state.failure !== null) throw state.failure;
      return state.text;
    },
  };
}

/**
 * True for a cancellation, whichever runtime produced it.
 *
 * An abort is the caller getting what they asked for, not a transport failure:
 * retrying it re-sends a request the caller already abandoned, and on a billed
 * endpoint that is a second charge. Platforms disagree on the class
 * (`DOMException` in browsers and Node's `fetch`, a plain `Error` elsewhere)
 * but agree on `name`.
 */
export function isAbortError(err: unknown): boolean {
  // The SHARED name set, not a local `=== 'AbortError'`.
  //
  // `AbortSignal.timeout()` names its reason `TimeoutError` and the openai
  // client raises `APIUserAbortError`; errors.ts already treats both as
  // aborts, and this exported helper did not. So the same package answered
  // two different things about the same cancellation, and a caller using this
  // one to decide whether to retry a cancelled stream took the wrong branch.
  // One implementation per cross-cutting concern.
  return isAbortLike(err);
}

// ---------------------------------------------------------------------------
// The frame reader
// ---------------------------------------------------------------------------

async function* readFrames(
  body: AsyncIterable<Uint8Array>,
  state: StreamState,
  status: number,
  meta: ResponseMeta,
  signal?: AbortSignal,
): AsyncGenerator<StreamChunk, void, undefined> {
  // ONE decoder for the whole stream, always called with `{ stream: true }`.
  // A multi-byte character can be split across network chunks, and a decoder
  // constructed per chunk (or called without `stream`) emits U+FFFD for the
  // half it sees — the classic source of mojibake that only appears under
  // load, when chunks get small and arrive at arbitrary offsets.
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    for await (const bytes of body) {
      // The signal aborts the transport, but a runner backed by a queue or a
      // buffered iterable can keep yielding after the abort landed. Checking
      // per chunk bounds how much of an abandoned response we keep decoding.
      throwIfAborted(signal);

      buffer +=
        typeof bytes === 'string'
          ? // Some runners (Node streams not in binary mode) hand back strings
            // already. Decoding one would throw; appending it is correct, at
            // the cost of trusting that runner's own decoding.
            (bytes as string)
          : decoder.decode(bytes, { stream: true });

      const split = splitEvents(buffer);
      buffer = split.rest;

      for (const block of split.events) {
        const frame = parseEventBlock(block);
        if (frame === null) continue;

        const outcome = interpret(frame, status, meta);
        if (outcome.kind === 'done') return;
        if (outcome.kind === 'error') throw outcome.error;
        if (outcome.kind === 'skip') continue;

        state.text += outcome.chunk.delta;
        yield outcome.chunk;
      }
    }

    // Flush the decoder. A stream that ends mid-character is malformed, and
    // this is where that surfaces as a replacement char rather than as bytes
    // silently discarded.
    buffer += decoder.decode();

    // A server that closed without the final blank line still delivered its
    // last event.
    for (const frame of parseSSE(buffer)) {
      const outcome = interpret(frame, status, meta);
      if (outcome.kind === 'done') return;
      if (outcome.kind === 'error') throw outcome.error;
      if (outcome.kind === 'skip') continue;

      state.text += outcome.chunk.delta;
      yield outcome.chunk;
    }

    // FELL OFF THE END WITHOUT `data: [DONE]`.
    //
    // Every `return` above is a sentinel we actually saw. Reaching here means
    // the connection closed cleanly mid-answer — a dropped upstream, a proxy
    // idle timeout, a killed worker. The frames already yielded are real and
    // the request was BILLED, so the tokens are not the problem; reporting the
    // result as COMPLETE is. `text()` would hand back a truncated answer that
    // is indistinguishable from a short one, which is the same
    // silently-wrong-and-confident failure the buffered path refuses.
    //
    // Transport, not configuration: the identical request can succeed next
    // time, so this one IS retryable.
    throw transportError(
      'the stream ended without its [DONE] sentinel; the answer is truncated and ' +
        'the request was billed. Retrying is safe.',
      { status, meta },
    );
  } catch (err) {
    // An abort is recorded like any other terminal condition so a later
    // `text()` cannot return the partial answer as if it were whole — but it
    // is re-thrown unwrapped, so `isAbortError` still recognises it and no
    // retry layer mistakes it for a transient failure.
    // An abort and an nRouterError are re-thrown UNWRAPPED — the first so
    // `isAbortError` still recognises it and no retry layer treats it as
    // transient, the second because it is already classified.
    //
    // Anything else is a raw socket or runtime failure escaping out of the
    // body iterator, and rethrowing it meant nr.stream() left the advertised
    // nRouterError hierarchy entirely: `isRetryable` answered false and the
    // status and request id were lost, for a request that DID reach the
    // gateway.
    // `signal.aborted`, not just the error's NAME. `AbortController.abort()`
    // with no argument produces an AbortError, but `abort(new Error('user
    // cancelled'))` propagates that reason verbatim — a generic Error, which
    // the name check missed. It was then wrapped as a transport failure and
    // reported RETRYABLE, so a generic retry loop could resend a billed
    // request the caller had explicitly cancelled (gate 8). The signal is the
    // authority on whether a cancellation happened; the name is only a hint.
    if (err instanceof nRouterError || isAbortError(err) || signal?.aborted) {
      state.failure = err instanceof Error ? err : new Error(String(err));
      throw err;
    }
    const wrapped = transportError(
      `the stream failed while being read (${err instanceof Error ? err.message : String(err)})`,
      { status, meta, cause: err },
    );
    state.failure = wrapped;
    throw wrapped;
  }
}

type FrameOutcome =
  | { kind: 'chunk'; chunk: StreamChunk }
  | { kind: 'skip' }
  | { kind: 'done' }
  | { kind: 'error'; error: nRouterError };

/** Decide what one parsed SSE frame means. */
function interpret(
  frame: { event?: string; data: string },
  status: number,
  meta: ResponseMeta,
): FrameOutcome {
  const data = frame.data.trim();

  // The terminator. It is not JSON and it is not a chunk; parsing it would
  // count as a malformed frame and hide real ones.
  if (data === '' || data === '[DONE]') {
    return data === '[DONE]' ? { kind: 'done' } : { kind: 'skip' };
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(data);
  } catch {
    // A `data:` payload that is not JSON must NOT kill the stream. It is
    // almost always a proxy's keep-alive or a partially-flushed frame from a
    // buffering intermediary, and tokens already delivered are already billed
    // — throwing here would discard a paid-for answer over a cosmetic frame.
    // An in-band error is JSON (see `errorFromValue`), so nothing that matters
    // is dropped by skipping.
    if (frame.event === 'error') {
      // ...unless the server explicitly labelled it an error. Then the payload
      // is unreadable but the verdict is not, and going quiet would truncate.
      return {
        kind: 'error',
        error: createError(truncate(data), { status, meta }),
      };
    }
    return { kind: 'skip' };
  }

  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    return { kind: 'skip' };
  }
  const raw = parsed as Record<string, unknown>;

  // In-band error. VERIFIED shape, from the gateway's own cut-stream frame
  // (`nrouter-rust-gateway/src/http/postcall.rs`, `blocked_sse_frame`):
  //
  //     event: error
  //     data: {"error":{"type":"guardrail_blocked","message":"..."}}
  //
  // The status line is long gone by then — that is what streaming takes away
  // from an output guardrail — so this frame is the ONLY signal that the
  // answer was withheld. A reader that ends the stream quietly hands back a
  // truncated response that looks complete, which is the failure this branch
  // exists to prevent. Both tests are applied: the `event: error` label and a
  // top-level `error` member, because they agree on the gateway's own frame
  // and each catches a shape the other misses.
  if (frame.event === 'error' || raw.error !== undefined) {
    return {
      kind: 'error',
      error: errorFromValue(raw, data, status, meta),
    };
  }

  return { kind: 'chunk', chunk: { delta: extractDelta(raw), raw } };
}

/**
 * The incremental text a frame carried.
 *
 * Two wire shapes, because the gateway serves both `/v1/chat/completions`
 * (OpenAI-shaped: `choices[0].delta.content`) and `/v1/messages`
 * (Anthropic-shaped: a `content_block_delta` carrying `delta.text`). The
 * Anthropic arm is gated on `type` so a `message_delta` — whose `delta` holds
 * a stop reason, not text — cannot be read as content.
 */
function extractDelta(raw: Record<string, unknown>): string {
  const choices = raw.choices;
  if (Array.isArray(choices) && choices.length > 0) {
    const first = choices[0];
    if (typeof first === 'object' && first !== null) {
      const delta = (first as Record<string, unknown>).delta;
      if (typeof delta === 'object' && delta !== null) {
        const content = (delta as Record<string, unknown>).content;
        if (typeof content === 'string') return content;
      }
    }
  }

  if (raw.type === 'content_block_delta') {
    const delta = raw.delta;
    if (typeof delta === 'object' && delta !== null) {
      const text = (delta as Record<string, unknown>).text;
      if (typeof text === 'string') return text;
    }
  }

  return '';
}

// ---------------------------------------------------------------------------
// Error mapping
// ---------------------------------------------------------------------------

/** Classify a non-2xx response body. */
function errorFromBody(
  rawBody: string,
  status: number,
  meta: ResponseMeta,
  retryAfter: number | null = null,
): nRouterError {
  const trimmed = rawBody.trim();
  if (trimmed === '') {
    return createError(`gateway returned HTTP ${status}`, { status, meta, retryAfter });
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    // Not JSON — an intermediary's HTML error page, or a truncated body. The
    // status is still authoritative, so classify on that.
    return createError(truncate(trimmed), { status, meta, retryAfter });
  }
  if (typeof parsed !== 'object' || parsed === null) {
    return createError(truncate(trimmed), { status, meta, retryAfter });
  }
  return errorFromValue(parsed as Record<string, unknown>, trimmed, status, meta, retryAfter);
}

/**
 * Turn a decoded gateway error envelope into a typed error.
 *
 * The gateway's main error path sends NO `code` — it emits
 * `{"error":{"type":"gateway_error","message":…}}` — so `type` is read as the
 * code when `code` is absent. Classifying on `code` alone is what made
 * `guardrail_blocked` unreachable in five SDKs at once; it arrives as `type`.
 */
function errorFromValue(
  value: Record<string, unknown>,
  fallbackText: string,
  status: number,
  meta: ResponseMeta,
  retryAfter: number | null = null,
): nRouterError {
  const inner = value.error;

  if (typeof inner === 'string') {
    return createError(truncate(inner), { status, meta, retryAfter });
  }

  if (typeof inner === 'object' && inner !== null) {
    const err = inner as Record<string, unknown>;
    // `type` is promoted ONLY when it is a stable spec code. The gateway's
    // ordinary error path sends type: "gateway_error", and promoting that
    // hands classifyErrorClass an UNKNOWN code — which takes precedence over
    // the status fallback, so every 400/401/402/429/503 on the streaming path
    // collapsed into a generic error. The guardrail cut is the one frame that
    // really does carry a spec code in `type`.
    const code = typeof err.code === 'string' && err.code
      ? err.code
      : isSpecErrorCode(err.type)
        ? err.type
        : null;
    const message =
      typeof err.message === 'string' && err.message.trim() !== ''
        ? err.message
        : fallbackText;
    return createError(truncate(message), { code, status, meta, retryAfter });
  }

  // Some upstream shapes answer `{"detail": "..."}` rather than `{"error": …}`.
  if (typeof value.detail === 'string') {
    return createError(truncate(value.detail), { status, meta, retryAfter });
  }
  if (typeof value.message === 'string') {
    return createError(truncate(value.message), { status, meta, retryAfter });
  }

  return createError(truncate(fallbackText), { status, meta, retryAfter });
}

function truncate(text: string): string {
  return text.length > MAX_ERROR_MESSAGE_CHARS
    ? `${text.slice(0, MAX_ERROR_MESSAGE_CHARS)}…`
    : text;
}

// ---------------------------------------------------------------------------
// Framing
// ---------------------------------------------------------------------------

/**
 * Take every COMPLETE event out of `buffer`, leaving the partial tail behind.
 *
 * Completeness is the whole point: a network chunk can end anywhere, including
 * inside an event, inside a `data:` line, or between the `\r` and the `\n` of
 * a CRLF. Only a fully-matched separator consumes bytes, so a dangling `\r`
 * stays in `rest` and is reconsidered once the next chunk arrives.
 */
function splitEvents(buffer: string): { events: string[]; rest: string } {
  const events: string[] = [];
  let rest = buffer;

  for (;;) {
    const match = EVENT_SEPARATOR.exec(rest);
    if (match === null) break;
    events.push(rest.slice(0, match.index));
    rest = rest.slice(match.index + match[0].length);
  }

  return { events, rest };
}

/** Parse one event block. Returns null when it carried no `data:` line. */
function parseEventBlock(block: string): { event?: string; data: string } | null {
  let event: string | undefined;
  const dataLines: string[] = [];

  for (const line of block.split(LINE_SEPARATOR)) {
    if (line === '') continue;
    // A line starting with a colon is a comment. Proxies send these as
    // keep-alives; treating one as a field would produce an empty-named field.
    if (line.startsWith(':')) continue;

    const colon = line.indexOf(':');
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? '' : line.slice(colon + 1);
    // Exactly ONE leading space is part of the framing; a second belongs to
    // the payload and stripping it would corrupt indented text.
    if (value.startsWith(' ')) value = value.slice(1);

    if (field === 'data') dataLines.push(value);
    else if (field === 'event') event = value;
    // `id:` and `retry:` are ignored — the gateway does not resume streams, so
    // there is nothing this SDK could do with either.
  }

  if (dataLines.length === 0) return null;
  const data = dataLines.join('\n');
  return event === undefined ? { data } : { event, data };
}

// ---------------------------------------------------------------------------
// Cancellation
// ---------------------------------------------------------------------------

function throwIfAborted(signal?: AbortSignal): void {
  if (signal === undefined || !signal.aborted) return;

  // Prefer the platform's own reason, so a caller that aborted with a typed
  // reason gets it back unchanged.
  const reason: unknown = (signal as { reason?: unknown }).reason;
  if (reason instanceof Error) throw reason;

  const err = new Error('the request was aborted');
  // The name is the cross-runtime contract every retry layer checks. Set it
  // explicitly so a cancellation is never counted as a retryable failure.
  err.name = 'AbortError';
  throw err;
}

/** One raw header value out of any of the three shapes a runner may hand back. */
function headerValue(headers: HeaderSource, name: string): string | null {
  if (typeof (headers as { get?: unknown }).get === 'function') {
    return (headers as { get(n: string): string | null | undefined }).get(name) ?? null;
  }
  // CASE-INSENSITIVE over the record's own keys. HTTP header names are
  // case-insensitive on the wire, and a hand-written StreamRunner returning a
  // plain object very reasonably spells it `Retry-After` — which an exact
  // lowercase lookup missed, so a streaming 429 came back with retryAfter null
  // and the caller retried immediately against the limit that just refused
  // them. The buffered and multimodal paths already normalize; this one did
  // not.
  const record = headers as Record<string, string | string[] | undefined>;
  const wanted = name.toLowerCase();
  for (const key of Object.keys(record)) {
    if (key.toLowerCase() !== wanted) continue;
    const raw = record[key];
    const single = Array.isArray(raw) ? raw[0] : raw;
    return single ?? null;
  }
  return null;
}
