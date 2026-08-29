// Conversation memory — a CLIENT-SIDE helper, and every case below exists to
// keep it from quietly becoming something else.
//
// MEASURED 2026-08-28: the string `memory` appears ZERO times in
// spec/nrouter-sdk-spec.json, and the gateway mounts no memory route. There is
// no server-side conversation state to test against, so every assertion here
// is about a plain object in this process. If a future case in this file needs
// a network mock, the feature has grown a lie.
//
// The four cases that are NOT obvious, each pinning a defect that ships green
// without them:
//
//   * `messages()` returns a COPY. Handing out the live array lets a caller's
//     ordinary `msgs.push(...)`/`msgs.sort()` before a call mutate the memory
//     it read from, so the next turn silently carries a message nobody added.
//   * A custom store is USED, proven by EFFECT. Asserting only that `load` and
//     `save` were called passes against an implementation that calls them and
//     then answers from its own array — an arg-blind double proves nothing.
//   * Concurrent `add()` cannot lose a message. Every `add` is a
//     read-modify-write across an await, which is the classic lost update; an
//     async store makes the window real and a sync default store hides it.
//   * A throwing store is a `configuration` error, never `transport`.
//     `isRetryable` is what a caller's `while (isRetryable(e))` loop reads, and
//     `transport` is retryable — a permanent fault classified retryable spins
//     that loop forever.

const { test } = require('node:test');
const assert = require('node:assert/strict');

const { createMemory, createArrayStore } = require('../dist/memory');
const { isRetryable, nRouterConfigurationError, nRouterError } = require('../dist/index');

// ---------------------------------------------------------------------------
// Case 1 — round trip and clear
// ---------------------------------------------------------------------------

test('messages round-trip IN ORDER and clear() empties', async () => {
  const mem = createMemory();

  await mem.add({ role: 'user', content: 'first' });
  await mem.add({ role: 'assistant', content: 'second' });
  await mem.add({ role: 'user', content: 'third' });

  assert.deepEqual(await mem.messages(), [
    { role: 'user', content: 'first' },
    { role: 'assistant', content: 'second' },
    { role: 'user', content: 'third' },
  ]);

  await mem.clear();
  assert.deepEqual(await mem.messages(), []);
});

test('a fresh memory starts EMPTY', async () => {
  assert.deepEqual(await createMemory().messages(), []);
});

test('content parts survive unchanged — memory is not a message rewriter', async () => {
  // A multimodal turn is an array of parts. Anything that flattens or reorders
  // them here changes the request the caller assembled.
  const mem = createMemory();
  const parts = [
    { type: 'text', text: 'what is this' },
    { type: 'image_url', image_url: { url: 'https://example.test/a.png' } },
  ];
  await mem.add({ role: 'user', content: parts });
  assert.deepEqual(await mem.messages(), [{ role: 'user', content: parts }]);
});

// ---------------------------------------------------------------------------
// Case 2 — the store is REALLY the store, proven by effect
// ---------------------------------------------------------------------------

test('a custom store is the ONLY system of record — proven by EFFECT, not by call count', async () => {
  // The store is seeded with a message this process never `add`ed. If the
  // memory keeps its own array and merely calls `load`, that seeded message
  // cannot appear — so this assertion cannot be satisfied by a double that
  // only records calls.
  const rows = [{ role: 'assistant', content: 'seeded by the store, never added here' }];
  const calls: string[] = [];
  const store = {
    load() {
      calls.push('load');
      return rows.map((m) => ({ ...m }));
    },
    save(messages: unknown[]) {
      calls.push('save');
      rows.length = 0;
      for (const m of messages) rows.push({ ...(m as { role: string; content: string }) });
    },
  };

  const mem = createMemory({ store });

  assert.deepEqual(await mem.messages(), [
    { role: 'assistant', content: 'seeded by the store, never added here' },
  ]);

  await mem.add({ role: 'user', content: 'added here' });

  // The EFFECT: the caller's own backing array grew. Nothing about a recorded
  // call name would have caught an implementation that saved into a private
  // field instead.
  assert.equal(rows.length, 2);
  assert.equal(rows[1].content, 'added here');

  await mem.clear();
  assert.equal(rows.length, 0, 'clear() must reach the caller store, not just a local cache');

  assert.ok(calls.includes('load'), 'load was never called');
  assert.ok(calls.includes('save'), 'save was never called');
});

test('the DEFAULT store writes to no disk, no localStorage and no network', async () => {
  // Prompt text is usually personal data. Persisting it is a GDPR decision the
  // caller makes by supplying a store, never a convenience this SDK takes.
  // The proof is structural: the default store is a plain array holder, and
  // two memories built with no options share nothing.
  const a = createMemory();
  const b = createMemory();
  await a.add({ role: 'user', content: 'only in a' });

  assert.deepEqual(await b.messages(), [], 'the default store leaked state between instances');

  const store = createArrayStore();
  assert.deepEqual(store.load(), []);
  store.save([{ role: 'user', content: 'x' }]);
  assert.deepEqual(store.load(), [{ role: 'user', content: 'x' }]);
});

test('createArrayStore seeds from a caller array WITHOUT aliasing it', async () => {
  // Exercised DIRECTLY, not through createMemory. Measured: routing this
  // through the memory hid the defect entirely — the memory's own read-path
  // validation rebuilds every message into a fresh array, so an aliasing store
  // still passed. createArrayStore is exported, so a caller can hold it alone
  // and that masking is not available to them.
  const seed = [{ role: 'user', content: 'seed' }];
  const store = createArrayStore(seed);

  // 1. The seed is copied in.
  store.save([...store.load(), { role: 'assistant', content: 'reply' }]);
  assert.equal(seed.length, 1, 'the seed array the caller still holds was mutated');

  // 2. load() hands out a copy, so mutating it cannot rewrite the store.
  const got = store.load();
  got.push({ role: 'user', content: 'injected' });
  got[0].content = 'overwritten';
  assert.deepEqual(store.load(), [
    { role: 'user', content: 'seed' },
    { role: 'assistant', content: 'reply' },
  ]);

  // 3. save() copies in, so the caller's array is not adopted by reference.
  const handed = [{ role: 'user', content: 'handed in' }];
  store.save(handed);
  handed.push({ role: 'user', content: 'appended after save' });
  assert.deepEqual(store.load(), [{ role: 'user', content: 'handed in' }]);
});

// ---------------------------------------------------------------------------
// Case 3 — messages() hands out a COPY
// ---------------------------------------------------------------------------

test('messages() returns a copy — mutating it cannot corrupt the memory', async () => {
  const mem = createMemory();
  await mem.add({ role: 'user', content: 'kept' });

  const first = await mem.messages();
  first.push({ role: 'user', content: 'injected by a caller mutation' });
  first[0].content = 'overwritten by a caller mutation';

  assert.deepEqual(
    await mem.messages(),
    [{ role: 'user', content: 'kept' }],
    'the caller mutated the memory through the array it was handed'
  );
});

test('add() copies the message — mutating the caller object cannot rewrite history', async () => {
  const mem = createMemory();
  const msg = { role: 'user', content: 'as sent' };
  await mem.add(msg);
  msg.content = 'rewritten after the fact';

  assert.deepEqual(await mem.messages(), [{ role: 'user', content: 'as sent' }]);
});

test('a nested content part is copied too, not aliased', async () => {
  const mem = createMemory();
  const part = { type: 'image_url', image_url: { url: 'https://example.test/a.png' } };
  await mem.add({ role: 'user', content: [part] });

  part.image_url.url = 'https://attacker.test/b.png';

  const out = await mem.messages();
  assert.equal((out[0].content as any)[0].image_url.url, 'https://example.test/a.png');
});

// ---------------------------------------------------------------------------
// Case 4 — NO tenancy field, ever
// ---------------------------------------------------------------------------
//
// test/options.test.ts already asserts "NO tenancy identifier is ever written
// into a body" for the body builders. Memory is the other way a message
// reaches that body, so the same gate has to hold here or memory is the hole.
// Rust gateway rules §4f gate 5: tenancy comes from the authenticated caller
// alone — a body-supplied org/team id is the spend-attribution spoof.

const TENANCY_KEYS = [
  'organization_id',
  'org_id',
  'team_id',
  'user_id',
  'organizationId',
  'orgId',
  'teamId',
  'userId',
  'nrouter_org',
];

for (const key of TENANCY_KEYS) {
  test(`add() REFUSES a message carrying ${key}`, async () => {
    const mem = createMemory();
    await assert.rejects(
      () => mem.add({ role: 'user', content: 'hi', [key]: 'org-uuid' } as any),
      (err: unknown) => {
        assert.ok(err instanceof nRouterError, 'not an SDK error');
        assert.equal((err as any).kind, 'configuration');
        assert.match((err as Error).message, new RegExp(key));
        return true;
      }
    );
    assert.deepEqual(await mem.messages(), [], 'the refused message was stored anyway');
  });
}

test('a tenancy field planted in the STORE is refused on the way out', async () => {
  // A store is caller-supplied and can be a shared Redis key another process
  // writes. Trusting it on the read path would make the store the smuggling
  // route the add() guard closed.
  const store = {
    load: () => [{ role: 'user', content: 'hi', team_id: 'other-team' }],
    save: () => {},
  };
  const mem = createMemory({ store });
  await assert.rejects(() => mem.messages(), nRouterConfigurationError);
});

test('nothing memory emits serializes a tenancy key', async () => {
  const mem = createMemory();
  await mem.add({ role: 'system', content: 'be terse' });
  await mem.add({ role: 'user', content: 'hi' });

  const serialized = JSON.stringify(await mem.messages()).toLowerCase();
  for (const forbidden of ['organization_id', 'org_id', 'team_id', 'user_id', 'nrouter_org']) {
    assert.equal(serialized.includes(forbidden), false, `memory emitted ${forbidden}`);
  }
});

// ---------------------------------------------------------------------------
// Case 5 — concurrency: an async store must not lose an add
// ---------------------------------------------------------------------------

test('concurrent add() calls against an ASYNC store lose NOTHING', async () => {
  // Every add is load -> append -> save. With a real await between load and
  // save, two adds started together both read the same list and the second
  // save overwrites the first — the textbook lost update. Serializing the
  // read-modify-write is the only fix; a mutex-free "it works with the default
  // store" implementation passes every other test in this file.
  let rows: Array<{ role: string; content: string }> = [];
  const tick = () => new Promise((r) => setTimeout(r, 1));
  const store = {
    async load() {
      await tick();
      return rows.map((m) => ({ ...m }));
    },
    async save(messages: Array<{ role: string; content: string }>) {
      await tick();
      rows = messages.map((m) => ({ ...m }));
    },
  };

  const mem = createMemory({ store });

  await Promise.all([
    mem.add({ role: 'user', content: 'a' }),
    mem.add({ role: 'user', content: 'b' }),
    mem.add({ role: 'user', content: 'c' }),
    mem.add({ role: 'user', content: 'd' }),
    mem.add({ role: 'user', content: 'e' }),
  ]);

  const out = await mem.messages();
  assert.equal(out.length, 5, `an add was lost: ${JSON.stringify(out)}`);
  assert.deepEqual(
    out.map((m: { content: string }) => m.content).sort(),
    ['a', 'b', 'c', 'd', 'e']
  );
});

test('a concurrent clear() is serialized with the adds, not interleaved', async () => {
  let rows: Array<{ role: string; content: string }> = [];
  const tick = () => new Promise((r) => setTimeout(r, 1));
  const store = {
    async load() {
      await tick();
      return rows.map((m) => ({ ...m }));
    },
    async save(messages: Array<{ role: string; content: string }>) {
      await tick();
      rows = messages.map((m) => ({ ...m }));
    },
  };
  const mem = createMemory({ store });

  await mem.add({ role: 'user', content: 'before' });
  await Promise.all([mem.clear(), mem.add({ role: 'user', content: 'after' })]);

  // Ordering is the caller's, but the two operations must not corrupt each
  // other: whatever survives is a whole message list, never a half-written one.
  const out = await mem.messages();
  assert.deepEqual(out, [{ role: 'user', content: 'after' }]);
});

// ---------------------------------------------------------------------------
// Case 6 — a throwing store fails LOUDLY and PERMANENTLY
// ---------------------------------------------------------------------------

test('a store whose load() throws raises a CONFIGURATION error, not a transport one', async () => {
  const boom = new Error('redis: ECONNREFUSED');
  const mem = createMemory({
    store: {
      load() {
        throw boom;
      },
      save() {},
    },
  });

  await assert.rejects(() => mem.messages(), (err: unknown) => {
    assert.ok(err instanceof nRouterConfigurationError, 'wrong class');
    assert.equal((err as any).kind, 'configuration');
    assert.equal(
      isRetryable(err),
      false,
      'a retryable classification here spins a caller `while (isRetryable(e))` loop forever'
    );
    // The cause is PRESERVED but SANITIZED — errors.ts `sanitizeCause` rebuilds
    // it, because a raw store failure can carry a connection object holding a
    // credential (Rule #5). So this asserts the diagnosis survived, never
    // object identity: `cause === boom` would be a false requirement that
    // pushes someone to delete the redaction.
    const cause = (err as any).cause;
    assert.ok(cause instanceof Error, 'the underlying failure was discarded');
    assert.match(cause.message, /ECONNREFUSED/);
    assert.notEqual(cause, boom, 'the raw cause was attached unsanitized');
    return true;
  });
});

test('a store whose save() rejects raises a CONFIGURATION error', async () => {
  const mem = createMemory({
    store: {
      load: () => [],
      async save() {
        throw new Error('disk full');
      },
    },
  });

  await assert.rejects(() => mem.add({ role: 'user', content: 'hi' }), (err: unknown) => {
    assert.equal((err as any).kind, 'configuration');
    assert.equal(isRetryable(err), false);
    return true;
  });
});

test('a store failure does NOT wedge the memory — the next call still runs', async () => {
  // The serialization chain must survive a rejection. If a failed add poisons
  // the chain, one bad Redis blip silently kills every later add in the process.
  let fail = true;
  let rows: Array<{ role: string; content: string }> = [];
  const mem = createMemory({
    store: {
      load: () => rows.map((m) => ({ ...m })),
      save(messages: Array<{ role: string; content: string }>) {
        if (fail) throw new Error('transient');
        rows = messages.map((m) => ({ ...m }));
      },
    },
  });

  await assert.rejects(() => mem.add({ role: 'user', content: 'lost' }));
  fail = false;
  await mem.add({ role: 'user', content: 'kept' });

  assert.deepEqual(await mem.messages(), [{ role: 'user', content: 'kept' }]);
});

test('a store returning a NON-array is a configuration error, not a silent empty history', async () => {
  // Failing open here would drop the whole conversation and send a bare turn
  // to the provider, which reads as a model that forgot rather than a broken
  // store.
  const mem = createMemory({ store: { load: () => null as any, save: () => {} } });
  await assert.rejects(() => mem.messages(), nRouterConfigurationError);
});

// ---------------------------------------------------------------------------
// Case 7 — shape validation
// ---------------------------------------------------------------------------

test('a message with no role, or an unknown role, is refused', async () => {
  const mem = createMemory();
  await assert.rejects(() => mem.add({ content: 'hi' } as any), nRouterConfigurationError);
  await assert.rejects(
    () => mem.add({ role: 'root', content: 'hi' } as any),
    nRouterConfigurationError
  );
  await assert.rejects(() => mem.add(null as any), nRouterConfigurationError);
});

test('the module documents itself as CLIENT-SIDE ONLY', async () => {
  // Not decoration. The gateway remembers nothing between requests, and a
  // reader who assumes otherwise builds a feature on state that does not
  // exist. This assertion is what keeps that sentence from being deleted as
  // a stale comment.
  const fs = require('node:fs');
  const path = require('node:path');
  const src = fs.readFileSync(
    path.join(__dirname, '..', 'src', 'memory.ts'),
    'utf8'
  );
  assert.match(src, /CLIENT-SIDE ONLY/);
  assert.match(src, /gateway (stores|remembers) nothing/i);
});
