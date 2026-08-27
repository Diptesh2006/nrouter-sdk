const assert = require("node:assert/strict");
const { nRouter } = require("../dist");

assert.throws(
  () => new nRouter({ apiKey: "bad-key" }),
  /sk-nrouter-/,
  "invalid keys should be rejected before a request is made"
);

function authOf(init) {
  const h = init && init.headers;
  if (!h) return undefined;
  if (typeof h.get === "function") return h.get("authorization");
  return h.Authorization || h.authorization;
}

(async () => {
  // Model listing must travel the client's OWN request pipeline, so a caller's
  // fetch override / timeout / proxy / default headers apply to it too. Poison
  // the global fetch to prove the configured transport is what runs.
  global.fetch = async () => {
    throw new Error("global fetch must not be used when a transport is configured");
  };

  let seenUrl = "";
  let seenAuth = "";
  let calls = 0;
  const client = new nRouter({
    apiKey: "sk-nrouter-test",
    fetch: async (url, init) => {
      calls += 1;
      seenUrl = String(url);
      seenAuth = authOf(init);
      return new Response(
        JSON.stringify({
          object: "list",
          data: [{ id: "claude-haiku", object: "model", owned_by: "nrouter" }],
        }),
        { status: 200, headers: { "content-type": "application/json" } }
      );
    },
  });

  const models = await client.nrouterModels.list();

  assert.equal(calls, 1, "the configured transport should be the one used");
  assert.equal(seenUrl, "https://api.nrouter.ai/v1/models");
  assert.equal(seenAuth, "Bearer sk-nrouter-test");
  assert.equal(models.data.length, 1);
  assert.equal(models.data[0].id, "claude-haiku");
  assert.equal(client.nrouter_models, client.nrouterModels);

  console.log("JS smoke tests passed");
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
