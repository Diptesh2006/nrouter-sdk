# nRouter SDK & Examples

[![npm](https://img.shields.io/npm/v/%40nrouter_ai%2Fsdk?logo=npm&label=%40nrouter_ai%2Fsdk)](https://www.npmjs.com/package/@nrouter_ai/sdk)
[![PyPI](https://img.shields.io/pypi/v/nrouter-sdk?logo=pypi&logoColor=white&label=nrouter-sdk)](https://pypi.org/project/nrouter-sdk/)
[![Socket](https://badge.socket.dev/npm/package/@nrouter_ai/sdk/latest)](https://socket.dev/npm/package/@nrouter_ai/sdk)
[![npm publish](https://github.com/nRouterAI/nrouter-sdk/actions/workflows/publish-npm.yml/badge.svg)](https://github.com/nRouterAI/nrouter-sdk/actions/workflows/publish-npm.yml)
[![PyPI publish](https://github.com/nRouterAI/nrouter-sdk/actions/workflows/publish-pypi.yml/badge.svg)](https://github.com/nRouterAI/nrouter-sdk/actions/workflows/publish-pypi.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

SDK and code examples for the [nRouter](https://nrouter.ai) LLM gateway.

One API key for models across six provider clouds — Alibaba US, OpenAI, AWS Bedrock, Azure Foundry, Google Vertex AI and Anthropic. nRouter serves the OpenAI wire format and Anthropic's Messages API natively, plus embeddings, audio, images and video.

One key. One bill. The live multi-provider catalog. Guardrails, prompt templates, and cost
tracking built in. Browse the exact models available now at
[nrouter.ai/api/public/models](https://nrouter.ai/api/public/models).

Live catalogue note: as of 2026-08-29, the public examples use Anthropic
Claude models because those are the models currently live through the gateway.
Other provider routes may exist in the SDK contract, but examples should use a
model returned by your own `/v1/models` response before spending.

## Quick Start

### Python (Branded SDK)
```bash
pip install nrouter-sdk
```
```python
from nroutersdk import nRouter

client = nRouter()  # reads NROUTER_API_KEY from env
response = client.chat.completions.create(
    model="anthropic/claude-sonnet-4-5-20250929",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
print(f"Cost: ${client.last_response.cost}")
```

### Other Branded SDKs

Nine more branded packages, each pre-configured for nRouter. Every one validates the
`sk-nrouter-` prefix before any request and points at `https://api.nrouter.ai/v1`; all
but Dart also resolve `NROUTER_API_KEY` (Dart requires an explicit key — `dart:io` does
not exist in a Flutter web build, so an environment fallback would silently resolve to
nothing):

> **Published status is a fact, not an intention.** Only the packages marked
> PUBLISHED below resolve today (checked 2026-08-26). The rest are complete and
> tested in this repo but not yet on their registry, so their install command
> will fail — build from source until each is released. Each SDK's
> `PUBLISHING.md` has the steps; the backlog is [`open-issues.csv`](open-issues.csv).

| Language | Install | Registry status | Package | Typed errors | `x-nr-*` metadata |
|----------|---------|---|---------|---|---|
| **TypeScript / JS** | `npm install @nrouter_ai/sdk` | ✅ PUBLISHED | [`sdks/js/`](sdks/js/) | vendor SDK's | via `.asResponse()` |
| **Java** | Maven `ai.nrouter:nrouter-sdk` | ✅ PUBLISHED | [`sdks/java/`](sdks/java/) | vendor SDK's | via an OkHttp interceptor |
| **Kotlin** | Maven `ai.nrouter:nrouter-sdk-kotlin` | ⛔ not published | [`sdks/kotlin/`](sdks/kotlin/) | ✅ 9 codes | ✅ 13 headers |
| **Android** | Maven `ai.nrouter:nrouter-sdk-android` | ⛔ not published | [`sdks/android/`](sdks/android/) | ✅ 9 codes | ✅ 13 headers |
| **Swift** | SwiftPM, this repo's URL | ⛔ not published (needs a semver tag) | [`sdks/swift/`](sdks/swift/) | ✅ 9 codes | ✅ 13 headers |
| **Rust** | `cargo add nrouter` | ⛔ not published | [`sdks/rust/`](sdks/rust/) | ✅ 9 codes | ✅ 13 headers |
| **Dart / Flutter** | `dart pub add nrouter` | ⛔ not published | [`sdks/dart/`](sdks/dart/) | ✅ 9 codes | ✅ 13 headers |
| **R** | `install.packages("nrouter", repos = "https://nrouterai.r-universe.dev")` | ⛔ not published | [`sdks/r/`](sdks/r/) | ✅ 9 classed conditions | ✅ 13 headers |
| **Go** | `go get github.com/nRouterAI/nrouter-sdk/sdks/go` | ⛔ not published (needs a `sdks/go/vX.Y.Z` tag) | [`sdks/go/`](sdks/go/) | ✅ 9 codes | ✅ 13 headers |

Verify any row rather than trusting it:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://pypi.org/pypi/nrouter-sdk/json
curl -s -o /dev/null -w "%{http_code}\n" https://registry.npmjs.org/@nrouter_ai%2Fsdk
# crates.io blocks curl's default user agent with a 403, which is NOT an
# answer about the crate. Send one it accepts.
curl -s -A "nrouter-registry-check" -o /dev/null -w "%{http_code}\n" https://crates.io/api/v1/crates/nrouter
curl -s -o /dev/null -w "%{http_code}\n" https://pub.dev/api/packages/nrouter
curl -s https://repo1.maven.org/maven2/ai/nrouter/ | grep -oE 'href="[^"]+"'
# Go has no registry: proxy.golang.org serves whatever a git tag points at, and
# it case-encodes the path (each uppercase letter becomes '!' + lowercase).
curl -s https://proxy.golang.org/github.com/n!router!a!i/nrouter-sdk/sdks/go/@v/list
```

The JS and Java SDKs extend a vendor OpenAI client, which owns the transport and its own
error types; the rest are native clients that map the gateway's nine stable error codes to
typed errors and hand back all thirteen `x-nr-*` headers beside every response.

**Every SDK is held to one contract.** `conformance/check_conformance.py` reads
[`spec/nrouter-sdk-spec.json`](spec/nrouter-sdk-spec.json) and fails if any SDK drifts on
the base URL, the environment variable, the key prefix, a response header or an error code.
It needs no toolchains, and its `--self-test` proves it goes red rather than merely
printing green. See [`conformance/`](conformance/).

Publishing is [`PUBLISHING.md`](PUBLISHING.md): bump the version, merge to `main`, and one workflow per language tests it and ships it. A merge that changes no version publishes nothing.

Swift is the one that does not use a registry: SwiftPM resolves a git repo by
tag, and it reads `Package.swift` from the repository ROOT. That is what
[`Package.swift`](Package.swift) here is for — this directory is the root of the
public `nrouter-sdk` repo, and the manifest uses `path:` to reach
`sdks/swift/`, so the Swift sources stay beside the other eight. Consumers use:

```swift
.package(url: "https://github.com/nRouterAI/nrouter-sdk.git", from: "2.1.0")
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
| **TypeScript / JS (branded)** | `npm install @nrouter_ai/sdk` | [`sdks/js/`](sdks/js/) · [`examples/hello-world/typescript.ts`](examples/hello-world/typescript.ts), [`javascript.js`](examples/hello-world/javascript.js) |
| **Java (branded)** | Maven `ai.nrouter:nrouter-sdk` | [`sdks/java/`](sdks/java/) · [`examples/hello-world/java.java`](examples/hello-world/java.java) |
| **Rust (branded)** | `cargo add nrouter` | [`sdks/rust/`](sdks/rust/) · [`examples/hello-world/rust.rs`](examples/hello-world/rust.rs) |
| **R (branded)** | `remotes::install_github(..., subdir = "nrouter-sdk/sdks/r")` | [`sdks/r/`](sdks/r/) · [`examples/hello-world/r.R`](examples/hello-world/r.R) |
| **Node.js / TypeScript (plain openai)** | `npm install openai` | [`examples/node.ts`](examples/node.ts) |
| **Go** | `go get github.com/openai/openai-go`, or the branded [`sdks/go/`](sdks/go/) | [`examples/go.go`](examples/go.go) |
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
│   ├── js/                          ← Branded SDK → npm install @nrouter_ai/sdk
│   ├── java/                        ← Branded SDK → Maven ai.nrouter:nrouter-sdk
│   ├── rust/                        ← Branded SDK → cargo add nrouter
│   ├── go/                          ← Branded SDK → go get .../sdks/go
│   └── r/                           ← Branded SDK → remotes::install_github(...)
└── examples/
    ├── curl.sh                      ← cURL
    ├── node.ts                      ← Node.js / TypeScript (plain openai)
    ├── go.go                        ← Go (plain openai-go; sdks/go/ is branded)
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

## Documentation

Every link below was checked live before it was written here; none is derived
from the sitemap alone, because a URL can sit in a sitemap and still 404.

**How each capability works**, and where it is enforced — all of these are
gateway-side, so they behave identically from every SDK in this repository:

| Capability | Guide | Product page |
|---|---|---|
| Guardrails — PII redaction, injection protection, pre- and post-call | [docs/guides/guardrails](https://nrouter.ai/docs/guides/guardrails) | [product/guardrails](https://nrouter.ai/product/guardrails) |
| Budgets and spend limits, per key / team / org | [docs/guides/budget-controls](https://nrouter.ai/docs/guides/budget-controls) | [product/budgets](https://nrouter.ai/product/budgets) |
| Routing, fallback chains, failover | [docs/guides/router-settings](https://nrouter.ai/docs/guides/router-settings) | [product/routing](https://nrouter.ai/product/routing) |
| Observability and cost tracking | [docs/guides/observability](https://nrouter.ai/docs/guides/observability) | [product/observability](https://nrouter.ai/product/observability) |
| Prompt templates and versioning | [docs/guides/prompts](https://nrouter.ai/docs/guides/prompts) | — |
| API keys — creation, rotation, scope | [docs/guides/api-key-management](https://nrouter.ai/docs/guides/api-key-management) | — |

**None of this lives in the SDK.** It is configured in the dashboard and
enforced at the gateway on the request path, so whatever you have enabled
applies to a raw `curl` exactly as it does to a branded SDK, and no client can
bypass it. That is the reason a thin client is the right shape here.

⚠️ **Two things are conditional, and assuming otherwise is how you rely on
protection you do not have:**

- **Which guardrails run is resolved per request.** The organization's
  guardrail switch gates everything; below it the narrowest applicable
  assignment wins across key > team > org > default, and a winner disabled at
  that scope does not run. A guardrail you configured is not necessarily a
  guardrail this request gets — check the assignment, not just the switch.
- **Routing is opt-in by what you put in `model`, and applies to text wires
  only.** An alias gets its strategy and fallback chain; a concrete model is
  never re-routed and inherits no hidden platform fallback. Audio, image and
  video take a single-provider route and are not cross-provider Smart Router
  wires.

Cost accounting covers every BILLABLE call. Some routes these SDKs expose are
deliberately free and emit no `x-nr-request-cost` at all —
`/v1/messages/count_tokens`, and video polling and content retrieval — because
they generate no completion. Absent is not zero (Rule #28): a missing cost
header means unpriced or free, never a $0 inference.

**Per-language quickstarts:**
[Python](https://nrouter.ai/docs/sdks/python) ·
[Node.js / TypeScript](https://nrouter.ai/docs/sdks/nodejs) ·
[Go](https://nrouter.ai/docs/sdks/go) ·
[Java](https://nrouter.ai/docs/sdks/java) ·
[PHP](https://nrouter.ai/docs/sdks/php) ·
[Ruby](https://nrouter.ai/docs/sdks/ruby) ·
[curl](https://nrouter.ai/docs/sdks/curl) ·
[OpenAI SDK against nRouter](https://nrouter.ai/docs/sdks/python-openai)

**Reference:**
[Quick start](https://nrouter.ai/docs/getting-started/quick-start) ·
[API reference](https://nrouter.ai/docs/api-reference) ·
[Live model catalogue](https://nrouter.ai/models) ·
[Pricing](https://nrouter.ai/pricing) ·
[Changelog](https://nrouter.ai/changelog)

## Contributing, security, and support

| | |
|---|---|
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to build and test each SDK, and the PR checklist. **Read the version-field warning before you open a PR** — merging `main` publishes immutably. |
| [SECURITY.md](SECURITY.md) | Report a vulnerability privately to `security@nrouter.ai`, never as an issue. Supported version lines per registry. |
| [SUPPORT.md](SUPPORT.md) | SDK bugs go to issues; account, billing, and API-key questions go to `support@nrouter.ai`. |
| [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) | Adapted from the Contributor Covenant 2.1. |
| [CHANGELOG.md](CHANGELOG.md) | Per-registry release history. Each SDK versions independently — do not read across the sections. |
| [PUBLISHING.md](PUBLISHING.md) | How a release actually ships, and which credential each registry needs. |

npm builds **1.1.1 and later** carry [provenance attestations](https://docs.npmjs.com/generating-provenance-statements)
tying the tarball to the exact commit and workflow that produced it — verify
with `npm audit signatures`. 1.0.0 and 1.1.0 were published by hand and have
none; provenance cannot be added to a version after the fact. See
[SECURITY.md](SECURITY.md#release-integrity).
