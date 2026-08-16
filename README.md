# nRouter SDK & Examples

> **Where this lives (corrected 2026-08-02).** This tree hosts the canonical nRouter API
> examples and SDK code (Rule #14). Its authoring home is **inside `nrouter-ent-ai-hub`**, at
> `nrouter-brain/nrouter-ent-ai-hub/nrouter-sdk/` — edit it there. The nRouter monorepo
> vendors it at `04-nroutersdk/` as a **`git subtree --squash`** from this repo's `sdk-only`
> split branch. It is **not** a git submodule — the workspace migrated off submodules on
> 2026-07-22, so there is no `.gitmodules` entry and `git submodule update --init` does nothing.
> A plain clone of the monorepo already contains these files.

OpenAI-compatible SDK and code examples for the [nRouter](https://nrouter.ai) LLM gateway.

One key. One bill. 240+ models. Guardrails, prompt templates, and cost tracking built in.

## Quick Start

### Python (Branded SDK)
```bash
pip install nroutersdk
```
```python
from nroutersdk import nRouter

client = nRouter()  # reads NROUTER_API_KEY from env
response = client.chat.completions.create(
    model="claude-sonnet-4-20250514",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
print(f"Cost: ${client.last_response.cost}")
```

### Any Other Language (OpenAI SDK)
```
base_url  →  https://api.nrouter.ai/v1
api_key   →  NROUTER_API_KEY
```
```typescript
// Node.js — npm install openai
import OpenAI from "openai";
const client = new OpenAI({
  apiKey: process.env.NROUTER_API_KEY,
  baseURL: "https://api.nrouter.ai/v1",
});
```

---

## Supported Endpoints

All endpoints are served by the nRouter gateway at `https://api.nrouter.ai/v1`, which
routes to the upstream providers. You never call a provider directly and you never need a
provider key.

| Endpoint | SDK Method | nRouter Features |
|----------|-----------|---------------|
| `/v1/chat/completions` | `chat.completions.create()` | Guardrails + Prompts + A/B Testing + Credits |
| `/v1/completions` | `completions.create()` | Credits |
| `/v1/embeddings` | `embeddings.create()` | Credits |
| `/v1/images/generations` | `images.generate()` | Credits |
| `/v1/images/edits` | `images.edit()` | Credits |
| `/v1/audio/speech` | `audio.speech.create()` | Credits (TTS) |
| `/v1/audio/transcriptions` | `audio.transcriptions.create()` | Credits (Whisper STT) |
| `/v1/moderations` | `moderations.create()` | Content safety |
| `/v1/rerank` | `POST /v1/rerank` | Credits |
| `/v1/ocr` | `POST /v1/ocr` | Credits |
| `/v1/models` | `models.list()` | Cached 60s |

### Coming Soon
Files, fine-tuning, batches, assistants/threads, vector stores, responses API.

---

## Examples by Language

### SDKs (Direct OpenAI-compatible)

| Language | Install | Example |
|----------|---------|---------|
| **Python (branded)** | `pip install nroutersdk` | [`sdks/python/`](sdks/python/) |
| **Node.js / TypeScript** | `npm install openai` | [`examples/node.ts`](examples/node.ts) |
| **Go** | `go get github.com/openai/openai-go` | [`examples/go.go`](examples/go.go) |
| **Java** | `com.openai:openai-java` | [`examples/java.java`](examples/java.java) |
| **Ruby** | `gem install ruby-openai` | [`examples/ruby.rb`](examples/ruby.rb) |
| **PHP** | `composer require openai-php/client` | [`examples/php.php`](examples/php.php) |
| **C# / .NET** | `dotnet add package OpenAI` | [`examples/dotnet.cs`](examples/dotnet.cs) |
| **cURL** | Built-in | [`examples/curl.sh`](examples/curl.sh) |

### AI Frameworks

| Framework | Install | Example | What Changes |
|-----------|---------|---------|-------------|
| **LangChain** | `pip install langchain-openai` | [`examples/langchain.py`](examples/langchain.py) | `base_url` + `api_key` on `ChatOpenAI` |
| **LlamaIndex** | `pip install llama-index-llms-openai` | [`examples/llamaindex.py`](examples/llamaindex.py) | `api_base` + `api_key` on `OpenAI` |
| **Vercel AI SDK** | `npm install ai @ai-sdk/openai` | [`examples/vercel_ai.ts`](examples/vercel_ai.ts) | `baseURL` on `createOpenAI()` |
| **CrewAI** | `pip install crewai` | [`examples/crewai.py`](examples/crewai.py) | `OPENAI_API_BASE` env var |
| **AutoGen** | `pip install autogen-agentchat` | [`examples/autogen.py`](examples/autogen.py) | `base_url` in config_list |

**Every framework** that supports OpenAI-compatible endpoints works with nRouter. Set `base_url` to `https://api.nrouter.ai/v1` and `api_key` to your `NROUTER_API_KEY`. That's it.

---

## Response Headers

The gateway emits only the following public `x-nr-*` response headers. Most are
conditional; `x-nr-request-id` is the only header present on every response.

| Header | Type | Description |
|--------|------|-------------|
| `x-nr-request-id` | string | Unique request ID (always present) |
| `x-nr-request-cost` | float | Exact cost in USD; absent when the model is unpriced |
| `x-nr-cost-status` | string | `exact` or `unpriced` when cost metadata is available |
| `x-nr-model` | string | Model that served the request |
| `x-nr-input-tokens` | integer | Input token count |
| `x-nr-output-tokens` | integer | Output token count |
| `x-nr-total-tokens` | integer | Total token count, including cache tokens |
| `x-nr-cache-read-tokens` | integer | Cache-read tokens; emitted only when nonzero |
| `x-nr-cache-write-tokens` | integer | Cache-write tokens; emitted only when nonzero |
| `x-nr-limit-source` | string | `key`, `plan`, `team`, `user`, or `budget` on 429 responses |

Python SDK captures these automatically in `client.last_response`. Other languages read them from HTTP response headers.

---

## Structure

```
04-nroutersdk/
├── README.md                        ← You are here (single reference for all)
├── spec/nrouter-sdk-spec.json          ← Source of truth (headers, errors, endpoints)
├── sdks/python/                     ← Branded SDK → pip install nroutersdk
└── examples/
    ├── curl.sh                      ← cURL
    ├── node.ts                      ← Node.js / TypeScript
    ├── go.go                        ← Go
    ├── java.java                    ← Java
    ├── ruby.rb                      ← Ruby
    ├── php.php                      ← PHP
    ├── dotnet.cs                    ← C# / .NET
    ├── langchain.py                 ← LangChain
    ├── llamaindex.py                ← LlamaIndex
    ├── vercel_ai.ts                 ← Vercel AI SDK
    ├── crewai.py                    ← CrewAI
    └── autogen.py                   ← AutoGen
```

This is the **single reference** for all SDK/examples. The playground code generation and docs site pull from these examples.
