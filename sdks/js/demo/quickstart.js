// nRouter JavaScript hello world
//
// npm install @nrouter_ai/sdk
// set NROUTER_API_KEY before running.

const { nRouter } = require("@nrouter_ai/sdk");

const client = new nRouter();

(async () => {
  // A concrete model id pins the request to that model; `nrouter/auto` lets
  // nRouter choose, and `x-nr-model` names the model that answered.
  const model = process.env.NROUTER_MODEL || "claude-sonnet-4-5-20250929";
  const response = await client.nr.chat({
    model,
    prompt: "Reply with one short sentence saying hello from nRouter.",
    maxTokens: 32,
  });

  console.log(client.nr.text(response));
  console.log({
    requestId: response.meta.requestId,
    model: response.meta.model,
    cost: response.meta.cost,
    costStatus: response.meta.costStatus,
  });
})();
