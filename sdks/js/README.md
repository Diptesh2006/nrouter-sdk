# @nrouter/sdk (JS/TS)

SDK for the [nRouter](https://nrouter.ai) LLM gateway — one API key for models across six provider clouds (Alibaba US, OpenAI, AWS Bedrock, Azure Foundry, Google Vertex AI, Anthropic). A thin wrapper
around the official `openai` package — same API surface, pre-configured for nRouter.

## Install

```bash
npm install @nrouter/sdk
```

## Usage

```typescript
import { nRouter } from "@nrouter/sdk";

const client = new nRouter(); // reads NROUTER_API_KEY from env

const response = await client.chat.completions.create({
  model: "claude-sonnet-4-20250514",
  messages: [{ role: "user", content: "Hello!" }],
});
console.log(response.choices[0].message.content);
```

```javascript
const { nRouter } = require("@nrouter/sdk");

const client = new nRouter({ apiKey: process.env.NROUTER_API_KEY });
```

`nRouter` extends the `OpenAI` class directly, so every resource the `openai` package
supports (`chat.completions`, `embeddings`, `images`, streaming, ...) works unmodified.

## Basic only, for now

This is a minimal wrapper: API key resolution/validation (`sk-nrouter-...`) and a
default `baseURL` of `https://api.nrouter.ai/v1`. It doesn't yet have the typed errors,
automatic cost-header capture, or `credits`/`guardrails`/`prompts` namespaces that
[`sdks/python/`](../python/) has — see that package for the fuller pattern this one will
grow into.
