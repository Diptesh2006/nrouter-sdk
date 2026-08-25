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

// Guardrails, prompt templates, rate limits and budgets are configured in the
// dashboard and enforced server-side on every request. There is deliberately no
// endpoint to list or override them: a request cannot opt out of its org policy.
// Balances and spend history live at https://app.nrouter.ai — org billing data,
// not inference. Per-request cost arrives on the x-nr-request-cost header.
// ━━━ 1. BASIC CALL (org defaults auto-apply) ━━━━━━━━━━━━━━━
// Guardrails, cache, and rate limits are all enforced server-side.
// No extra code needed — just call the API normally.
const response = await client.chat.completions.create({
  model: "claude-sonnet-4-5",
  messages: [{ role: "user", content: "Hello!" }],
});
console.log(response.choices[0].message.content);

// ━━━ 2. WITH PROMPT TEMPLATE + VARIABLES ━━━━━━━━━━━━━━━━━━━
// Prompt templates are opt-in: pass the template ID + Jinja2 variables.
// The template's system prompt is injected server-side before the LLM call.
const withPrompt = await client.chat.completions.create({
  model: "gpt-5.5",
  messages: [{ role: "user", content: "Q1 revenue was $4.2M..." }],
  // @ts-expect-error nRouter-specific fields
  nrouter_prompt_template_id: "your-summarizer-id",
  nrouter_prompt_variables: { language: "Spanish", max_length: "100" },
});

// ━━━ 3. OVERRIDE GUARDRAILS (run only specific ones) ━━━━━━━
// By default, ALL org-enabled guardrails apply automatically.
// Pass nrouter_guardrail_ids to run only a subset on this request.
const withGuardrails = await client.chat.completions.create({
  model: "gpt-5.5",
  messages: [{ role: "user", content: "Summarize Q1 earnings..." }],
  // @ts-expect-error nRouter-specific fields
  nrouter_guardrail_ids: ["guardrail-uuid-1", "guardrail-uuid-2"],
});

// ━━━ 4. DISABLE CACHE (per-request opt-out) ━━━━━━━━━━━━━━━━
// Cache is enabled by default. Pass nrouter_cache: false for fresh responses.
const noCacheResponse = await client.chat.completions.create({
  model: "gpt-5.5",
  messages: [{ role: "user", content: "What's the latest news?" }],
  // @ts-expect-error nRouter-specific fields
  nrouter_cache: false,
});

// ━━━ 5. READ COST + METADATA FROM RESPONSE ━━━━━━━━━━━━━━━━━
const raw = await client.chat.completions
  .create({ model: "gpt-5.4-mini", messages: [{ role: "user", content: "Hi" }] })
  .asResponse();
const cost = raw.headers.get("x-nr-request-cost");
const costStatus = raw.headers.get("x-nr-cost-status");
console.log(cost === null ? `Cost status: ${costStatus}` : `Cost: $${cost}`);
console.log(`Model: ${raw.headers.get("x-nr-model")}`);
console.log(`Total tokens: ${raw.headers.get("x-nr-total-tokens")}`);

// ━━━ 6. HANDLE ERRORS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
try {
  await client.chat.completions.create({
    model: "gpt-5.5",
    messages: [{ role: "user", content: "My SSN is 123-45-6789" }],
  });
} catch (e: any) {
  if (e.status === 400) console.log(`Guardrail blocked: ${e.message}`);
  if (e.status === 402) console.log(`Insufficient credits: ${e.message}`);
  if (e.status === 429) console.log(`Rate limited: ${e.message}`);
}

// ━━━ 7. STREAMING + EMBEDDINGS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
const stream = await client.chat.completions.create({
  model: "gpt-5.5", messages: [{ role: "user", content: "Write a haiku" }], stream: true,
});
for await (const chunk of stream) {
  process.stdout.write(chunk.choices[0]?.delta?.content || "");
}

const embed = await client.embeddings.create({
// NOTE: embeddings and image generation are MOUNTED endpoints, but the model
// must be enabled for your org before it will answer. Measured on 2026-08-25 the
// served catalogue carried no embedding and no image model, so the names below
// are illustrative. Check what YOUR key can reach first:
//     print([m.id for m in client.models.list().data])
  model: "text-embedding-3-small", input: "Hello world",
});

