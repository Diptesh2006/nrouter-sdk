const assert = require("node:assert/strict");
const { nRouter } = require("../dist");

assert.throws(
  () => new nRouter({ apiKey: "bad-key" }),
  /sk-nrouter-/,
  "invalid keys should be rejected before a request is made"
);

let requestedUrl = "";
let requestedAuth = "";
global.fetch = async (url, options) => {
  requestedUrl = url;
  requestedAuth = options.headers.Authorization;
  return {
    ok: true,
    status: 200,
    async json() {
      return {
        data: [{ id: "claude-haiku", object: "model", owned_by: "nrouter" }],
      };
    },
  };
};

(async () => {
  const client = new nRouter({ apiKey: "sk-nrouter-test" });
  const models = await client.nrouterModels.list();

  assert.equal(requestedUrl, "https://api.nrouter.ai/v1/models");
  assert.equal(requestedAuth, "Bearer sk-nrouter-test");
  assert.equal(models.data.length, 1);
  assert.equal(models.data[0].id, "claude-haiku");
  assert.equal(client.nrouter_models, client.nrouterModels);

  // A caller-supplied `fetch` override must win over the global one, so a
  // configured proxy / timeout / instrumentation hook still applies to model
  // discovery. Poison the global to prove the override is the one used.
  let overrideCalls = 0;
  global.fetch = async () => {
    throw new Error("global fetch must not be used when an override is configured");
  };
  const overridden = new nRouter({
    apiKey: "sk-nrouter-test",
    fetch: async () => {
      overrideCalls += 1;
      return { ok: true, status: 200, async json() { return { data: [] }; } };
    },
  });
  await overridden.nrouterModels.list();
  assert.equal(overrideCalls, 1, "the configured fetch override should be used");

  console.log("JS smoke tests passed");
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
