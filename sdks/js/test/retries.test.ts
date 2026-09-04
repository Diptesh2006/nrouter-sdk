// Client-side retries on billed calls, counted at the transport.
//
// THE GAP THIS FILE CLOSES. `NRouterSurface.raw()` has pinned `maxRetries: 0`
// on every non-GET since the beginning, and `client.test.ts` proved it for
// `nr.chat`. But `raw()` is only reached by the `nr.*` helpers. Every INHERITED
// vendor resource — `chat.completions.create`, `responses.create`,
// `embeddings.create`, `images.generate`, `audio.speech.create`,
// `audio.transcriptions.create` — goes straight to the vendor pipeline and used
// the vendor's own default of two retries. MEASURED on this package against a
// 503 before the fix: `nr.chat` 1 attempt, `chat.completions.create` 3. All of
// those are billed, non-idempotent POSTs, and `chat.completions.create` is the
// call the README quickstart shows first.
//
// Gateway gate 8: a retry is a second call and a second BILL. The gateway
// reserves credit exactly once per customer request and owns retry and failover
// on its own side; a 503 or a timeout may arrive after it already accepted,
// dispatched and billed the request, so the retry buys a second answer nobody
// asked for.
//
// EVERY ASSERTION HERE COUNTS HTTP ATTEMPTS. None reads back a constructor
// argument: `maxRetries: 0` sitting on the options object proves the value was
// stored, not that it reached the retry loop.

const { test } = require('node:test');
const assert = require('node:assert/strict');

const { nRouter } = require('../dist/index');
// Not re-exported from the package entry point — read it where it is defined,
// the same way the other suites reach `../dist/meta` and `../dist/options`.
const { DEFAULT_MAX_RETRIES } = require('../dist/client');
const { toFile } = require('openai/uploads');

// Assembled from parts so the literal never looks like a real credential to a
// secret scanner. It is not one — the transport below is a fake.
const TEST_KEY = 'sk-nrouter-' + 'test0000000000000abcd';

type ClientOptions = { maxRetries?: number };

/**
 * Run `call` against a transport that answers 503 to everything and counts each
 * attempt it is handed. 503 is retryable to every client that retries at all,
 * so a count above 1 is a retry and nothing else.
 */
async function attempts(
  call: (client: any) => Promise<unknown>,
  options: ClientOptions = {},
): Promise<number> {
  let seen = 0;
  const client = new nRouter({
    apiKey: TEST_KEY,
    // maxRetries deliberately absent unless a case supplies one: the DEFAULT is
    // what is under test.
    ...options,
    fetch: async (url: unknown) => {
      // COUNT ONLY REAL REQUESTS. MEASURED: the vendor client probes its
      // runtime with `fetch('data:,')` before a multipart upload, so a naive
      // counter reads 2 attempts for one POST and the failure looks like a
      // retry that is not there.
      if (String(url).startsWith('http')) seen += 1;
      return new Response(JSON.stringify({ error: { message: 'upstream blip' } }), {
        status: 503,
        headers: { 'content-type': 'application/json' },
      });
    },
  });
  await assert.rejects(() => call(client));
  return seen;
}

/**
 * Every billed non-GET this client can send, by the name a customer types.
 *
 * The two halves are the point: the `nr.*` rows were already covered by
 * `raw()`, the `client.*` rows were the gap. They are tested through ONE table
 * so a future reader cannot fix one half and believe the property holds.
 */
const BILLED_POSTS: [string, (client: any) => Promise<unknown>][] = [
  // Inherited vendor resources — the OpenAI-compatible surface.
  ['chat.completions.create', (c) => c.chat.completions.create({ model: 'm', messages: [{ role: 'user', content: 'x' }] })],
  ['completions.create', (c) => c.completions.create({ model: 'm', prompt: 'x' })],
  ['responses.create', (c) => c.responses.create({ model: 'm', input: 'x' })],
  ['embeddings.create', (c) => c.embeddings.create({ model: 'm', input: 'x' })],
  ['images.generate', (c) => c.images.generate({ model: 'm', prompt: 'x' })],
  // BINARY response path: an mp3 comes back, not JSON.
  ['audio.speech.create', (c) => c.audio.speech.create({ model: 'm', input: 'x', voice: 'alloy' })],
  // MULTIPART request path: a file goes up. A retry here re-uploads the whole
  // body as well as re-billing the transcription.
  [
    'audio.transcriptions.create (multipart)',
    async (c) => c.audio.transcriptions.create({ file: await toFile(Buffer.from('RIFF'), 'a.mp3'), model: 'whisper-1' }),
  ],
  // The nRouter-native surface, through NRouterSurface.raw().
  ['nr.chat', (c) => c.nr.chat({ model: 'm', prompt: 'x' })],
  ['nr.stream', (c) => c.nr.stream({ model: 'm', prompt: 'x' })],
  ['nr.responses', (c) => c.nr.responses({ model: 'm', input: 'x' })],
  ['nr.messages', (c) => c.nr.messages({ model: 'm', max_tokens: 8, messages: [] })],
  ['nr.media.image', (c) => c.nr.media.image({ model: 'm', prompt: 'x' })],
  ['nr.media.video', (c) => c.nr.media.video({ model: 'm', prompt: 'x' })],
  // nr.media multipart and binary.
  [
    'nr.media.transcribe (multipart)',
    (c) => c.nr.media.transcribe({ model: 'whisper-1', file: new Uint8Array([1, 2, 3]), fileName: 'a.mp3' }),
  ],
  ['nr.media.speech (binary)', (c) => c.nr.media.speech({ model: 'm', input: 'x', voice: 'alloy' })],
];

for (const [name, call] of BILLED_POSTS) {
  test(`${name} is sent exactly once on a retryable failure`, async () => {
    const seen = await attempts(call);
    assert.equal(
      seen,
      1,
      `${name} made ${seen} HTTP attempts on a 503; every one past the first is a second reservation and a second bill`,
    );
  });
}

// THE STRUCTURAL HALF, and the reason a table alone is not enough: the table
// can only cover helpers that exist today. A helper added tomorrow is safe
// because the CLIENT default is zero, not because someone remembered to pin it
// per request. Deleting the constructor default turns this red even if nobody
// touches the table.
test('a new POST helper cannot ship with vendor retries on: the client default is zero', () => {
  const client = new nRouter({ apiKey: TEST_KEY, fetch: async () => new Response('{}') });
  assert.equal(DEFAULT_MAX_RETRIES, 0);
  assert.equal(
    client.maxRetries,
    0,
    'the vendor default of 2 is inherited by every resource this SDK does not wrap by hand',
  );
});

// The default is a default, not a ceiling.
test('an explicit maxRetries is honoured on an inherited POST', async () => {
  assert.equal(await attempts((c) => c.chat.completions.create({ model: 'm', messages: [] }), { maxRetries: 2 }), 3);
});

// The per-method split survives: a caller who raises maxRetries for their own
// reads does not thereby re-arm a billed nr.* POST, because raw() pins it.
test('raising maxRetries retries a GET but never an nr.* billed POST', async () => {
  assert.equal(await attempts((c) => c.models.list(), { maxRetries: 2 }), 3, 'a GET follows the caller');
  assert.equal(await attempts((c) => c.nr.chat({ model: 'm', prompt: 'x' }), { maxRetries: 2 }), 1, 'a billed nr.* POST does not');
});
