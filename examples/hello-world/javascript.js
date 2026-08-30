// nRouter JavaScript hello world
//
// npm install @nrouter_ai/sdk
// set NROUTER_API_KEY before running.

const { nRouter } = require("@nrouter_ai/sdk");

const client = new nRouter();

(async () => {
  const response = await client.nr.chat({
    model: "claude-sonnet-4-5-20250929",
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
