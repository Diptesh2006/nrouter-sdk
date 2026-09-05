// Cases 8 and 9 — the extra_body mapping and the message assembly.
//
// Both are places where an "obvious simplification" is a real regression:
//
//   * `cache: true` OMITTED — true is the gateway default (spec
//     extra_body_fields.nrouter_cache.default), so sending it changes nothing
//     and just grows every body. `cache: false` MUST be sent: it is the only
//     way to force provider egress.
//   * `guardrailIds` REFUSED, loudly. It was a fake surface: MEASURED
//     2026-08-28, `nrouter_guardrail_ids` appears NOWHERE in the whole
//     nrouter-rust-gateway repo (0 hits against 608 guardrail references),
//     and the gateway's own OpenAPI advertises only the other three
//     extra_body fields. Guardrail selection there is org/config driven,
//     with no per-request override. Sending it anyway reached the PROVIDER
//     verbatim — every provider transformation explicitly
//     `object.remove("nrouter_cache")` and none removes this one — so the
//     caller got an opaque upstream rejection. Deleting the option silently
//     would be worse still: a plain-JS caller, or a TS caller spreading a
//     widened options object, would see NO error and a normal-looking answer
//     with the safety control they selected never applied. That is the
//     "fake success" nrouter-app already refuses by name in
//     `api/nrouter-proxy/chat/route.ts` (400 GATEWAY_FEATURE_UNSUPPORTED);
//     this SDK must not be the laxer surface.

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

/** spec/nrouter-sdk-spec.json — the Rule #14 source of truth, four levels up. */
const SPEC_PATH = path.resolve(__dirname, '..', '..', '..', 'spec', 'nrouter-sdk-spec.json');

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

test('an EMPTY guardrailIds array is accepted and omitted, NOT refused', () => {
  // The refusal must fire exactly when the caller's intent goes unserved. `[]`
  // expresses no selection at all — the org's guardrails apply either way — so
  // refusing it would break a caller wiring `guardrailIds: state.selected` with
  // an empty default, on a request that works correctly today and will keep
  // working correctly. Scope the throw to a REAL selection.
  const extra = buildExtraBody({ model: 'gpt-4o', guardrailIds: [] });
  assert.deepEqual(extra, {});
});

test('a non-empty guardrailIds array is REFUSED, naming what to do instead', () => {
  // Locally, before egress: today this reaches the provider as an unrecognized
  // argument and costs a round trip to learn nothing useful.
  assert.throws(
    () => buildExtraBody({ model: 'gpt-4o', guardrailIds: ['gr-1'] }),
    (err: unknown) => {
      const e = err as { kind?: string; message?: string };
      // CONFIGURATION, and that is load-bearing: it is permanent and never
      // retried, so a caller's `if (isRetryable(e)) retry` loop cannot spin on
      // a condition no retry improves.
      assert.equal(e.kind, 'configuration');
      const m = String(e.message);
      assert.match(m, /guardrailIds/, 'must name the option the caller set');
      assert.match(m, /dashboard/i, 'must name where guardrails ARE configured');
      assert.match(
        m,
        /automatically|already appl/i,
        'must say the org guardrails still run — otherwise it reads as "no guardrails"',
      );
      return true;
    },
  );
});

test('the refusal reaches callers through buildChatBody, not just buildExtraBody', () => {
  // buildExtraBody is internal; every real caller arrives via buildChatBody.
  // A guard wired only into the helper nobody calls is not a guard.
  assert.throws(
    () => buildChatBody({ model: 'm', prompt: 'hi', guardrailIds: ['gr-1'] }, {}),
    (err: unknown) => (err as { kind?: string }).kind === 'configuration',
  );
});

test('NO guardrail-shaped key can ever reach the wire', () => {
  // Keyed on the SHAPE rather than the one spelling: the defect was a field
  // this SDK invented that the gateway never read, and a second invented
  // spelling would be the same defect with a green suite.
  const extra = buildExtraBody({
    model: 'gpt-4o',
    promptTemplateId: 'tpl-1',
    promptVariables: { a: 'b' },
    guardrailIds: [],
    cache: false,
  });
  for (const key of Object.keys(extra)) {
    assert.equal(/guardrail/i.test(key), false, `emitted a guardrail field: ${key}`);
  }
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

test('the extra_body field set is CLOSED to the three spec fields', () => {
  // The gateway strips the fields it knows and forwards the rest to the
  // provider, so an invented `nrouter_*` field is not an error a caller ever
  // sees: it is a dead option that looks live. It was FOUR until
  // `nrouter_guardrail_ids` was measured to have zero gateway readers.
  const extra = buildExtraBody({
    model: 'gpt-4o',
    promptTemplateId: 'tpl-1',
    promptVariables: { a: 'b' },
    cache: false,
  });
  assert.deepEqual(Object.keys(extra).sort(), [
    'nrouter_cache',
    'nrouter_prompt_template_id',
    'nrouter_prompt_variables',
  ]);
});

test('the emittable fields and the SPEC agree in BOTH directions', () => {
  // The pin that would have caught this defect. `extra_body_fields` in
  // spec/nrouter-sdk-spec.json is the Rule #14 source of truth, and it carried
  // `nrouter_guardrail_ids` while the gateway read no such field — so the SoT
  // was wrong and every SDK generated from it inherited the lie. Asserting
  // only "code ⊆ spec" would have stayed green through exactly that.
  const spec = JSON.parse(fs.readFileSync(SPEC_PATH, 'utf8'));
  const specFields = Object.keys(spec.extra_body_fields).sort();
  const emitted = Object.keys(
    buildExtraBody({
      model: 'gpt-4o',
      promptTemplateId: 'tpl-1',
      promptVariables: { a: 'b' },
      cache: false,
    }),
  ).sort();
  assert.deepEqual(
    emitted,
    specFields,
    'the spec and this SDK disagree about the nRouter request fields',
  );
  assert.equal(
    'nrouter_guardrail_ids' in spec.extra_body_fields,
    false,
    'the gateway reads no such field — 0 hits in nrouter-rust-gateway, measured 2026-08-28',
  );
});

test('NO tenancy identifier is ever written into a body', () => {
  // Gateway gate 5: tenancy comes from the authenticated key alone. A
  // body-supplied org/team id is the spend-attribution spoof that gate exists
  // to stop, and this SDK must not be the thing that supplies one.
  const body = buildChatBody(
    { model: 'gpt-4o', prompt: 'hi', promptTemplateId: 'tpl-1', cache: false },
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

// ---------------------------------------------------------------------------
// SWEEP LANE D — defects found 2026-08-28, each pinned by the test above it.
// ---------------------------------------------------------------------------

test('buildMessages keeps EVERY field of a turn, not just role and content', () => {
  // The defect: `out.push({ role, content })` rebuilt each turn from two
  // properties and silently discarded the rest. A tool-calling conversation
  // lost `tool_calls` off the assistant turn and `tool_call_id` off the tool
  // turn — the exact two fields this SDK's own Anthropic translator reads
  // (src/chat.ts, `role === 'tool'` and `assistant && tool_calls`), which made
  // that translator unreachable and every replayed tool conversation a billed
  // provider 400.
  const messages = [
    { role: 'user', content: 'weather in SF?' },
    {
      role: 'assistant',
      content: '',
      tool_calls: [
        { id: 'call_1', type: 'function', function: { name: 'get_weather', arguments: '{}' } },
      ],
    },
    { role: 'tool', tool_call_id: 'call_1', name: 'get_weather', content: '72F' },
  ];
  const out = buildMessages({ model: 'gpt-4o', messages });

  assert.deepEqual(
    out[1].tool_calls,
    messages[1].tool_calls,
    'the assistant turn lost its tool_calls — the model is asked to answer a call it never made',
  );
  assert.equal(
    out[2].tool_call_id,
    'call_1',
    'the tool result lost the id binding it to its call',
  );
  assert.equal(out[2].name, 'get_weather', 'the tool result lost its function name');
  assert.deepEqual(out, messages, 'every turn must survive intact');
});

test('a preserved turn is still a COPY — the caller may reuse the array', () => {
  const original = [
    { role: 'assistant', content: 'x', tool_calls: [{ id: 'c1' }] },
    { role: 'user', content: 'hi' },
  ];
  const snapshot = JSON.stringify(original);
  const out = buildMessages({ model: 'm', messages: original, images: ['https://x/y.png'] });
  assert.equal(JSON.stringify(original), snapshot, 'the caller array was mutated');
  assert.notEqual(out[0], original[0], 'a turn must be copied, not aliased');
});

test('a tenancy identifier CANNOT be smuggled onto the wire through extra', () => {
  // Gateway rules §4f GATE 5: tenancy is resolved from the authenticated caller
  // ALONE. `src/memory.ts` already refuses these keys on a message and its
  // comment claims "test/options.test.ts already pins this for the body
  // builders" — it did not. The body builder was the laxer of the two surfaces,
  // which is the inverse of what that comment asserts.
  //
  // Normalized, exactly as memory.ts normalizes: `organizationId` and
  // `ORGANIZATION_ID` are the same key as `organization_id`.
  for (const key of [
    'organization_id',
    'organizationId',
    'ORG_ID',
    'team_id',
    'teamId',
    'user_id',
    'nrouter_org',
  ]) {
    assert.throws(
      () => buildChatBody({ model: 'm', prompt: 'hi', extra: { [key]: 'org-victim' } }, {}),
      (err: unknown) => {
        const e = err as { kind?: string; message?: string };
        // CONFIGURATION: permanent, never retried.
        assert.equal(e.kind, 'configuration', `${key} must be refused as a configuration error`);
        assert.match(String(e.message), new RegExp(key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
        return true;
      },
      `extra.${key} reached the request body`,
    );
  }
});

test('the tenancy guard keys on FIELD NAMES, never on message text', () => {
  // The old test greped the serialized body for the substring "team_id", which
  // would have refused a caller legitimately asking the model about a database
  // column. A prompt is content, not a field.
  const body = buildChatBody(
    {
      model: 'm',
      prompt: 'write SQL selecting organization_id, team_id and user_id from the audit table',
      systemPrompt: 'you know about org_id columns',
    },
    {},
  );
  assert.ok(JSON.stringify(body.messages).includes('organization_id'), 'content must pass through');
  for (const key of Object.keys(body)) {
    assert.equal(
      /^(organization_?id|org_?id|team_?id|user_?id|nrouter_?org)$/i.test(key),
      false,
      `the BODY carries a tenancy field: ${key}`,
    );
  }
});

test('a prompt-template VARIABLE named like a tenancy field is not a tenancy field', () => {
  // `nrouter_prompt_variables` is a Jinja namespace the gateway renders into a
  // prompt; a variable spelled `organization_id` is a string in a template, not
  // a body-level tenancy claim. Pinned so the guard above is never "fixed"
  // into refusing it.
  const body = buildChatBody(
    { model: 'm', prompt: 'hi', promptTemplateId: 't', promptVariables: { organization_id: 'x' } },
    {},
  );
  assert.deepEqual(body.nrouter_prompt_variables, { organization_id: 'x' });
});

test('a __proto__ key in extra is REFUSED, not silently swallowed', () => {
  // `Object.assign` invokes the `__proto__` setter, so a JSON-parsed escape
  // hatch carrying it (a) never reaches the wire and (b) replaces the body
  // object's prototype. Measured: `extra: JSON.parse('{"__proto__":{"stream":
  // true}}')` makes chat() throw "remove `stream: true` from `extra`" at a
  // caller who never set stream.
  const evil = JSON.parse('{"__proto__":{"stream":true}}');
  assert.throws(
    () => buildChatBody({ model: 'm', prompt: 'hi', extra: evil }, {}),
    (err: unknown) => {
      assert.equal((err as { kind?: string }).kind, 'configuration');
      assert.match(String((err as { message?: string }).message), /__proto__/);
      return true;
    },
  );

  for (const dangerous of ['prototype', 'constructor']) {
    assert.throws(
      () => buildChatBody({ model: 'm', prompt: 'hi', extra: { [dangerous]: { injected: true } } }, {}),
      (err: unknown) => {
        assert.equal((err as { kind?: string }).kind, 'configuration');
        assert.match(String((err as { message?: string }).message), new RegExp(dangerous));
        return true;
      },
    );
  }
});


test('maxTokens must be a positive integer, never coerced', () => {
  // `max_tokens: NaN` serializes as JSON `null` — a value the caller never
  // chose, on a field that decides what the request costs.
  for (const bad of [NaN, Infinity, -Infinity, 0, -5, 1.5]) {
    assert.throws(
      () => buildChatBody({ model: 'm', prompt: 'hi', maxTokens: bad }, {}),
      (err: unknown) => (err as { kind?: string }).kind === 'configuration',
      `maxTokens ${String(bad)} reached the wire`,
    );
  }
  assert.equal(buildChatBody({ model: 'm', prompt: 'hi', maxTokens: 1 }, {}).max_tokens, 1);
  assert.equal(buildChatBody({ model: 'm', prompt: 'hi', maxTokens: 4096 }, {}).max_tokens, 4096);
});

test('a body with ZERO messages is refused before it is billed', () => {
  // This file already reasons that "a request carrying zero messages is a
  // guaranteed provider 400" — and then emitted exactly that when neither
  // `prompt` nor `messages` was supplied.
  assert.throws(
    () => buildChatBody({ model: 'm' }, {}),
    (err: unknown) => {
      assert.equal((err as { kind?: string }).kind, 'configuration');
      return true;
    },
  );
  assert.throws(() => buildChatBody({ model: 'm', messages: [] }, {}), (err: unknown) =>
    (err as { kind?: string }).kind === 'configuration');
  // A system turn alone is still a real request; only the empty list is refused.
  assert.equal(buildChatBody({ model: 'm', systemPrompt: 's' }, {}).messages.length, 1);
});
