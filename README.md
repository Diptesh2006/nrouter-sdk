# nRouter SDK & Examples

SDK and code examples for the [nRouter](https://nrouter.ai) LLM gateway.

One API key for models across six provider clouds — Alibaba US, OpenAI, AWS Bedrock, Azure Foundry, Google Vertex AI and Anthropic. nRouter serves the OpenAI wire format and Anthropic's Messages API natively, plus embeddings, audio, images and video.

One key. One bill. The live multi-provider catalog. Guardrails, prompt templates, and cost
tracking built in. Browse the exact models available now at
[nrouter.ai/api/public/models](https://nrouter.ai/api/public/models).

## Quick Start

### Python (Branded SDK)
```bash
pip install nrouter-sdk
```
```python
from nroutersdk import nRouter

client = nRouter()  # reads NROUTER_API_KEY from env
response = client.chat.completions.create(
    model="claude-sonnet-4-5",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
print(f"Cost: ${client.last_response.cost}")
```

### Other Branded SDKs

Eight more branded packages, each pre-configured for nRouter. Every one of them
resolves `NROUTER_API_KEY`, validates the `sk-nrouter-` prefix before any request, and
points at `https://api.nrouter.ai/v1`:

| Language | Install | Package | Typed errors | `x-nr-*` metadata |
|----------|---------|---------|---|---|
| **TypeScript / JS** | `npm install @nrouter/sdk` | [`sdks/js/`](sdks/js/) | vendor SDK's | via `.asResponse()` |
| **Java** | Maven `ai.nrouter:nrouter-sdk` | [`sdks/java/`](sdks/java/) | vendor SDK's | via an OkHttp interceptor |
| **Kotlin** | Maven `ai.nrouter:nrouter-sdk-kotlin` | [`sdks/kotlin/`](sdks/kotlin/) | ✅ 9 codes | ✅ 13 headers |
| **Android** | Maven `ai.nrouter:nrouter-sdk-android` | [`sdks/android/`](sdks/android/) | ✅ 9 codes | ✅ 13 headers |
| **Swift** | SwiftPM `nrouter-sdk-swift` | [`sdks/swift/`](sdks/swift/) | ✅ 9 codes | ✅ 13 headers |
| **Rust** | `cargo add nrouter` | [`sdks/rust/`](sdks/rust/) | ✅ 9 codes | ✅ 13 headers |
| **Dart / Flutter** | `dart pub add nrouter` | [`sdks/dart/`](sdks/dart/) | ✅ 9 codes | ✅ 13 headers |
| **R** | `install.packages("nrouter", repos = "https://nrouterai.r-universe.dev")` | [`sdks/r/`](sdks/r/) | ✅ 9 classed conditions | ✅ 13 headers |

The JS and Java SDKs extend a vendor OpenAI client, which owns the transport and its own
error types; the rest are native clients that map the gateway's nine stable error codes to
typed errors and hand back all thirteen `x-nr-*` headers beside every response.

**Every SDK is held to one contract.** `conformance/check_conformance.py` reads
[`spec/nrouter-sdk-spec.json`](spec/nrouter-sdk-spec.json) and fails if any SDK drifts on
the base URL, the environment variable, the key prefix, a response header or an error code.
It needs no toolchains, and its `--self-test` proves it goes red rather than merely
printing green. See [`conformance/`](conformance/).

Publishing each package is documented in its own `PUBLISHING.md`, per registry.

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
provider key. This table is derived from `spec/nrouter-sdk-spec.json` › `supported_endpoints`
(Rule #14) — edit the spec first, this table second.

| Endpoint | SDK Method | nRouter Features |
|----------|-----------|---------------|
| `/v1/chat/completions` | `chat.completions.create()` | Guardrails + Prompts + A/B Testing + Credits |
| `/v1/completions` | `completions.create()` | Credits |
| `/v1/embeddings` | `embeddings.create()` | Credits |
| `/v1/images/generations` | `images.generate()` | Credits |
| `/v1/audio/speech` | `audio.speech.create()` | Credits (TTS) |
| `/v1/audio/transcriptions` | `audio.transcriptions.create()` | Credits (Whisper STT) |
| `/v1/audio/translations` | `audio.translations.create()` | Credits |
| `/v1/messages` | `client.messages.create()` | Anthropic-compatible buffered call; Credits |
| `/v1/messages/count_tokens` | `POST /v1/messages/count_tokens` | Count before spending |
| `/v1/responses` | `responses.create()` | OpenAI Responses API |
| `/v1/videos` | `POST /v1/videos` | Start a video job (billed) |
| `/v1/videos/{id}` | `GET /v1/videos/{id}` | Poll job status (free) |
| `/v1/videos/{id}/content` | `GET /v1/videos/{id}/content` | Download the video (free) |
| `/v1/models` | `models.list()` | Tenant-filtered model list |
| `/v1/models/{model_id}` | `models.retrieve()` | Retrieve one model |

### Not Served By The Gateway

`spec/nrouter-sdk-spec.json` › `unsupported_endpoints` marks these as never called: files,
fine-tuning, batches, beta/assistants-threads, vector stores, uploads, containers,
conversations, webhooks, image edits, moderations, rerank, OCR. Do not add a client method or
example for any of these without first adding the route to the gateway and the spec.

---

## Examples by Language

### SDKs (direct)

| Language | Install | Example |
|----------|---------|---------|
| **Python (branded)** | `pip install nrouter-sdk` | [`sdks/python/`](sdks/python/) |
| **TypeScript / JS (branded)** | `npm install @nrouter/sdk` | [`sdks/js/`](sdks/js/) · [`examples/hello-world/typescript.ts`](examples/hello-world/typescript.ts), [`javascript.js`](examples/hello-world/javascript.js) |
| **Java (branded)** | Maven `ai.nrouter:nrouter-sdk` | [`sdks/java/`](sdks/java/) · [`examples/hello-world/java.java`](examples/hello-world/java.java) |
| **Rust (branded)** | `cargo add nrouter` | [`sdks/rust/`](sdks/rust/) · [`examples/hello-world/rust.rs`](examples/hello-world/rust.rs) |
| **R (branded)** | `remotes::install_github(..., subdir = "nrouter-sdk/sdks/r")` | [`sdks/r/`](sdks/r/) · [`examples/hello-world/r.R`](examples/hello-world/r.R) |
| **Node.js / TypeScript (plain openai)** | `npm install openai` | [`examples/node.ts`](examples/node.ts) |
| **Go** | `go get github.com/openai/openai-go` | [`examples/go.go`](examples/go.go) |
| **Java (plain openai-java)** | `com.openai:openai-java` | [`examples/java.java`](examples/java.java) |
| **Ruby** | `gem install ruby-openai` | [`examples/ruby.rb`](examples/ruby.rb) |
| **PHP** | `composer require openai-php/client` | [`examples/php.php`](examples/php.php) |
| **C# / .NET** | `dotnet add package OpenAI` | [`examples/dotnet.cs`](examples/dotnet.cs) |
| **cURL** | Built-in | [`examples/curl.sh`](examples/curl.sh) |

`examples/hello-world/` holds one minimal script per NON-Python branded SDK (`typescript.ts`,
`javascript.js`, `java.java`, `rust.rs`, `r.R`) — the first-run smoke test, separate from the
richer per-framework examples above. Python has no `hello-world` entry; `sdks/python/` and the
Quick Start snippet above serve that role for Python.

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

This repo's own path is `nrouter-sdk/` (`04-nroutersdk/` is only the name it takes when
`nrouter-app` vendors it via `git subtree --squash` — see the note at the top of this file):

```
nrouter-sdk/
├── README.md                        ← You are here (single reference for all)
├── LANGUAGES.md                     ← every-language guide (any OpenAI-format client)
├── spec/nrouter-sdk-spec.json       ← Source of truth (headers, errors, endpoints, Rule #14)
├── sdks/
│   ├── python/                      ← Branded SDK → pip install nrouter-sdk
│   ├── js/                          ← Branded SDK → npm install @nrouter/sdk
│   ├── java/                        ← Branded SDK → Maven ai.nrouter:nrouter-sdk
│   ├── rust/                        ← Branded SDK → cargo add nrouter
│   └── r/                           ← Branded SDK → remotes::install_github(...)
└── examples/
    ├── curl.sh                      ← cURL
    ├── node.ts                      ← Node.js / TypeScript (plain openai)
    ├── go.go                        ← Go
    ├── java.java                    ← Java (plain openai-java)
    ├── ruby.rb                      ← Ruby
    ├── php.php                      ← PHP
    ├── dotnet.cs                    ← C# / .NET
    ├── langchain.py                 ← LangChain
    ├── llamaindex.py                ← LlamaIndex
    ├── vercel_ai.ts                 ← Vercel AI SDK
    ├── crewai.py                    ← CrewAI
    ├── autogen.py                   ← AutoGen
    └── hello-world/                 ← one minimal script per non-Python branded SDK
        ├── typescript.ts
        ├── javascript.js
        ├── java.java
        ├── rust.rs
        └── r.R
```

This is the **single reference** for all SDK/examples. The playground code generation and docs site pull from these examples.
