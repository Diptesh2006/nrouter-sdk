// nRouter Node.js / TypeScript example.
//
// npm install @nrouter_ai/sdk
// npx tsx examples/node.ts
// set NROUTER_API_KEY before running.

import {
  nRouter,
  createMemory,
  promptTemplate,
  systemVariableConflicts,
} from "@nrouter_ai/sdk";

const MODEL = "claude-sonnet-4-5-20250929";
const client = new nRouter();

function printResult(name: string, result: Awaited<ReturnType<typeof client.nr.chat>>) {
  console.log(`\n${name}`);
  console.log(client.nr.text(result));
  console.log({
    requestId: result.meta.requestId,
    model: result.meta.model,
    cost: result.meta.cost,
    costStatus: result.meta.costStatus,
    inputTokens: result.meta.inputTokens,
    outputTokens: result.meta.outputTokens,
    responseCache: result.meta.responseCache,
  });
}

async function main() {
  const models = await client.nrouterModels.list();
  console.log("available models");
  console.log(models.data.map((model) => model.id).slice(0, 5));

  // Basic Claude call. nr.chat() selects /messages for Claude models and
  // translates the response back to an OpenAI-style completion.
  const chat = await client.nr.chat({
    model: MODEL,
    prompt: "Reply exactly: basic-ok",
    maxTokens: 16,
    cache: false,
  });
  printResult("basic chat", chat);

  // Cache metadata. Same prompt twice should normally show miss then hit.
  const cacheA = await client.nr.messages({
    model: MODEL,
    messages: [{ role: "user", content: "Reply exactly: cache-ok" }],
    max_tokens: 16,
  });
  const cacheB = await client.nr.messages({
    model: MODEL,
    messages: [{ role: "user", content: "Reply exactly: cache-ok" }],
    max_tokens: 16,
  });
  console.log("\ncache");
  console.log({
    first: cacheA.meta.responseCache,
    second: cacheB.meta.responseCache,
    secondAge: cacheB.meta.responseCacheAge,
  });

  // Count tokens. This endpoint is not billed.
  const count = await client.nr.countTokens({
    model: MODEL,
    messages: [{ role: "user", content: "Count this short sentence." }],
  });
  console.log("\ncount tokens");
  console.log(count.body);

  // Streaming. Use .text() to drain the SDK stream helper.
  const stream = await client.nr.stream({
    model: MODEL,
    prompt: "Reply exactly: stream-ok",
    maxTokens: 16,
    cache: false,
  });
  console.log("\nstream");
  console.log(await stream.text());
  console.log({ requestId: stream.meta.requestId, costStatus: stream.meta.costStatus });

  // Compare two visible models. Results stay in the same order as the input
  // model list.
  const compared = await client.nr.compare(
    {
      prompt: "Reply with exactly one word: ok",
      maxTokens: 12,
      cache: false,
    },
    ["claude-haiku-4-5-20251001", MODEL],
  );
  console.log("\ncompare");
  console.log(compared.map((result) => client.nr.text(result)));

  // Client-side memory. The gateway stores no conversation state; this just
  // keeps local messages you explicitly pass back in.
  const memory = createMemory();
  await memory.add({ role: "user", content: "Reply exactly: memory-ok" });
  const remembered = await client.nr.chat({
    model: MODEL,
    messages: await memory.messages(),
    maxTokens: 16,
    cache: false,
  });
  printResult("memory", remembered);

  // Optional prompt template. Set NROUTER_PROMPT_TEMPLATE_ID to exercise a real
  // template; the example skips this instead of sending a placeholder.
  if (process.env.NROUTER_PROMPT_TEMPLATE_ID) {
    const selection = promptTemplate(process.env.NROUTER_PROMPT_TEMPLATE_ID, {
      language: "English",
    });
    const prompted = await client.nr.chat({
      model: MODEL,
      prompt: "Reply exactly: prompt-ok",
      maxTokens: 16,
      promptTemplateId: selection.templateId,
      promptVariables: selection.variables,
      cache: false,
    });
    printResult("prompt template", prompted);
  } else {
    console.log("\nprompt template skipped: set NROUTER_PROMPT_TEMPLATE_ID to test it");
  }

  // Guardrails run server-side from dashboard policy. There is no per-request
  // guardrail override; this local refusal proves callers cannot pretend there is.
  try {
    await client.nr.chat({
      model: MODEL,
      prompt: "This should fail before the network.",
      maxTokens: 16,
      guardrailIds: ["gr_test"],
    });
  } catch (error) {
    console.log("\nguardrailIds local refusal");
    console.log(error instanceof Error ? error.message : error);
  }

  console.log("\nsystem variable conflicts");
  console.log(systemVariableConflicts({ model: "fake", org_name: "fake" }));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
