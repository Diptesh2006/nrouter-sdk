// Cases 8 and 9 — the extra_body mapping and the message assembly.
//
// Both are places where an "obvious simplification" is a real regression:
//
//   * `cache: true` OMITTED — true is the gateway default (spec
//     extra_body_fields.nrouter_cache.default), so sending it changes nothing
//     and just grows every body. `cache: false` MUST be sent: it is the only
//     way to force provider egress.
//   * an EMPTY `guardrailIds` array OMITTED — omission means "apply every
//     org-enabled guardrail", a present list means "run ONLY these". `[]` is a
//     different instruction, and the dangerous one: it asks for zero
//     guardrails on a request whose org configured some. Collapsing this to
//     `if (opts.guardrailIds)` turns "no guardrail UI state yet" into
//     "disable the org's guardrails", with a green test suite.

const { test } = require('node:test');
const assert = require('node:assert/strict');

const { buildExtraBody, buildMessages, buildChatBody } = require('../dist/options');

// ---------------------------------------------------------------------------
// Case 8 — buildExtraBody
// ---------------------------------------------------------------------------

test('nothing set produces an EMPTY extra body', () => {
  assert.deepEqual(buildExtraBody({ model: 'gpt-4o' }), {});
});

test('cache: true is OMITTED — it is the gateway default', () => {
  const extra = buildExtraBody({ model: 'gpt-4o', cache: true });
  assert.equal('nrouter_cache' in extra, false, 'sending the default changes nothing but grows every body');
  assert.deepEqual(extra, {});
});

test('cache: false IS sent — it is the only way to force provider egress', () => {
  assert.deepEqual(buildExtraBody({ model: 'gpt-4o', cache: false }), { nrouter_cache: false });
});

test('cache undefined is not confused with cache false', () => {
  // A loose `if (!opts.cache)` would send `nrouter_cache: false` on every
  // request that never mentioned caching, disabling it silently for everyone.
  assert.equal('nrouter_cache' in buildExtraBody({ model: 'gpt-4o' }), false);
  assert.equal('nrouter_cache' in buildExtraBody({ model: 'gpt-4o', cache: undefined }), false);
});

test('an EMPTY guardrailIds array is OMITTED, not sent as []', () => {
  const extra = buildExtraBody({ model: 'gpt-4o', guardrailIds: [] });
  assert.equal(
    'nrouter_guardrail_ids' in extra,
    false,
    '[] asks the gateway for ZERO guardrails; omission asks for all org-enabled ones'
  );
  assert.deepEqual(extra, {});
});

test('a non-empty guardrailIds array IS sent', () => {
  const ids = ['11111111-1111-1111-1111-111111111111'];
  assert.deepEqual(buildExtraBody({ model: 'gpt-4o', guardrailIds: ids }), {
    nrouter_guardrail_ids: ids,
  });
});

test('the prompt template and its variables map onto the spec field names', () => {
  const extra = buildExtraBody({
    model: 'gpt-4o',
    promptTemplateId: 'tpl-1',
    promptVariables: { name: 'Ada' },
  });
  assert.deepEqual(extra, {
    nrouter_prompt_template_id: 'tpl-1',
    nrouter_prompt_variables: { name: 'Ada' },
  });
});

test('an EMPTY promptVariables object is omitted', () => {
  const extra = buildExtraBody({ model: 'gpt-4o', promptTemplateId: 'tpl-1', promptVariables: {} });
  assert.deepEqual(extra, { nrouter_prompt_template_id: 'tpl-1' });
});

test('the extra_body field set is CLOSED to the four spec fields', () => {
  // The gateway strips the fields it knows and forwards the rest to the
  // provider, so an invented `nrouter_*` field is not an error a caller ever
  // sees: it is a dead option that looks live.
  const extra = buildExtraBody({
    model: 'gpt-4o',
    promptTemplateId: 'tpl-1',
    promptVariables: { a: 'b' },
    guardrailIds: ['g'],
    cache: false,
  });
  assert.deepEqual(Object.keys(extra).sort(), [
    'nrouter_cache',
    'nrouter_guardrail_ids',
    'nrouter_prompt_template_id',
    'nrouter_prompt_variables',
  ]);
});

test('NO tenancy identifier is ever written into a body', () => {
  // Gateway gate 5: tenancy comes from the authenticated key alone. A
  // body-supplied org/team id is the spend-attribution spoof that gate exists
  // to stop, and this SDK must not be the thing that supplies one.
  const body = buildChatBody(
    { model: 'gpt-4o', prompt: 'hi', guardrailIds: ['g'], cache: false },
    {}
  );
  const serialized = JSON.stringify(body).toLowerCase();
  for (const forbidden of ['organization_id', 'org_id', 'team_id', 'user_id', 'nrouter_org']) {
    assert.equal(serialized.includes(forbidden), false, `the body carries ${forbidden}`);
  }
});

// ---------------------------------------------------------------------------
// Case 9 — buildMessages
// ---------------------------------------------------------------------------

test('systemPrompt LEADS the message list', () => {
  const msgs = buildMessages({ model: 'm', systemPrompt: 'be terse', prompt: 'hi' });
  assert.deepEqual(msgs, [
    { role: 'system', content: 'be terse' },
    { role: 'user', content: 'hi' },
  ]);
  assert.equal(msgs[0].role, 'system', 'the system turn must be first');
});

test('an EMPTY systemPrompt adds no turn', () => {
  // An empty system message still costs tokens and can change behaviour.
  assert.deepEqual(buildMessages({ model: 'm', systemPrompt: '', prompt: 'hi' }), [
    { role: 'user', content: 'hi' },
  ]);
});

test('explicit messages BEAT prompt', () => {
  const msgs = buildMessages({
    model: 'm',
    prompt: 'ignored',
    messages: [
      { role: 'user', content: 'first' },
      { role: 'assistant', content: 'ok' },
      { role: 'user', content: 'second' },
    ],
  });
  assert.deepEqual(msgs.map((m: { content: unknown }) => m.content), ['first', 'ok', 'second']);
  assert.equal(
    JSON.stringify(msgs).includes('ignored'),
    false,
    'prompt is a single-turn convenience and must not be appended'
  );
});

test('an EMPTY messages array falls through to prompt', () => {
  // A request carrying zero messages is a guaranteed provider 400, so treating
  // `[]` as "supplied" turns a caller's uninitialised state into a billed
  // failure.
  assert.deepEqual(buildMessages({ model: 'm', messages: [], prompt: 'hi' }), [
    { role: 'user', content: 'hi' },
  ]);
});

test('images fold into the LAST user turn as content parts', () => {
  const dataUrl = 'data:image/png;base64,iVBORw0KGgo=';
  const msgs = buildMessages({
    model: 'm',
    messages: [
      { role: 'user', content: 'first' },
      { role: 'assistant', content: 'ok' },
      { role: 'user', content: 'look at this' },
    ],
    images: [dataUrl],
  });

  assert.equal(msgs.length, 3);
  assert.equal(msgs[0].content, 'first', 'an earlier user turn must be untouched');
  assert.deepEqual(msgs[2].content, [
    { type: 'text', text: 'look at this' },
    { type: 'image_url', image_url: { url: dataUrl } },
  ]);
});

test('an image-only turn carries no empty text part', () => {
  // Several providers reject a zero-length text block outright, and an empty
  // string is not something the caller asked to send.
  const msgs = buildMessages({ model: 'm', prompt: '', images: ['https://x/y.png'] });
  assert.deepEqual(msgs, [
    { role: 'user', content: [{ type: 'image_url', image_url: { url: 'https://x/y.png' } }] },
  ]);
});

test('images with no user turn get one rather than being dropped', () => {
  // A dropped attachment is invisible until the model answers as if it never
  // saw the image, which reads as a model failure rather than an SDK one.
  const msgs = buildMessages({ model: 'm', systemPrompt: 'sys', images: ['https://x/y.png'] });
  assert.equal(msgs.length, 2);
  assert.equal(msgs[0].role, 'system');
  assert.equal(msgs[1].role, 'user');
  assert.deepEqual(msgs[1].content, [{ type: 'image_url', image_url: { url: 'https://x/y.png' } }]);
});

test('images append to an existing content-parts array', () => {
  const msgs = buildMessages({
    model: 'm',
    messages: [{ role: 'user', content: [{ type: 'text', text: 'a' }] }],
    images: ['https://x/y.png'],
  });
  assert.deepEqual(msgs[0].content, [
    { type: 'text', text: 'a' },
    { type: 'image_url', image_url: { url: 'https://x/y.png' } },
  ]);
});

test("buildMessages never mutates the caller's array or its turns", () => {
  const original = [{ role: 'user', content: 'hi' }];
  const snapshot = JSON.stringify(original);
  buildMessages({ model: 'm', messages: original, images: ['https://x/y.png'] });
  assert.equal(JSON.stringify(original), snapshot, 'the caller may reuse this array for a second call');
});

// ---------------------------------------------------------------------------
// buildChatBody — the merge order
// ---------------------------------------------------------------------------

test('buildChatBody carries model, messages and the resolved sampling params', () => {
  const body = buildChatBody(
    { model: 'claude-sonnet-4-5', prompt: 'hi', maxTokens: 128 },
    { top_p: 0.4 }
  );
  assert.equal(body.model, 'claude-sonnet-4-5');
  assert.deepEqual(body.messages, [{ role: 'user', content: 'hi' }]);
  assert.equal(body.max_tokens, 128);
  assert.equal(body.top_p, 0.4);
  assert.equal('temperature' in body, false, 'the policy resolved this; it must not be re-derived');
});

test('an unset maxTokens is OMITTED, never capped at an SDK-chosen number', () => {
  const body = buildChatBody({ model: 'm', prompt: 'hi' }, {});
  assert.equal('max_tokens' in body, false);
});

test('buildChatBody never sets `stream` — the transport owns it', () => {
  const body = buildChatBody({ model: 'm', prompt: 'hi' }, {});
  assert.equal('stream' in body, false);
});

test('opts.extra is applied LAST so a caller can always reach an unmodelled field', () => {
  const body = buildChatBody(
    { model: 'm', prompt: 'hi', cache: false, extra: { seed: 7, nrouter_cache: true } },
    {}
  );
  assert.equal(body.seed, 7);
  assert.equal(body.nrouter_cache, true, 'the escape hatch outranks everything above it');
});

test('the API key is never a body field', () => {
  const body = buildChatBody({ model: 'm', prompt: 'hi', extra: {} }, {});
  const keys = Object.keys(body).join(',').toLowerCase();
  assert.equal(keys.includes('api_key'), false);
  assert.equal(keys.includes('apikey'), false);
  assert.equal(keys.includes('authorization'), false);
});

// The SDK's image contract was enforced on nr.media.* and quietly ignored on
// the far more common nr.chat({ images }). A bare path or an http:// URL fails
// at the provider AFTER the request is billed; refusing locally is free.
test('nr.chat({ images }) enforces the same image contract as the media surface', () => {
  const bad = ['/local/path.png', 'http://example.com/a.png', 'data:image/png;base64,A', 'https://example.com bad'];
  for (const url of bad) {
    assert.throws(
      () => buildMessages({ model: 'm', prompt: 'hi', images: [url] }),
      (err: unknown) => {
        assert.equal((err as { kind?: string }).kind, 'configuration', `should refuse: ${url}`);
        return true;
      },
      `accepted an unusable image reference: ${url}`,
    );
  }
  // ...and a good one still builds a part, so the guard is not merely strict.
  const msgs = buildMessages({ model: 'm', prompt: 'hi', images: ['https://example.com/a.png'] });
  assert.ok(JSON.stringify(msgs).includes('image_url'));
});
