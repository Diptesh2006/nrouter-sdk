// nRouter with the Vercel AI SDK.
//
// npm install ai @ai-sdk/openai zod
// npx tsx examples/vercel_ai.ts
//
// This example uses the Vercel AI OpenAI provider, so it needs a model that
// your nRouter key can use on /v1/chat/completions. If your key currently sees
// only Claude/Anthropic models, use examples/node.ts or @nrouter_ai/sdk
// instead; the nRouter SDK translates Claude calls to /v1/messages.

import { createOpenAI } from "@ai-sdk/openai";
import { generateText } from "ai";

async function main() {
  const model = process.env.NROUTER_OPENAI_WIRE_MODEL;
  if (!model) {
    console.log(
      "Set NROUTER_OPENAI_WIRE_MODEL to a model available on /v1/chat/completions. " +
        "For Claude-only keys, use examples/node.ts with @nrouter_ai/sdk.",
    );
    return;
  }

  const nrouter = createOpenAI({
    apiKey: process.env.NROUTER_API_KEY,
    baseURL: "https://api.nrouter.ai/v1",
  });

  const { text } = await generateText({
    model: nrouter(model),
    prompt: "Reply with one short sentence saying hello from nRouter.",
  });

  console.log(text);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
