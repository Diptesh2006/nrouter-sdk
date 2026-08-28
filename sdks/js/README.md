# @nrouter_ai/sdk (JS/TS)

SDK for the [nRouter](https://nrouter.ai) LLM gateway: one API key for models
across six provider clouds. It wraps the official `openai` package with the
same API surface, pre-configured for nRouter.

As of 2026-08-29, the runnable examples use an Anthropic Claude model returned
by the public catalogue. The SDK does not restrict you to Anthropic: pass any
model returned by `client.nrouterModels.list()` for your key.

## Install

```bash
npm install @nrouter_ai/sdk
```

## Usage

```typescript
import { nRouter } from "@nrouter_ai/sdk";

const client = new nRouter(); // reads NROUTER_API_KEY from env

const response = await client.chat.completions.create({
  model: "anthropic/claude-sonnet-4-5-20250929",
  messages: [{ role: "user", content: "Hello!" }],
});
console.log(response.choices[0].message.content);
```

```javascript
const { nRouter } = require("@nrouter_ai/sdk");

const client = new nRouter({ apiKey: process.env.NROUTER_API_KEY });
```

`nRouter` extends the `OpenAI` class directly, so every resource the `openai`
package supports (`chat.completions`, `embeddings`, `images`, streaming, ...)
works unmodified.

## nRouter Helpers

Use `client.nr.chat()` when you want nRouter features and response metadata in
one call:

```typescript
const result = await client.nr.chat({
  model: "anthropic/claude-sonnet-4-5-20250929",
  prompt: "Summarize this ticket.",
  systemPrompt: "Be concise.",
  guardrailIds: ["<guardrail-id>"], // omit to apply all org-enabled guardrails
  promptTemplateId: "<prompt-template-id>",
  promptVariables: { customer: "Acme" },
  cache: false, // force provider egress; omit or true uses the gateway default
});

console.log(client.nr.text(result));
console.log(result.meta.requestId, result.meta.cost, result.meta.model);
```

Other helpers:

- `client.nr.compare(options, models)` runs one prompt against several models
  and returns results in the same order as `models`.
- `client.nr.stream(options, signal)` opens an SSE stream with typed errors.
- `client.nr.responses(body, options)` posts to `/v1/responses` and applies the
  same nRouter guardrail, prompt-template and cache fields.
- `client.nr.messages(body, options)` posts to `/v1/messages` for Anthropic-style
  message bodies while keeping nRouter metadata and errors.
- `client.nr.countTokens(body)` posts to `/v1/messages/count_tokens`; the body is
  sent unchanged so callers can use the gateway token-count contract directly.
- `client.nr.meta(headers)` parses `x-nr-*` headers from a response you obtained
  another way.
- `client.nr.media.speech()`, `.transcribe()`, `.translate()`, `.image()`,
  `.video()`, `.videoStatus()`, `.videoContent()` and `.embeddings()` cover the
  non-chat endpoints with the same metadata and error handling.

## Model Discovery

Use the nRouter helper for model listing:

```typescript
const models = await client.nrouterModels.list();
console.log(models.data[0].id);
```

The raw nRouter `/models` response is valid JSON, but the current OpenAI JS SDK
page parser exposes it with an empty `data` array. `nrouterModels.list()`
bypasses that parser and returns the gateway response directly. It still travels
the client's own request pipeline, so a configured `fetch`, `timeout`,
`maxRetries`, `httpAgent` and default headers apply to it exactly as they do to
every other call.

## Development

```bash
npm ci
npm test
```

The test suite runs TypeScript test files directly through Node's built-in test
runner, so use Node `22.18.0` or newer. Older Node 22 builds fail before the
tests execute because they cannot strip TypeScript syntax from `.ts` test files.
