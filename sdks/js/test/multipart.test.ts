// Case 14 — a multipart filename or field name carrying CR/LF must never put a
// raw line break on the wire.
//
// Ported from sdks/go/client_test.go's TestMultipartRefusesHeaderInjection.
// Go's `mime/multipart` escapes quotes and backslashes in a
// Content-Disposition parameter but NOT line breaks, so a CR or LF there
// terminates the header and injects whatever follows — and filenames come from
// user uploads. The Go SDK therefore has to REFUSE before sending.
//
// The property under test is the wire, not the mechanism. Two implementations
// satisfy it and this file accepts either:
//
//   (a) refuse before anything is sent (what the Go SDK does), or
//   (b) escape, so the break can never terminate a header.
//
// Measured on this package at the time of writing: the JS path takes (b) —
// `formdata-node`, which the `openai` dependency uses, percent-encodes the
// break to `%0D%0A`. That is a property of the ENCODER, not of anything this
// SDK wrote, which is exactly why it needs a test: swapping the transport for
// a hand-rolled multipart builder — the obvious "drop a dependency" change —
// reintroduces the Go bug with no other symptom.

const { test } = require('node:test');
const assert = require('node:assert/strict');

const { nRouter } = require('../dist/index');
const { toFile } = require('openai/uploads');

// Assembled from parts so the literal never looks like a real credential to a
// secret scanner. It is not one — the transport below is a fake.
const TEST_KEY = 'sk-nrouter-' + 'test0000000000000abcd';

/** The header an attacker is trying to smuggle into the request. */
const INJECTED = 'X-Injected: yes';

/** Drain whatever body shape the SDK handed the transport into one string. */
async function readBody(body: unknown): Promise<string> {
  if (body === null || body === undefined) return '';
  if (typeof body === 'string') return body;
  if (typeof (body as any)[Symbol.asyncIterator] === 'function') {
    let out = '';
    for await (const part of body as AsyncIterable<Uint8Array>) {
      out += Buffer.from(part).toString('latin1');
    }
    return out;
  }
  return String(body);
}

/** Send one transcription and hand back the raw multipart body, or the refusal. */
async function sendTranscription(filename: string, fields: Record<string, string>) {
  let wire: string | null = null;
  const client = new nRouter({
    apiKey: TEST_KEY,
    maxRetries: 0,
    fetch: async (_url: unknown, init: any) => {
      wire = await readBody(init?.body);
      return new Response(JSON.stringify({ text: 'ok' }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    },
  });

  const file = await toFile(Buffer.from('RIFF'), filename);
  try {
    await client.audio.transcriptions.create({ file, model: 'whisper-1', ...fields });
    return { wire, refused: null as unknown };
  } catch (refused) {
    return { wire, refused };
  }
}

const HOSTILE: [string, string, Record<string, string>][] = [
  ['filename CRLF', `a.mp3\r\n${INJECTED}`, {}],
  ['filename LF', `a.mp3\n${INJECTED}`, {}],
  ['filename CR', `a.mp3\r${INJECTED}`, {}],
  ['field name CRLF', 'a.mp3', { [`prompt\r\n${INJECTED}`]: 'v' }],
  // A CRLF in a field VALUE is deliberately NOT here. It lands after the
  // part's blank line, inside the body, where the boundary — not a line
  // break — is the delimiter. A prompt legitimately contains newlines, so
  // refusing one would break ordinary use; the value case is covered by the
  // header-region check below, which proves it never becomes a header.
  ['field value CRLF stays in the BODY', 'a.mp3', { prompt: `hello\r\n${INJECTED}` }],
];

/**
 * The header block of each multipart part: everything from the boundary line
 * up to the first blank line. A break that terminates a header shows up HERE;
 * one that is merely inside a value does not, and is not an injection.
 */
function headerRegions(body: string): string[] {
  return body
    .split(/--form-data-boundary-[A-Za-z0-9]+/)
    .map((part) => part.split('\r\n\r\n')[0] ?? '')
    .filter((head) => head.includes('Content-Disposition:'));
}

for (const [name, filename, fields] of HOSTILE) {
  test(`multipart header injection: ${name} never reaches the wire`, async () => {
    const { wire, refused } = await sendTranscription(filename, fields);

    if (refused !== null) {
      // Implementation (a): refused before sending. Nothing may have gone out.
      assert.equal(wire, null, 'the hostile request must be refused BEFORE it is sent');
      return;
    }

    // Implementation (b): escaped. The break must not survive as a raw CR/LF
    // anywhere a header could be terminated by it.
    assert.ok(wire !== null, 'the request was neither refused nor sent');
    const body = String(wire);

    // The smoking gun: a header line the caller never asked for, inside a
    // part's HEADER region.
    for (const head of headerRegions(body)) {
      for (const line of head.split('\r\n')) {
        // The injection succeeded only if the break TERMINATED a header and
        // the smuggled text became a header line of its own. Seeing the same
        // characters escaped INSIDE a quoted parameter (`%0D%0A`) is the
        // encoder doing its job, not a leak.
        assert.equal(
          line.trim().startsWith('X-Injected'),
          false,
          `an injected header line reached the wire:\n${head}`
        );
        if (!line.startsWith('Content-Disposition:')) continue;
        assert.equal(
          /[\r\n]/.test(line),
          false,
          `a Content-Disposition carried a raw line break: ${JSON.stringify(line)}`
        );
      }
    }
  });
}

test('a benign filename and field still travel unchanged', async () => {
  // The inverse guard: escaping must not be so aggressive that ordinary
  // uploads stop working, which would make the tests above vacuously green.
  const { wire, refused } = await sendTranscription('speech.mp3', { prompt: 'hello there' });
  assert.equal(refused, null, `a benign upload was refused: ${refused}`);
  const body = String(wire);
  assert.match(body, /filename="speech\.mp3"/);
  assert.match(body, /name="model"/);
  assert.match(body, /whisper-1/);
  assert.match(body, /hello there/);
});
