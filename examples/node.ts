// nRouter — Node.js / TypeScript
// OpenAI SDK + guardrails + prompt templates + cache + cost tracking.
//
// npm install openai

import OpenAI from "openai";

const NROUTER_BASE = "https://api.nrouter.ai";
const NROUTER_KEY = process.env.NROUTER_API_KEY;
if (!NROUTER_KEY) {
  console.error("Set NROUTER_API_KEY environment variable. Get your key at https://nrouter.ai/keys");
  process.exit(1);
}
const headers = { Authorization: `Bearer ${NROUTER_KEY}` };

const client = new OpenAI({ apiKey: NROUTER_KEY, baseURL: `${NROUTER_BASE}/v1` });

// ━━━ 1. DISCOVER ORG CONFIG ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
const guardrails = await fetch(`${NROUTER_BASE}/nrouter/guardrail/list`, { headers }).then(r => r.json());
console.log("Guardrails:", guardrails.data?.map((g: any) => g.guardrail_name));

const prompts = await fetch(`${NROUTER_BASE}/nrouter/prompt/list`, { headers }).then(r => r.json());
console.log("Prompts:", prompts.data?.map((p: any) => p.name));

const balance = await fetch(`${NROUTER_BASE}/api/credits/balance`, { headers }).then(r => r.json());
console.log(`Credits: $${balance.available}`);

// ━━━ 2. BASIC CALL (org defaults auto-apply) ━━━━━━━━━━━━━━━
// Guardrails, cache, and rate limits are all enforced server-side.
// No extra code needed — just call the API normally.
const response = await client.chat.completions.create({
  model: "claude-sonnet-4-20250514",
  messages: [{ role: "user", content: "Hello!" }],
});
console.log(response.choices[0].message.content);

// ━━━ 3. WITH PROMPT TEMPLATE + VARIABLES ━━━━━━━━━━━━━━━━━━━
// Prompt templates are opt-in: pass the template ID + Jinja2 variables.
// The template's system prompt is injected server-side before the LLM call.
const withPrompt = await client.chat.completions.create({
  model: "gpt-4o",
  messages: [{ role: "user", content: "Q1 revenue was $4.2M..." }],
  // @ts-expect-error nRouter-specific fields
  nrouter_prompt_template_id: "your-summarizer-id",
  nrouter_prompt_variables: { language: "Spanish", max_length: "100" },
});

// ━━━ 4. OVERRIDE GUARDRAILS (run only specific ones) ━━━━━━━
// By default, ALL org-enabled guardrails apply automatically.
// Pass nrouter_guardrail_ids to run only a subset on this request.
const withGuardrails = await client.chat.completions.create({
  model: "gpt-4o",
  messages: [{ role: "user", content: "Summarize Q1 earnings..." }],
  // @ts-expect-error nRouter-specific fields
  nrouter_guardrail_ids: ["guardrail-uuid-1", "guardrail-uuid-2"],
});

// ━━━ 5. DISABLE CACHE (per-request opt-out) ━━━━━━━━━━━━━━━━
// Cache is enabled by default. Pass nrouter_cache: false for fresh responses.
const noCacheResponse = await client.chat.completions.create({
  model: "gpt-4o",
  messages: [{ role: "user", content: "What's the latest news?" }],
  // @ts-expect-error nRouter-specific fields
  nrouter_cache: false,
});

// ━━━ 6. READ COST + METADATA FROM RESPONSE ━━━━━━━━━━━━━━━━━
const raw = await client.chat.completions
  .create({ model: "gpt-4o-mini", messages: [{ role: "user", content: "Hi" }] })
  .asResponse();
const cost = raw.headers.get("x-nr-request-cost");
const costStatus = raw.headers.get("x-nr-cost-status");
console.log(cost === null ? `Cost status: ${costStatus}` : `Cost: $${cost}`);
console.log(`Model: ${raw.headers.get("x-nr-model")}`);
console.log(`Total tokens: ${raw.headers.get("x-nr-total-tokens")}`);

// ━━━ 7. HANDLE ERRORS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
try {
  await client.chat.completions.create({
    model: "gpt-4o",
    messages: [{ role: "user", content: "My SSN is 123-45-6789" }],
  });
} catch (e: any) {
  if (e.status === 400) console.log(`Guardrail blocked: ${e.message}`);
  if (e.status === 402) console.log(`Insufficient credits: ${e.message}`);
  if (e.status === 429) console.log(`Rate limited: ${e.message}`);
}

// ━━━ 8. STREAMING + EMBEDDINGS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
const stream = await client.chat.completions.create({
  model: "gpt-4o", messages: [{ role: "user", content: "Write a haiku" }], stream: true,
});
for await (const chunk of stream) {
  process.stdout.write(chunk.choices[0]?.delta?.content || "");
}

const embed = await client.embeddings.create({
  model: "text-embedding-3-small", input: "Hello world",
});

// ━━━ 9. CHECK SPEND ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
const newBalance = await fetch(`${NROUTER_BASE}/api/credits/balance`, { headers }).then(r => r.json());
console.log(`\nSpent: $${(balance.available - newBalance.available).toFixed(4)}`);
