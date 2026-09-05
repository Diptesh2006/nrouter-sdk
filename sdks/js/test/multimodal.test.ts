const { test } = require('node:test');
const assert = require('node:assert/strict');

const {
  nRouter,
  nRouterConfigurationError,
  validateAudioFormat,
  VALID_AUDIO_FORMATS,
} = require('../dist/index');

const TEST_KEY = 'sk-nrouter-test0000000000000abcd';

function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json', ...headers },
  });
}

function binaryResponse(bytes: Uint8Array, contentType: string, status = 200, headers: Record<string, string> = {}) {
  return new Response(bytes, {
    status,
    headers: { 'content-type': contentType, ...headers },
  });
}

test('nr.media.speech returns binary audio bytes and metadata', async () => {
  let seenUrl = '';
  const client = new nRouter({
    apiKey: TEST_KEY,
    fetch: async (url: unknown, init: any) => {
      seenUrl = String(url);
      return binaryResponse(new Uint8Array([0x49, 0x44, 0x33]), 'audio/mpeg', 200, {
        'x-nr-request-id': 'req-speech',
        'x-nr-request-cost': '0.015',
        'x-nr-cost-status': 'exact',
      });
    },
  });

  const res = await client.nr.media.speech({
    model: 'tts-1',
    input: 'Hello world',
    voice: 'alloy',
  });

  assert.ok(seenUrl.endsWith('/audio/speech'));
  assert.equal(res.contentType, 'audio/mpeg');
  assert.equal(res.bytes.length, 3);
  assert.equal(res.meta.requestId, 'req-speech');
  assert.equal(res.meta.cost, 0.015);
});

test('nr.media.image creates image generation request', async () => {
  let seenUrl = '';
  const client = new nRouter({
    apiKey: TEST_KEY,
    fetch: async (url: unknown, init: any) => {
      seenUrl = String(url);
      return jsonResponse({ data: [{ url: 'https://images.nrouter.ai/img1.png' }] }, 200, {
        'x-nr-request-id': 'req-img',
      });
    },
  });

  const res = await client.nr.media.image({
    model: 'dall-e-3',
    prompt: 'A sunset over mountains',
  });

  assert.ok(seenUrl.endsWith('/images/generations'));
  assert.equal((res.body.data as any[])[0].url, 'https://images.nrouter.ai/img1.png');
  assert.equal(res.meta.requestId, 'req-img');
});

test('nr.media video lifecycle: generate, status, and download bytes', async () => {
  let calls: string[] = [];
  const client = new nRouter({
    apiKey: TEST_KEY,
    fetch: async (url: unknown) => {
      const u = String(url);
      calls.push(u);
      if (u.endsWith('/videos')) {
        return jsonResponse({ id: 'vid_123', status: 'queued' });
      }
      if (u.endsWith('/videos/vid_123')) {
        return jsonResponse({ id: 'vid_123', status: 'completed' });
      }
      if (u.endsWith('/videos/vid_123/content')) {
        return binaryResponse(new Uint8Array([0x00, 0x00, 0x00, 0x18]), 'video/mp4');
      }
      return new Response('not found', { status: 404 });
    },
  });

  const created = await client.nr.media.video({
    model: 'veo-2',
    prompt: 'A gentle ocean wave',
  });
  assert.equal(created.body.id, 'vid_123');

  const status = await client.nr.media.videoStatus('vid_123');
  assert.equal(status.body.status, 'completed');

  const content = await client.nr.media.videoContent('vid_123');
  assert.equal(content.contentType, 'video/mp4');
  assert.equal(content.bytes.length, 4);
});

test('nr.media.embeddings creates embeddings request', async () => {
  let seenUrl = '';
  const client = new nRouter({
    apiKey: TEST_KEY,
    fetch: async (url: unknown) => {
      seenUrl = String(url);
      return jsonResponse({ data: [{ embedding: [0.1, 0.2, 0.3] }] });
    },
  });

  const res = await client.nr.media.embeddings({
    model: 'text-embedding-3-small',
    input: 'search query',
  });

  assert.ok(seenUrl.endsWith('/embeddings'));
  assert.equal((res.body.data as any[])[0].embedding.length, 3);
});

test('nr.media input validation refusals', async () => {
  const client = new nRouter({ apiKey: TEST_KEY });

  // Missing model
  await assert.rejects(
    () => client.nr.media.speech({ model: '', input: 'hi', voice: 'alloy' }),
    nRouterConfigurationError,
  );

  // Video ID with path traversal
  await assert.rejects(
    () => client.nr.media.videoStatus('../bad_id'),
    nRouterConfigurationError,
  );

  // Empty embeddings input
  await assert.rejects(
    () => client.nr.media.embeddings({ model: 'text-embedding-3', input: null as any }),
    nRouterConfigurationError,
  );
});

test('nr.media.transcribe supports plain text, srt, and vtt formats', async () => {
  const dummyFile = new Uint8Array([0x52, 0x49, 0x46, 0x46]); // RIFF header

  const client = new nRouter({
    apiKey: TEST_KEY,
    fetch: async (_url: unknown, init: any) => {
      // Return SRT response
      return new Response('1\n00:00:00,000 --> 00:00:01,000\nHello', {
        status: 200,
        headers: {
          'content-type': 'text/plain',
          'x-nr-request-id': 'req-transcribe-srt',
        },
      });
    },
  });

  const res = await client.nr.media.transcribe({
    model: 'whisper-1',
    file: dummyFile,
    fileName: 'sample.mp3',
    response_format: 'srt',
  });

  assert.equal(res.format, 'srt');
  if (res.format === 'srt') {
    assert.ok(res.text.includes('00:00:00,000'));
  }
  assert.equal(res.meta.requestId, 'req-transcribe-srt');
});

test('validateAudioFormat accepts valid formats and rejects invalid ones', () => {
  for (const fmt of VALID_AUDIO_FORMATS) {
    assert.doesNotThrow(() => validateAudioFormat(fmt));
    assert.doesNotThrow(() => validateAudioFormat(` ${fmt.toUpperCase()} `));
  }
  assert.throws(() => validateAudioFormat('mp4'), nRouterConfigurationError);
  assert.throws(() => validateAudioFormat('ogg'), nRouterConfigurationError);
});

test('nr.media.speech validates response_format', async () => {
  const client = new nRouter({ apiKey: TEST_KEY });
  await assert.rejects(
    () => client.nr.media.speech({
      model: 'tts-1',
      input: 'hello',
      voice: 'alloy',
      response_format: 'unsupported' as any,
    }),
    nRouterConfigurationError
  );
});

test('nr.media.waitForVideo polls until completion', async () => {
  let calls = 0;
  const client = new nRouter({
    apiKey: TEST_KEY,
    fetch: async (url: unknown) => {
      const u = String(url);
      if (u.endsWith('/videos/vid_poll')) {
        calls++;
        if (calls === 1) {
          return jsonResponse({ id: 'vid_poll', status: 'processing' });
        }
        return jsonResponse({ id: 'vid_poll', status: 'completed' });
      }
      return new Response('not found', { status: 404 });
    },
  });

  const res = await client.nr.media.waitForVideo('vid_poll', { pollIntervalMs: 10, timeoutMs: 1000 });
  assert.equal(res.body.status, 'completed');
  assert.equal(calls, 2);
});

test('nr.media.waitForVideo throws on failed status', async () => {
  const client = new nRouter({
    apiKey: TEST_KEY,
    fetch: async (url: unknown) => {
      return jsonResponse({ id: 'vid_fail', status: 'failed' });
    },
  });

  await assert.rejects(
    () => client.nr.media.waitForVideo('vid_fail', { pollIntervalMs: 10, timeoutMs: 1000 }),
    /ended with status: failed/
  );
});
