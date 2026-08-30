// Model discovery — NRouterModels(client) with list / ids / get / has.
//
// The load-bearing decision under test is that discovery reads the RAW
// response body rather than the vendor SDK's parsed page object: OpenAI JS
// receives the right bytes from nRouter and exposes an EMPTY `data` array.
// A future "simplify this to client.models.list()" compiles, returns a
// well-formed empty list, and makes every caller conclude the account has no
// models — which is why the empty-envelope cases below are pinned.

const { test } = require('node:test');
const assert = require('node:assert/strict');

const { NRouterModels } = require('../dist/models');

/** A RawRequester double that records the path and answers with a canned body. */
function fakeClient(bodyByPath: Record<string, unknown> | ((path: string) => unknown)) {
  const seen: string[] = [];
  return {
    seen,
    get(path: string) {
      seen.push(path);
      const body =
        typeof bodyByPath === 'function' ? bodyByPath(path) : bodyByPath[path];
      return {
        asResponse: () => Promise.resolve({ json: () => Promise.resolve(body) }),
      };
    },
  };
}

const LIST_BODY = {
  object: 'list',
  data: [
    { id: 'claude-haiku-4-5', object: 'model', owned_by: 'nrouter' },
    { id: 'gpt-4o', object: 'model', owned_by: 'nrouter' },
  ],
};

test('list() reads the raw envelope and keeps every field the gateway sent', async () => {
  const client = fakeClient({ '/models': LIST_BODY });
  const models = new NRouterModels(client);
  const listed = await models.list();

  assert.deepEqual(client.seen, ['/models']);
  assert.equal(listed.data.length, 2);
  assert.equal(listed.data[0].id, 'claude-haiku-4-5');
  assert.equal(listed.object, 'list', 'envelope fields must survive, not be discarded');
});

test('an unexpected 2xx shape degrades to an empty list rather than crashing', async () => {
  // A proxy returning HTML, or a gateway version that renames the envelope.
  // Discovery is usually decorative; a crash there takes down a whole app.
  for (const body of [null, 'a string', 42, {}, { data: 'not an array' }, []]) {
    const models = new NRouterModels(fakeClient({ '/models': body }));
    assert.deepEqual(await models.list(), { data: [] }, `body ${JSON.stringify(body)}`);
  }
});

test('ids() returns ids in gateway order and drops entries without one', async () => {
  // An `undefined` id fed into a `model:` field becomes the string "undefined"
  // and a baffling upstream error.
  const client = fakeClient({
    '/models': { data: [{ id: 'a' }, { object: 'model' }, { id: '' }, { id: 'b' }] },
  });
  assert.deepEqual(await new NRouterModels(client).ids(), ['a', 'b']);
});

test('get() preserves model namespace slashes and encodes each component', async () => {
  // `meta/llama-3.1-70b` interpolated unencoded splits into two path segments
  // and silently addresses a DIFFERENT resource.
  const client = fakeClient((path: string) => ({ id: decodeURIComponent(path.slice('/models/'.length)) }));
  const models = new NRouterModels(client);

  await models.get('meta/llama-3.1-70b');
  assert.equal(client.seen[0], '/models/meta/llama-3.1-70b');

  await models.get('anthropic.claude-sonnet-4-5:0');
  assert.equal(client.seen[1], '/models/anthropic.claude-sonnet-4-5%3A0');
});

test('get() refuses an empty id rather than silently calling the LIST endpoint', async () => {
  const client = fakeClient({});
  const models = new NRouterModels(client);
  for (const bad of ['', '   ']) {
    await assert.rejects(() => models.get(bad), TypeError);
  }
  assert.deepEqual(client.seen, [], 'nothing may be sent for a missing id');
});

test('get() refuses a 2xx body with no string id', async () => {
  const models = new NRouterModels(fakeClient({ '/models/x': { object: 'model' } }));
  await assert.rejects(() => models.get('x'));
});

test('has() is EXACT and case-sensitive', async () => {
  // Model aliases are case-sensitive on the wire, so a case-insensitive match
  // answers true and then fails at call time — a cheap correct pre-flight turned
  // into a false reassurance.
  const models = new NRouterModels(fakeClient({ '/models': LIST_BODY }));
  assert.equal(await models.has('gpt-4o'), true);
  assert.equal(await models.has('GPT-4o'), false);
  assert.equal(await models.has('gpt-4'), false);
});

test('has() lets an auth or transport failure propagate as itself', async () => {
  // Implemented over ids(), not get(), so a 401 or a timeout is not reported
  // as "the model does not exist".
  const boom = new Error('401 unauthorized');
  const client = {
    get() {
      return { asResponse: () => Promise.reject(boom) };
    },
  };
  await assert.rejects(() => new NRouterModels(client).has('gpt-4o'), /401/);
});
