// Case 13 — SSE framing.
//
// Every bug this file guards against reproduces only under a SPECIFIC byte
// split, which is exactly what a fake runner can produce on demand and a live
// call cannot:
//
//   * an event straddling two network chunks must reassemble, not be dropped
//     and not be parsed twice;
//   * `data: [DONE]` terminates the stream, and is not a malformed frame;
//   * a non-JSON `data:` line must NOT kill the stream — it is almost always a
//     buffering proxy's keep-alive, and throwing there discards tokens the
//     customer has already been billed for;
//   * an abort must actually stop the iteration, and must never be reported as
//     a retryable failure (retrying re-sends a request the caller abandoned,
//     which on a billed endpoint is a second charge).

const { test } = require('node:test');
const assert = require('node:assert/strict');
const { inspect } = require('node:util');

const { parseSSE, streamChat, isAbortError } = require('../dist/stream');
const { nRouterError, isRetryable, transportError } = require('../dist/errors');

const encoder = new TextEncoder();

/** A StreamRunner whose body yields exactly the chunks given, in order. */
function chunkRunner(
  chunks: string[],
  init: { status?: number; headers?: Record<string, string>; text?: string } = {}
) {
  const seen: { path?: string; body?: Record<string, unknown>; signal?: AbortSignal } = {};
  return {
    seen,
    open(path: string, body: unknown, signal?: AbortSignal) {
      seen.path = path;
      seen.body = body as Record<string, unknown>;
      seen.signal = signal;
      return Promise.resolve({
        status: init.status ?? 200,
        headers: init.headers ?? {},
        body:
          init.status !== undefined && (init.status < 200 || init.status >= 300)
            ? null
            : (async function* () {
                for (const chunk of chunks) {
                  yield encoder.encode(chunk);
                }
              })(),
        text: () => Promise.resolve(init.text ?? ''),
      });
    },
  };
}

const frame = (text: string) =>
  `data: ${JSON.stringify({ choices: [{ delta: { content: text } }] })}\n\n`;

async function collect(chunks: AsyncIterable<{ delta: string }>): Promise<string[]> {
  const out: string[] = [];
  for await (const chunk of chunks) out.push(chunk.delta);
  return out;
}

async function rejection(promise: Promise<unknown>): Promise<any> {
  try {
    await promise;
  } catch (err) {
    return err;
  }
  throw new Error('expected a rejection, got a resolved promise');
}

// ---------------------------------------------------------------------------
// parseSSE — the framing primitive.
// ---------------------------------------------------------------------------

test('parseSSE reads data, event and multi-line data', () => {
  assert.deepEqual(parseSSE('data: hello\n\n'), [{ data: 'hello' }]);
  assert.deepEqual(parseSSE('event: error\ndata: boom\n\n'), [{ event: 'error', data: 'boom' }]);
  // Several data lines in one event join with a newline, per the SSE spec.
  assert.deepEqual(parseSSE('data: a\ndata: b\n\n'), [{ data: 'a\nb' }]);
});

test('parseSSE strips exactly ONE leading space after the colon', () => {
  // A second space belongs to the payload; stripping it corrupts indented text.
  assert.deepEqual(parseSSE('data:  indented\n\n'), [{ data: ' indented' }]);
  assert.deepEqual(parseSSE('data:tight\n\n'), [{ data: 'tight' }]);
});

test('parseSSE drops comment keep-alives and fields it cannot act on', () => {
  // `: keep-alive` from a proxy, and `id:`/`retry:` — the gateway does not
  // resume streams, so an id there is noise.
  assert.deepEqual(parseSSE(': keep-alive\n\ndata: real\n\n'), [{ data: 'real' }]);
  assert.deepEqual(parseSSE('id: 7\nretry: 100\ndata: real\n\n'), [{ data: 'real' }]);
});

test('parseSSE keeps a trailing event a server closed without a blank line', () => {
  // Dropping it loses the last token, or the `[DONE]` that says the answer is
  // complete.
  assert.deepEqual(parseSSE('data: a\n\ndata: [DONE]'), [{ data: 'a' }, { data: '[DONE]' }]);
});

test('parseSSE handles all three line endings', () => {
  for (const [lf, blank] of [
    ['\n', '\n\n'],
    ['\r\n', '\r\n\r\n'],
    ['\r', '\r\r'],
  ]) {
    assert.deepEqual(
      parseSSE(`event: x${lf}data: y${blank}`),
      [{ event: 'x', data: 'y' }],
      `line ending ${JSON.stringify(lf)}`
    );
  }
});

// ---------------------------------------------------------------------------
// Chunk boundaries.
// ---------------------------------------------------------------------------

// Every OpenAI-protocol stream ends with this, and the gateway relays it
// (nrouter-rust-gateway chat_completions.rs:783). A stream that stops without
// it is truncated, and the SDK now refuses it — so a test that omits it is
// testing a failure mode, not the one it means to.
const DONE = 'data: [DONE]\n\n';

test('an event SPLIT ACROSS TWO NETWORK CHUNKS reassembles', async () => {
  const whole = frame('hello world') + DONE;
  const cut = Math.floor(whole.length / 2);
  const res = await streamChat(chunkRunner([whole.slice(0, cut), whole.slice(cut)]), {
    model: 'm',
    prompt: 'hi',
  });
  assert.deepEqual(await collect(res.chunks), ['hello world']);
});

test('a split at EVERY offset of a two-event stream still yields both', async () => {
  // The strong form: a buffer that is flushed rather than carried forward
  // fails at exactly one of these offsets, which is why a single hand-picked
  // split proves very little.
  const whole = frame('alpha') + frame('beta') + 'data: [DONE]\n\n';
  for (let cut = 1; cut < whole.length; cut += 1) {
    const res = await streamChat(chunkRunner([whole.slice(0, cut), whole.slice(cut)]), {
      model: 'm',
      prompt: 'hi',
    });
    assert.deepEqual(await collect(res.chunks), ['alpha', 'beta'], `split at offset ${cut}`);
  }
});

test('a CRLF split between the \\r and the \\n does not merge two events', async () => {
  // Treating a dangling `\r` as a line end merges the events when the next
  // chunk opens with `\n`.
  const whole = `data: {"choices":[{"delta":{"content":"a"}}]}\r\n\r\ndata: {"choices":[{"delta":{"content":"b"}}]}\r\n\r\n${DONE}`;
  const cut = whole.indexOf('\r\n\r\n') + 3; // between the second \r and its \n
  const res = await streamChat(chunkRunner([whole.slice(0, cut), whole.slice(cut)]), {
    model: 'm',
    prompt: 'hi',
  });
  assert.deepEqual(await collect(res.chunks), ['a', 'b']);
});

test('a multi-byte character split across chunks is not mojibake', async () => {
  // One TextDecoder for the whole stream, always with { stream: true }. A
  // per-chunk decoder emits U+FFFD for the half it sees — the classic bug that
  // only appears under load, when chunks get small.
  const whole = frame('héllo — ok') + DONE;
  const bytes = encoder.encode(whole);
  // Split inside the em-dash's UTF-8 sequence.
  const dash = whole.indexOf('—');
  const byteCut = encoder.encode(whole.slice(0, dash)).length + 1;
  const runner = {
    open() {
      return Promise.resolve({
        status: 200,
        headers: {},
        body: (async function* () {
          yield bytes.slice(0, byteCut);
          yield bytes.slice(byteCut);
        })(),
      });
    },
  };
  const res = await streamChat(runner, { model: 'm', prompt: 'hi' });
  assert.deepEqual(await collect(res.chunks), ['héllo — ok']);
});

// ---------------------------------------------------------------------------
// [DONE] and unparseable data lines.
// ---------------------------------------------------------------------------

test('data: [DONE] TERMINATES the stream', async () => {
  const res = await streamChat(
    chunkRunner([frame('a'), 'data: [DONE]\n\n', frame('never')]),
    { model: 'm', prompt: 'hi' }
  );
  assert.deepEqual(
    await collect(res.chunks),
    ['a'],
    'nothing after the terminator may be yielded'
  );
});

test('[DONE] is not reported as a malformed frame', async () => {
  const res = await streamChat(chunkRunner(['data: [DONE]\n\n']), { model: 'm', prompt: 'hi' });
  assert.equal(await res.text(), '');
});

test('a NON-JSON data: line does not kill the stream', async () => {
  // Tokens already delivered are already billed; throwing over a proxy's
  // cosmetic frame discards a paid-for answer.
  const res = await streamChat(
    chunkRunner([frame('a'), 'data: not-json-at-all\n\n', frame('b'), 'data: [DONE]\n\n']),
    { model: 'm', prompt: 'hi' }
  );
  assert.deepEqual(await collect(res.chunks), ['a', 'b']);
});

test('an in-band `event: error` frame DOES stop the stream, typed', async () => {
  // Streaming takes the status line away from an output guardrail, so this
  // frame is the ONLY signal that the answer was withheld. Ending quietly
  // hands back a truncated response that looks complete.
  const res = await streamChat(
    chunkRunner([
      frame('partial'),
      'event: error\ndata: {"error":{"type":"guardrail_blocked","message":"denied"}}\n\n',
    ]),
    { model: 'm', prompt: 'hi' }
  );
  const err = await rejection(collect(res.chunks));
  assert.ok(err instanceof nRouterError, `expected an nRouterError, got ${err}`);
  assert.equal(err.name, 'nRouterGuardrailBlockedError');
});

test('a failure during iteration is re-thrown by text(), never swallowed', async () => {
  const res = await streamChat(
    chunkRunner([
      frame('partial'),
      'event: error\ndata: {"error":{"type":"guardrail_blocked","message":"denied"}}\n\n',
    ]),
    { model: 'm', prompt: 'hi' }
  );
  const err = await rejection(res.text());
  assert.ok(err instanceof nRouterError, 'a truncated answer that looks complete is worse than an error');
});

// ---------------------------------------------------------------------------
// Metadata and non-2xx.
// ---------------------------------------------------------------------------

test('stream metadata is read from the headers before the body is touched', async () => {
  const res = await streamChat(
    chunkRunner([frame('a'), 'data: [DONE]\n\n'], {
      headers: { 'x-nr-request-id': 'nrouter-stream', 'x-nr-cost-status': 'unpriced' },
    }),
    { model: 'm', prompt: 'hi' }
  );
  assert.equal(res.meta.requestId, 'nrouter-stream');
  assert.equal(res.meta.cost, null, 'a stream has no settled cost yet; 0 would claim a free request');
  assert.equal(await res.text(), 'a');
});

test('streamChat sets stream: true itself and never lets the caller unset it', async () => {
  const runner = chunkRunner(['data: [DONE]\n\n']);
  await streamChat(runner, { model: 'm', prompt: 'hi' });
  assert.equal(runner.seen.body?.stream, true);
  assert.equal(runner.seen.path, '/chat/completions', 'the base URL already carries /v1');
});

test('a non-2xx throws a typed error BEFORE any streaming begins', async () => {
  const err = await rejection(
    streamChat(
      chunkRunner([], {
        status: 402,
        headers: { 'x-nr-request-id': 'nrouter-402' },
        text: JSON.stringify({ error: { code: 'insufficient_credits', message: 'top up' } }),
      }),
      { model: 'm', prompt: 'hi' }
    )
  );
  assert.ok(err instanceof nRouterError);
  assert.equal(err.name, 'nRouterCreditError');
  assert.equal(err.requestId, 'nrouter-402');
  assert.equal(err.status, 402, 'the response arrived; status must not read as "never sent"');
});

// ---------------------------------------------------------------------------
// Abort.
// ---------------------------------------------------------------------------

test('an ALREADY-aborted signal refuses before the runner is called', async () => {
  const controller = new AbortController();
  controller.abort();
  const runner = chunkRunner([frame('a')]);
  const err = await rejection(streamChat(runner, { model: 'm', prompt: 'hi' }, controller.signal));
  assert.equal(isAbortError(err) || err?.name === 'AbortError', true, `got ${err}`);
  assert.equal(runner.seen.path, undefined, 'nothing may be sent for a request already abandoned');
});

test('aborting MID-STREAM actually stops the iteration', async () => {
  const controller = new AbortController();
  // A runner that keeps producing after the abort lands, which is what a
  // queue-backed or buffered iterable really does.
  const runner = {
    open() {
      return Promise.resolve({
        status: 200,
        headers: {},
        body: (async function* () {
          for (let i = 0; i < 100; i += 1) {
            yield encoder.encode(frame(`t${i}`));
          }
        })(),
      });
    },
  };
  const res = await streamChat(runner, { model: 'm', prompt: 'hi' }, controller.signal);

  const seen: string[] = [];
  const err = await rejection(
    (async () => {
      for await (const chunk of res.chunks) {
        seen.push(chunk.delta);
        if (seen.length === 3) controller.abort();
      }
    })()
  );

  assert.equal(isAbortError(err) || err?.name === 'AbortError', true, `got ${err}`);
  assert.ok(seen.length < 100, `the abort did not stop iteration: ${seen.length} chunks decoded`);
});

test('an abort is never retryable', async () => {
  // The caller asked to stop. A retry re-sends a request they abandoned, and
  // on a billed endpoint that is a second charge.
  const abort = new Error('aborted');
  abort.name = 'AbortError';
  assert.equal(isAbortError(abort), true);
  assert.equal(isRetryable(abort), false, 'a bare abort is not an nRouterError and is not retryable');

  const { nRouterTransportError } = require('../dist/errors');
  assert.equal(isRetryable(new nRouterTransportError('gave up', { cause: abort })), false);
});

// A stream that stops mid-answer without its sentinel is TRUNCATED, and the
// request was billed. Returning the partial text as if it were whole is the
// same silently-wrong-and-confident failure the buffered path refuses.
test('a stream that ends without [DONE] is refused, not reported complete', async () => {
  const res = await streamChat(chunkRunner([frame('half an ans')]), { model: 'm', prompt: 'hi' });
  await assert.rejects(
    async () => {
      for await (const _ of res.chunks) { /* drain */ }
    },
    (err: unknown) => {
      assert.ok(err instanceof nRouterError, 'a typed error');
      assert.equal(isRetryable(err), true, 'the same request can succeed next time');
      assert.match((err as Error).message, /\[DONE\]/);
      return true;
    },
  );
});

test('...and text() re-throws rather than handing back the truncated answer', async () => {
  const res = await streamChat(chunkRunner([frame('half an ans')]), { model: 'm', prompt: 'hi' });
  await assert.rejects(async () => { for await (const _ of res.chunks) { /* drain */ } });
  await assert.rejects(() => res.text(), /\[DONE\]/);
});

// Rule #5: a fetch failure commonly holds the originating Request — headers
// included — so a RAW cause makes console.error(err) print the Authorization
// value. Neither toJSON nor message redaction covers that path.
test('a sanitized cause cannot carry the Authorization header into a log', () => {
  const leaky: Error & { request?: unknown } = new Error('socket hang up');
  leaky.name = 'AbortError';
  leaky.request = { headers: { authorization: 'Bearer sk-nrouter-secrettail1234' } };

  const err = transportError('the stream failed', { cause: leaky });
  const rendered = inspect(err, { depth: 10 });
  assert.ok(!rendered.includes('secrettail1234'), `the key leaked:\n${rendered}`);
  assert.ok(!rendered.includes('Bearer'), `an Authorization header leaked:\n${rendered}`);
  // ...and the abort is still recognisable, which is what the name is for.
  assert.equal(isRetryable(err), false, 'an abort must stay non-retryable through a sanitized cause');
});

// The buffered and media paths honour Retry-After; the streaming path returned
// null for it, so a caller could not respect the backoff the gateway asked for.
test('a streaming 429 carries its Retry-After', async () => {
  const runner = {
    open: async () => ({
      status: 429,
      headers: { 'content-type': 'application/json', 'retry-after': '42' },
      body: null,
      text: async () => JSON.stringify({ error: { code: 'rate_limit_exceeded', message: 'slow' } }),
    }),
  };
  await assert.rejects(
    () => streamChat(runner as never, { model: 'm', prompt: 'x' }),
    (err: unknown) => {
      assert.equal((err as { retryAfter?: number | null }).retryAfter, 42);
      return true;
    },
  );
});

// A socket that dies WHILE the body is being read. Rethrowing it raw meant
// nr.stream() left the advertised nRouterError hierarchy entirely: isRetryable
// answered false and the status and request id were lost, for a request that
// DID reach the gateway and was billed for what it delivered.
test('a raw failure out of the body iterator is normalized, not leaked', async () => {
  const runner = {
    open: async () => ({
      status: 200,
      headers: { 'content-type': 'text/event-stream', 'x-nr-request-id': 'nrouter-cut' },
      body: (async function* () {
        yield new TextEncoder().encode('data: {"choices":[{"delta":{"content":"par"}}]}\n\n');
        throw new Error('ECONNRESET');
      })(),
    }),
  };
  const res = await streamChat(runner as never, { model: 'm', prompt: 'x' });
  await assert.rejects(
    async () => {
      for await (const _ of res.chunks) { /* drain */ }
    },
    (err: unknown) => {
      assert.ok(err instanceof nRouterError, 'must stay inside the nRouterError hierarchy');
      const e = err as { status?: number | null; requestId?: string | null };
      assert.equal(e.status, 200, 'the response DID arrive');
      assert.equal(e.requestId, 'nrouter-cut', 'the request id must survive');
      assert.equal(isRetryable(err), true, 'a dropped socket can succeed on a retry');
      return true;
    },
  );
});

// AbortController.abort() with no argument yields an AbortError; abort(reason)
// propagates the reason VERBATIM — a generic Error the name check missed. It
// was then wrapped as a retryable transport failure, so a retry loop could
// resend a billed request the caller had explicitly cancelled.
test('a CUSTOM abort reason is still a cancellation, not a retryable failure', async () => {
  const controller = new AbortController();
  const runner = {
    open: async () => ({
      status: 200,
      headers: { 'content-type': 'text/event-stream' },
      body: (async function* () {
        yield new TextEncoder().encode('data: {"choices":[{"delta":{"content":"a"}}]}\n\n');
        controller.abort(new Error('the user navigated away'));
        yield new TextEncoder().encode('data: {"choices":[{"delta":{"content":"b"}}]}\n\n');
      })(),
    }),
  };
  const res = await streamChat(runner as never, { model: 'm', prompt: 'x' }, controller.signal);
  await assert.rejects(
    async () => {
      for await (const _ of res.chunks) { /* drain */ }
    },
    (err: unknown) => {
      assert.equal(isRetryable(err), false, 'a cancelled request must never be resent — it was billed');
      return true;
    },
  );
});

// HTTP header names are case-insensitive on the wire, and a hand-written
// runner returning a plain object reasonably spells it `Retry-After`. An exact
// lowercase lookup missed it, so the caller retried immediately against the
// limit that had just refused them.
test('Retry-After is found whatever case the runner spells it in', async () => {
  for (const spelling of ['retry-after', 'Retry-After', 'RETRY-AFTER']) {
    const runner = {
      open: async () => ({
        status: 429,
        headers: { 'content-type': 'application/json', [spelling]: '42' },
        body: null,
        text: async () => JSON.stringify({ error: { code: 'rate_limit_exceeded', message: 'slow' } }),
      }),
    };
    await assert.rejects(
      () => streamChat(runner as never, { model: 'm', prompt: 'x' }),
      (err: unknown) => {
        assert.equal((err as { retryAfter?: number | null }).retryAfter, 42, `spelling: ${spelling}`);
        return true;
      },
    );
  }
});

// errors.ts already treats TimeoutError and APIUserAbortError as aborts. This
// exported helper recognised only 'AbortError', so the same package answered
// two different things about the same cancellation and a caller using this one
// to decide whether to retry took the wrong branch.
test('isAbortError knows every name a runtime gives a cancellation', () => {
  for (const name of ['AbortError', 'TimeoutError', 'APIUserAbortError']) {
    const err = new Error('cancelled');
    err.name = name;
    assert.equal(isAbortError(err), true, `should recognise ${name}`);
  }
  const other = new Error('ECONNRESET');
  other.name = 'TypeError';
  assert.equal(isAbortError(other), false, 'must not swallow a real failure');
});

// ---------------------------------------------------------------------------
// THE ANTHROPIC WIRE, STREAMED — and the missing usage opt-in.
//
// Two defects, both measured, both silent:
//
//  1. `streamChat` hardcoded `/chat/completions`. The gateway declares
//     `chat_completions: None` for Anthropic and Bedrock, so `nr.stream()`
//     404'd on every Claude id in a package whose own keywords advertise them.
//
//  2. Anthropic's Messages stream has NO `data: [DONE]` sentinel — it ends on
//     `event: message_stop`. Reaching the end of the body without `[DONE]` is
//     this module's truncation refusal, so even once the path was right every
//     COMPLETE Claude stream would end by throwing "the answer is truncated"
//     over an answer that was whole.
//
//  3. (P1) The playground sends `stream_options: {include_usage: true}` on
//     every OpenAI stream and writes down why: the gateway injects it for
//     credit settlement, but a client that depends on that injection shows `-`
//     for every token count the day a rebuilt payload drops the usage chunk.
//     This SDK sent it nowhere. It must NOT go to Anthropic, which rejects the
//     key outright — "stream_options: Extra inputs are not permitted" is a
//     live 400 the app recorded.
// ---------------------------------------------------------------------------

/** The Anthropic Messages SSE sequence for a complete two-token answer. */
const ANTHROPIC_STREAM = [
  'event: message_start\ndata: {"type":"message_start","message":{"id":"msg_1","usage":{"input_tokens":9}}}\n\n',
  'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hel"}}\n\n',
  'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"lo"}}\n\n',
  'event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":2}}\n\n',
  'event: message_stop\ndata: {"type":"message_stop"}\n\n',
];

test('a streamed Claude request opens /messages with a translated body', async () => {
  const runner = chunkRunner(ANTHROPIC_STREAM);
  const result = await streamChat(runner, {
    model: 'claude-sonnet-4-5',
    systemPrompt: 'be brief',
    prompt: 'hi',
  });
  await result.text();

  assert.equal(runner.seen.path, '/messages');
  const body = runner.seen.body as any;
  assert.equal(body.stream, true);
  assert.equal(body.system, 'be brief', 'system must leave `messages`');
  assert.equal(body.max_tokens, 1024, 'Anthropic requires max_tokens');
  assert.equal(
    body.stream_options,
    undefined,
    'Anthropic 400s on stream_options: "Extra inputs are not permitted"',
  );
});

test('message_stop ends a Claude stream WITHOUT the truncation refusal', async () => {
  const runner = chunkRunner(ANTHROPIC_STREAM);
  const result = await streamChat(runner, { model: 'claude-sonnet-4-5', prompt: 'hi' });
  // The empty-box case: tokens billed, nothing rendered.
  assert.equal(await result.text(), 'Hello');
});

test('response.completed ends a Responses stream WITHOUT the truncation refusal', async () => {
  const runner = chunkRunner([
    'data: {"choices":[{"text":"Hello completions"}]}\n\n',
    'data: {"type":"response.completed"}\n\n',
  ]);
  const result = await streamChat(runner, { model: 'gpt-4o', prompt: 'hi' });
  assert.equal(await result.text(), 'Hello completions');
});

test('a Claude stream cut before message_stop is still reported as truncated', async () => {
  // The refusal must narrow to Anthropic's real terminator, not disappear:
  // a dropped upstream still hands back a partial answer that reads as whole.
  const runner = chunkRunner(ANTHROPIC_STREAM.slice(0, 3));
  const result = await streamChat(runner, { model: 'claude-sonnet-4-5', prompt: 'hi' });
  const err = await rejection(result.text());
  assert.ok(err instanceof nRouterError);
  assert.match(err.message, /truncated/);
  assert.equal(isRetryable(err), true);
});

test('an OpenAI stream asks for the usage chunk it would otherwise never get', async () => {
  const runner = chunkRunner([frame('hi'), 'data: [DONE]\n\n']);
  const result = await streamChat(runner, { model: 'gpt-4o-mini', prompt: 'hi' });
  await result.text();

  assert.equal(runner.seen.path, '/chat/completions');
  assert.deepEqual((runner.seen.body as any).stream_options, { include_usage: true });
});

test('a caller-supplied stream_options is never overwritten', async () => {
  // `extra` is the escape hatch for a gateway or provider field this SDK does
  // not model. Stamping our default over it would make the hatch a lie.
  const runner = chunkRunner([frame('hi'), 'data: [DONE]\n\n']);
  const result = await streamChat(runner, {
    model: 'gpt-4o-mini',
    prompt: 'hi',
    extra: { stream_options: { include_usage: false } },
  });
  await result.text();
  assert.deepEqual((runner.seen.body as any).stream_options, { include_usage: false });
});

test('n > 1 on a streamed Claude request is refused before the socket opens', async () => {
  const runner = chunkRunner(ANTHROPIC_STREAM);
  const err = await rejection(
    streamChat(runner, { model: 'claude-sonnet-4-5', prompt: 'hi', extra: { n: 3 } }),
  );
  assert.equal(err.name, 'nRouterConfigurationError');
  assert.equal(isRetryable(err), false);
  assert.equal(runner.seen.path, undefined, 'the refusal must precede the billed call');
});

test('an in-band Anthropic error frame still cuts the stream', async () => {
  // `message_stop` must not be read so eagerly that the guardrail cut ahead of
  // it is skipped — that frame is the only signal the answer was withheld.
  const runner = chunkRunner([
    ANTHROPIC_STREAM[0],
    ANTHROPIC_STREAM[1],
    'event: error\ndata: {"type":"error","error":{"type":"guardrail_blocked","message":"withheld"}}\n\n',
    ANTHROPIC_STREAM[4],
  ]);
  const result = await streamChat(runner, { model: 'claude-sonnet-4-5', prompt: 'hi' });
  const err = await rejection(result.text());
  assert.equal(err.name, 'nRouterGuardrailBlockedError');
});
