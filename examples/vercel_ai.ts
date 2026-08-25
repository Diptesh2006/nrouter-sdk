// nRouter — Vercel AI SDK (Next.js / React)
// Guardrails + prompt templates + cost tracking in your Next.js app.
//
// npm install ai @ai-sdk/openai

import { createOpenAI } from "@ai-sdk/openai";
import { generateText, streamText, tool } from "ai";
import { z } from "zod";

const nrouterRouter = createOpenAI({
  apiKey: process.env.NROUTER_API_KEY!,
  baseURL: "https://api.nrouter.ai/v1",
});

// ━━━ 1. CHECK GUARDRAILS + PROMPTS + BALANCE ━━━━━━━━━━━━━━

const nrouterBase = "https://api.nrouter.ai";
const headers = { Authorization: `Bearer ${process.env.NROUTER_API_KEY}` };

// Guardrails, prompt templates, rate limits and budgets are configured in the
// dashboard and enforced server-side on every request. There is deliberately no
// endpoint to list or override them: a request cannot opt out of its org policy.
// Balances and spend history live at https://app.nrouter.ai — org billing data,
// not inference. Per-request cost arrives on the x-nr-request-cost header.
// ━━━ 2. GENERATE (org defaults auto-apply) ━━━━━━━━━━━━━━━━
// Cache, guardrails, and rate limits auto-apply from org config.

const { text } = await generateText({
  model: nrouterRouter("claude-sonnet-4-5"),
  prompt: "What is quantum computing?",
});
console.log(text);
// Guardrails checked the prompt before the model saw it.

// ━━━ 3. STREAMING WITH GUARDRAILS ━━━━━━━━━━━━━━━━━━━━━━━━━

const stream = await streamText({
  model: nrouterRouter("gpt-5.5"),
  prompt: "Write a haiku about API security",
});
for await (const chunk of stream.textStream) {
  process.stdout.write(chunk);
}

// ━━━ 4. WITH PROMPT TEMPLATE + VARIABLES ━━━━━━━━━━━━━━━━━━━

const { text: summarized } = await generateText({
  model: nrouterRouter("gpt-5.5"),
  prompt: "Q1 revenue was $4.2M, up 23% YoY with strong enterprise growth...",
  // nRouter-specific: inject a server-side prompt template with Jinja2 variables
  body: {
    nrouter_prompt_template_id: "your-summarizer-id",
    nrouter_prompt_variables: { language: "Spanish", max_length: "100" },
  },
});
console.log(`\nSummarized: ${summarized}`);

// Per-request guardrail selection
// By default, ALL org-enabled guardrails apply automatically.
// Pass nrouter_guardrail_ids to run only specific guardrails on this request.
const { text: guarded } = await generateText({
  model: nrouterRouter("gpt-5.5"),
  prompt: "Summarize Q1 earnings...",
  body: {
    nrouter_guardrail_ids: ["guardrail-uuid-1", "guardrail-uuid-2"],
  },
});

// Disable cache for a single request
// Cache is enabled by default. Pass nrouter_cache: false for a fresh response.
const { text: fresh } = await generateText({
  model: nrouterRouter("gpt-5.5"),
  prompt: "What's the latest news?",
  body: {
    nrouter_cache: false,
  },
});

// ━━━ 5. TOOL CALLING WITH GUARDRAILS ━━━━━━━━━━━━━━━━━━━━━━

const { text: weatherResult } = await generateText({
  model: nrouterRouter("gpt-5.5"),
  prompt: "What's the weather in Tokyo?",
  tools: {
    getWeather: tool({
      description: "Get weather for a city",
      parameters: z.object({ city: z.string() }),
      execute: async ({ city }) => `72°F and sunny in ${city}`,
    }),
  },
});
// Input checked by guardrails BEFORE tool execution.
// Prompt injection attempts are caught before tools run.

// ━━━ 6. NEXT.JS API ROUTE (production pattern) ━━━━━━━━━━━━

// app/api/chat/route.ts
//
// import { createOpenAI } from "@ai-sdk/openai";
// import { streamText } from "ai";
//
// const nrouter = createOpenAI({
//   apiKey: process.env.NROUTER_API_KEY!,
//   baseURL: "https://api.nrouter.ai/v1",
// });
//
// export async function POST(req: Request) {
//   const { messages } = await req.json();
//
//   // Guardrails protect every message automatically.
//   // Prompt templates injected server-side.
//   // Cost tracked per-request.
//   const result = streamText({
//     model: nrouter("gpt-5.5"),
//     messages,
//     body: {
//       nrouter_prompt_template_id: "customer-support-template",
//       nrouter_prompt_variables: { product: "nRouter", tone: "friendly" },
//     },
//   });
//
//   return result.toDataStreamResponse();
// }

