# @nrouter_ai/sdk (JS/TS)

[![npm](https://img.shields.io/npm/v/%40nrouter_ai%2Fsdk?logo=npm&label=npm)](https://www.npmjs.com/package/@nrouter_ai/sdk)
[![Socket](https://badge.socket.dev/npm/package/@nrouter_ai/sdk/latest)](https://socket.dev/npm/package/@nrouter_ai/sdk)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/nRouterAI/nrouter-sdk/blob/main/LICENSE)

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

## Authentication & Setup

The SDK automatically reads your API key from the `NROUTER_API_KEY` environment variable:

```bash
export NROUTER_API_KEY="sk-nrouter-your-api-key-here"
```

## Usage

```typescript
import { nRouter } from "@nrouter_ai/sdk";

const client = new nRouter(); // reads NROUTER_API_KEY from env

const response = await client.nr.chat({
  model: "claude-sonnet-4-5-20250929",
  prompt: "Hello!",
  maxTokens: 32,
});
console.log(client.nr.text(response));
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
  model: "claude-sonnet-4-5-20250929",
  prompt: "Summarize this ticket.",
  systemPrompt: "Be concise.",
  promptTemplateId: "<prompt-template-id>",
  promptVariables: { customer: "Acme" },
  cache: false, // force provider egress; omit or true uses the gateway default
});

console.log(client.nr.text(result));
console.log(result.meta.requestId, result.meta.cost, result.meta.model);
```

Guardrails are **not** selected per request. They are assigned per key, team or
organization in the nRouter dashboard and apply automatically to every call.
The `guardrailIds` option is deprecated and throws a configuration error: the
gateway runs no per-request override, so it never scoped anything.

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
`maxRetries`, `fetchOptions` and default headers apply to it exactly as they do
to every other call.

## Development

```bash
npm ci
npm test
```

The test suite runs TypeScript test files directly through Node's built-in test
runner, so use Node `22.18.0` or newer. Older Node 22 builds fail before the
tests execute because they cannot strip TypeScript syntax from `.ts` test files.

## Requirements

**Node 22 or newer**, declared in `engines`. That is the RUNTIME floor for
anyone installing this package, not just for running its tests: `openai` 7 sets
it and this package inherits it. Before 2.0.0 nothing declared a floor at all,
so an unsupported runtime failed somewhere further in with a worse message.

The dependency tree is deliberately **one package**. `openai` 7 has no
dependencies of its own, where `openai` 4 pulled in 36 transitive packages —
which is where every supply-chain advisory against this package used to come
from.

## How guardrails, budgets and routing work

They are configured in the dashboard and enforced at the **gateway**, not in
this package. The useful guarantee is not that they are always on — it is that
**whatever you have enabled cannot be bypassed by a client**, this one
included, and behaves identically from every nRouter SDK and from raw `curl`.

- [Guardrails](https://nrouter.ai/docs/guides/guardrails) — PII redaction,
  injection protection, secret and keyword scanning, pre-call and post-call.
  Which ones run is resolved per request: the organization's guardrail switch
  first, then the narrowest applicable assignment wins across
  key > team > org > default, and a winner disabled at that scope does not run.
- [Budget controls](https://nrouter.ai/docs/guides/budget-controls) — spend
  limits per key, team and organization.
- [Observability](https://nrouter.ai/docs/guides/observability) — cost and usage
  on billable calls. Free routes are genuinely free and carry no
  `x-nr-request-cost`: `/v1/messages/count_tokens`, and video polling and
  content retrieval.

[Smart Router aliases and fallback chains](https://nrouter.ai/docs/guides/router-settings)
carry two conditions worth knowing before you rely on failover you have not
enabled:

- **Opt-in by what you put in `model`.** An alias gets the strategy and its
  chain; a concrete model is never re-routed and inherits no hidden fallback.
- **Text wires only** — chat completions, responses, messages and legacy
  completions. Audio, image and video calls take a single-provider route and
  are not cross-provider Smart Router wires.
- [Node.js / TypeScript quickstart](https://nrouter.ai/docs/sdks/nodejs) and the
  [API reference](https://nrouter.ai/docs/api-reference).
