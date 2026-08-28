# @nrouter_ai/sdk (JS/TS)

SDK for the [nRouter](https://nrouter.ai) LLM gateway: one API key for models
across six provider clouds. It wraps the official `openai` package with the
same API surface, pre-configured for nRouter.

## Install

```bash
npm install @nrouter_ai/sdk
```

## Usage

```typescript
import { nRouter } from "@nrouter_ai/sdk";

const client = new nRouter(); // reads NROUTER_API_KEY from env

const response = await client.chat.completions.create({
  model: "claude-sonnet-4-5",
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
