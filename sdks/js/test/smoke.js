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

  console.log("JS smoke tests passed");
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
