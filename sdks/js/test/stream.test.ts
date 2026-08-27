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

const { parseSSE, streamChat, isAbortError } = require('../dist/stream');
const { nRouterError, isRetryable } = require('../dist/errors');

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
