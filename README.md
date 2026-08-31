# nRouter SDK & Examples

[![npm](https://img.shields.io/npm/v/%40nrouter_ai%2Fsdk?logo=npm&label=%40nrouter_ai%2Fsdk)](https://www.npmjs.com/package/@nrouter_ai/sdk)
[![PyPI](https://img.shields.io/pypi/v/nrouter-sdk?logo=pypi&logoColor=white&label=nrouter-sdk)](https://pypi.org/project/nrouter-sdk/)
[![crates.io](https://img.shields.io/crates/v/nrouter?logo=rust&label=nrouter)](https://crates.io/crates/nrouter)
[![pub.dev](https://img.shields.io/pub/v/nrouter?logo=dart&label=nrouter)](https://pub.dev/packages/nrouter)
[![R-universe](https://nrouterai.r-universe.dev/nrouter/badges/version)](https://nrouterai.r-universe.dev/nrouter)
[![Go Reference](https://pkg.go.dev/badge/github.com/nRouterAI/nrouter-sdk/sdks/go.svg)](https://pkg.go.dev/github.com/nRouterAI/nrouter-sdk/sdks/go)
[![Socket](https://badge.socket.dev/npm/package/@nrouter_ai/sdk/latest)](https://socket.dev/npm/package/@nrouter_ai/sdk)
[![npm publish](https://github.com/nRouterAI/nrouter-sdk/actions/workflows/publish-npm.yml/badge.svg)](https://github.com/nRouterAI/nrouter-sdk/actions/workflows/publish-npm.yml)
[![PyPI publish](https://github.com/nRouterAI/nrouter-sdk/actions/workflows/publish-pypi.yml/badge.svg)](https://github.com/nRouterAI/nrouter-sdk/actions/workflows/publish-pypi.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

SDK and code examples for the [nRouter](https://nrouter.ai) LLM gateway.

## Supported today: JavaScript/TypeScript, Python, Java, Kotlin, Android, Rust, Dart / Flutter

**Seven SDKs are registry-published and supported.** Swift and Go have immutable
source-resolution tags. R is available via R-universe public preview. All ten are held
to the same conformance and security gates.

| SDK | Registry | Registry URL | Package | Version |
|---|---|---|---|---|
| JavaScript / TypeScript | npm | [npmjs.com/package/@nrouter_ai/sdk](https://www.npmjs.com/package/@nrouter_ai/sdk) | `@nrouter_ai/sdk` | 2.0.0 |
| Python | PyPI | [pypi.org/project/nrouter-sdk](https://pypi.org/project/nrouter-sdk/) | `nrouter-sdk` | 2.1.3 |
| Java | Maven Central | [central.sonatype.com](https://central.sonatype.com/artifact/ai.nrouter/nrouter-sdk) | `ai.nrouter:nrouter-sdk` | 1.0.0 |
| Kotlin | Maven Central | [central.sonatype.com](https://central.sonatype.com/artifact/ai.nrouter/nrouter-sdk-kotlin) | `ai.nrouter:nrouter-sdk-kotlin` | 2.1.0 |
| Android | Maven Central | [central.sonatype.com](https://central.sonatype.com/artifact/ai.nrouter/nrouter-sdk-android) | `ai.nrouter:nrouter-sdk-android` | 2.1.0 |
| Rust | crates.io | [crates.io/crates/nrouter](https://crates.io/crates/nrouter) | `nrouter` | 2.1.0 |
| Dart / Flutter | pub.dev | [pub.dev/packages/nrouter](https://pub.dev/packages/nrouter) | `nrouter` | 2.1.1 |

`sdks/{go,swift,r}` are held to the same public wire contract. The six first-party
native transports expose named helpers for all 15 supported gateway operations; Android
delegates that exact surface to Kotlin. Swift and Go resolve from their tagged source releases.

Read those versions off the registries rather than this table if the difference
would matter; the badges above are live and this text is not.


One API key for models across six provider clouds — Alibaba US, OpenAI, AWS Bedrock, Azure Foundry, Google Vertex AI and Anthropic. nRouter serves the OpenAI wire format and Anthropic's Messages API natively, plus embeddings, audio, images and video.

One key. One bill. The live multi-provider catalog. Guardrails, prompt templates, and cost
tracking built in. Browse the exact models available now at
[nrouter.ai/api/public/models](https://nrouter.ai/api/public/models).

Live catalogue note: as of 2026-08-29, the public examples use Anthropic
Claude models because those are the models currently live through the gateway.
Other provider routes may exist in the SDK contract, but examples should use a
model returned by your own `/v1/models` response before spending.

## Authentication & API Keys

All nRouter SDKs automatically read your API key from the `NROUTER_API_KEY` environment variable:

```bash
# 1. Get your API key from https://nrouter.ai/dashboard/keys
export NROUTER_API_KEY="sk-nrouter-your-api-key-here"
```

All API keys must start with the `sk-nrouter-` prefix. You can also pass the key explicitly in code via the `apiKey` / `api_key` parameter in any SDK constructor.

---

## Quick Start

### TypeScript / JavaScript
```bash
npm install @nrouter_ai/sdk
```
```typescript
import { nRouter } from "@nrouter_ai/sdk";

const client = new nRouter(); // reads NROUTER_API_KEY from environment
const res = await client.nr.chat({
  model: "claude-sonnet-4-5-20250929",
  prompt: "Hello from TypeScript!",
});
console.log(client.nr.text(res));
console.log(`Cost: $${res.meta.cost ?? "unpriced"}`);
```

### Python
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
print(f"Cost: ${client.last_response.cost}" if client.last_response.cost else "Cost: unpriced")
```

### Java
```xml
<dependency>
    <groupId>ai.nrouter</groupId>
    <artifactId>nrouter-sdk</artifactId>
    <version>1.0.0</version>
</dependency>
```
```java
import ai.nrouter.sdk.NRouter;
import com.openai.client.OpenAIClient;
import com.openai.models.chat.completions.*;

OpenAIClient client = NRouter.create(); // reads NROUTER_API_KEY
ChatCompletion res = client.chat().completions().create(
    ChatCompletionCreateParams.builder()
        .model("claude-sonnet-4-5-20250929")
        .addMessage(ChatCompletionMessageParam.ofUser(
            ChatCompletionUserMessageParam.builder().content("Hello!").build()
        ))
        .build()
);
System.out.println(res.choices().get(0).message().content());
```

### Swift
```swift
// Swift Package Manager
.package(url: "https://github.com/nRouterAI/nrouter-sdk.git", from: "2.1.1")
```
```swift
import NRouter

let client = try NRouter() // reads NROUTER_API_KEY
let res = try await client.chatCompletions([
    "model": "claude-sonnet-4-5-20250929",
    "messages": [["role": "user", "content": "Hello!"]]
])
print(res.meta.isPriced ? "Cost: $\(res.meta.cost!)" : "Cost: unpriced")
```

### Rust
```toml
# Cargo.toml
[dependencies]
nrouter = "2.1.0"
tokio = { version = "1", features = ["macros", "rt-multi-thread"] }
```
```rust
use nrouter::http::Client;
use serde_json::json;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let client = Client::from_env()?; // reads NROUTER_API_KEY
    let out = client.chat_completions(&json!({
        "model": "claude-sonnet-4-5-20250929",
        "messages": [{"role": "user", "content": "Hello from Rust!"}]
    })).await?;
    println!("Response: {:?}", out.body);
    Ok(())
}
```

### Dart / Flutter
```yaml
# pubspec.yaml
dependencies:
  nrouter: ^2.1.1
```
```dart
import 'package:nrouter/nrouter.dart';

final client = NRouter(apiKey: 'sk-nrouter-...');
final result = await client.chatCompletions({
  'model': 'claude-sonnet-4-5-20250929',
  'messages': [{'role': 'user', 'content': 'Hello from Dart!'}],
});
print(result.body['choices']);
client.close();
```

### Kotlin
```kotlin
// build.gradle.kts
dependencies {
    implementation("ai.nrouter:nrouter-sdk-kotlin:2.1.0")
}
```
```kotlin
import ai.nrouter.sdk.NRouter
import org.json.JSONObject

val client = NRouter() // reads NROUTER_API_KEY
val res = client.chatCompletions(
    JSONObject()
        .put("model", "claude-sonnet-4-5-20250929")
        .put("messages", listOf(mapOf("role" to "user", "content" to "Hello from Kotlin!")))
)
println("Cost: ${res.meta.cost?.let { "$$it" } ?: "unpriced"}")
```

### Android
```kotlin
// app/build.gradle.kts
dependencies {
    implementation("ai.nrouter:nrouter-sdk-android:2.1.0")
}
```

### SDK Ecosystem & Status

Ten branded packages, each pre-configured for nRouter. Every one validates the
`sk-nrouter-` prefix before any request and points at `https://api.nrouter.ai/v1`; all
but Dart also resolve `NROUTER_API_KEY` (Dart requires an explicit key — `dart:io` does
not exist in a Flutter web build, so an environment fallback would silently resolve to
nothing):

> **Published status is a fact, not an intention.** Packages marked PUBLISHED
> or PUBLIC PREVIEW below resolve today. A public preview is not a support
> commitment. Each SDK's `PUBLISHING.md` has the release procedure.

| Language | Install | Registry URL | Registry status | Package | Typed errors | `x-nr-*` metadata |
|----------|---------|--------------|---|---------|---|---|
| **Python** | `pip install nrouter-sdk` | [pypi.org/project/nrouter-sdk](https://pypi.org/project/nrouter-sdk/) | ✅ PUBLISHED | [`sdks/python/`](sdks/python/) | ✅ typed wrappers | ✅ `client.last_response` |
| **TypeScript / JS** | `npm install @nrouter_ai/sdk` | [npmjs.com/package/@nrouter_ai/sdk](https://www.npmjs.com/package/@nrouter_ai/sdk) | ✅ PUBLISHED | [`sdks/js/`](sdks/js/) | ✅ 9 codes | ✅ 13 headers |
| **Java** | Maven `ai.nrouter:nrouter-sdk` | [central.sonatype.com](https://central.sonatype.com/artifact/ai.nrouter/nrouter-sdk) | ✅ PUBLISHED | [`sdks/java/`](sdks/java/) | ✅ 9 codes (native HTTP surface) | ✅ 13 headers (native HTTP surface) |
| **Kotlin** | `implementation("ai.nrouter:nrouter-sdk-kotlin:2.1.0")` | [central.sonatype.com](https://central.sonatype.com/artifact/ai.nrouter/nrouter-sdk-kotlin) | ✅ PUBLISHED | [`sdks/kotlin/`](sdks/kotlin/) | ✅ 9 codes | ✅ 13 headers |
| **Android** | `implementation("ai.nrouter:nrouter-sdk-android:2.1.0")` | [central.sonatype.com](https://central.sonatype.com/artifact/ai.nrouter/nrouter-sdk-android) | ✅ PUBLISHED | [`sdks/android/`](sdks/android/) | ✅ 9 codes | ✅ 13 headers |
| **Rust** | `cargo add nrouter` | [crates.io/crates/nrouter](https://crates.io/crates/nrouter) | ✅ PUBLISHED | [`sdks/rust/`](sdks/rust/) | ✅ 9 codes | ✅ 13 headers |
| **Dart / Flutter** | `dart pub add nrouter` | [pub.dev/packages/nrouter](https://pub.dev/packages/nrouter) | ✅ PUBLISHED | [`sdks/dart/`](sdks/dart/) | ✅ 9 codes | ✅ 13 headers |
| **Swift** | SwiftPM, this repo's URL | [github.com/nRouterAI/nrouter-sdk](https://github.com/nRouterAI/nrouter-sdk) | ✅ git tag `2.1.1` | [`sdks/swift/`](sdks/swift/) | ✅ 9 codes | ✅ 13 headers |
| **R** | `install.packages("nrouter", repos = c(nrouterai = "https://nrouterai.r-universe.dev", CRAN = "https://cloud.r-project.org"))` | [nrouterai.r-universe.dev/nrouter](https://nrouterai.r-universe.dev/nrouter) | 🧪 PUBLIC PREVIEW | [`sdks/r/`](sdks/r/) | ✅ 9 classed conditions | ✅ 13 headers |
| **Go** | `go get github.com/nRouterAI/nrouter-sdk/sdks/go@v1.0.1` | [pkg.go.dev/github.com/nRouterAI/nrouter-sdk/sdks/go](https://pkg.go.dev/github.com/nRouterAI/nrouter-sdk/sdks/go) | ✅ git tag `sdks/go/v1.0.1` | [`sdks/go/`](sdks/go/) | ✅ 9 codes | ✅ 13 headers |

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
curl -s https://nrouterai.r-universe.dev/src/contrib/PACKAGES | grep -A4 '^Package: nrouter$'
```

Java keeps its vendor-compatible OpenAI factory and adds a Java 11 native HTTP
surface for all thirteen `x-nr-*` headers and nine typed gateway errors.
JavaScript/TypeScript and the six first-party native clients expose the same
contract. Android delegates those guarantees to Kotlin; Python adds the same
nRouter typing and metadata capture around its vendor client.

**Every SDK is held to one contract.** `conformance/check_conformance.py` reads
[`spec/nrouter-sdk-spec.json`](spec/nrouter-sdk-spec.json) and fails if any SDK drifts on
the base URL, the environment variable, the key prefix, a response header, an error code,
one of the 15 native endpoint helpers, or one of the four native streaming
helpers.
It needs no toolchains, and its `--self-test` proves it goes red rather than merely
printing green. See [`conformance/`](conformance/).

Run the complete local release gate—including all ten language suites, Android
lint/AAR assembly, race/clippy/analyzer checks, and conformance mutation
proof—with:

```bash
scripts/test-all.sh
```

The same command runs `scripts/security-audit.sh` and fails on known advisories
across npm, PyPI, Maven/Gradle, Cargo and Dart dependency graphs. Install
`osv-scanner` and `pip-audit`; missing security tooling fails loudly rather
than silently skipping the audit.

The opt-in live tests are intentionally excluded unless `NROUTER_LIVE=1` is
set, because they make billed inference calls.

Publishing is [`PUBLISHING.md`](PUBLISHING.md): bump the version, merge to `main`, and one workflow per language tests it and ships it. A merge that changes no version publishes nothing.

Swift is the one that does not use a registry: SwiftPM resolves a git repo by
tag, and it reads `Package.swift` from the repository ROOT. That is what
[`Package.swift`](Package.swift) here is for — this directory is the root of the
public `nrouter-sdk` repo, and the manifest uses `path:` to reach
`sdks/swift/`, so the Swift sources stay beside the other eight. Consumers use:

```swift
.package(url: "https://github.com/nRouterAI/nrouter-sdk.git", from: "2.1.1")
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

### Routing strategies are selected by the model value

Routing strategy is a gateway concern, so there is no separate per-language
strategy API to drift. Put a Smart Router alias in `model` to activate its
configured strategy and fallback chain; put a concrete model id there to pin
the call to that model. Every runnable hello-world example accepts
`NROUTER_MODEL` so the same example demonstrates both modes without inventing
client-only routing behavior.

```bash
NROUTER_MODEL=my-production-router ./run-your-example   # alias: strategy + fallback
NROUTER_MODEL=claude-sonnet-4-5-20250929 ./run-your-example  # concrete: pinned
```

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
| **Java (branded)** | `ai.nrouter:nrouter-sdk` | [`sdks/java/`](sdks/java/) · [`examples/hello-world/java.java`](examples/hello-world/java.java) |
| **Kotlin (branded)** | `ai.nrouter:nrouter-sdk-kotlin` | [`sdks/kotlin/`](sdks/kotlin/) · [`examples/hello-world/kotlin.kt`](examples/hello-world/kotlin.kt) |
| **Android (branded)** | `ai.nrouter:nrouter-sdk-android` | [`sdks/android/`](sdks/android/) |
| **Rust (branded)** | `cargo add nrouter` | [`sdks/rust/`](sdks/rust/) · [`examples/hello-world/rust.rs`](examples/hello-world/rust.rs) |
| **Dart / Flutter (branded)** | `dart pub add nrouter` | [`sdks/dart/`](sdks/dart/) |
| **R (branded)** | `install.packages("nrouter", repos = c(nrouterai = "https://nrouterai.r-universe.dev", CRAN = "https://cloud.r-project.org"))` | [`sdks/r/`](sdks/r/) · [`examples/hello-world/r.R`](examples/hello-world/r.R) |
| **Node.js / TypeScript (plain openai)** | `npm install openai` | [`examples/node.ts`](examples/node.ts) |
| **Go** | `go get github.com/nRouterAI/nrouter-sdk/sdks/go@v1.0.1`, or plain `openai-go` | [`examples/go.go`](examples/go.go) |
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

This is the standalone public `nRouterAI/nrouter-sdk` repository:

```
nrouter-sdk/
├── README.md                        ← You are here (single reference for all)
├── LANGUAGES.md                     ← every-language guide (any OpenAI-format client)
├── spec/nrouter-sdk-spec.json       ← Source of truth (headers, errors, endpoints, Rule #14)
├── sdks/
│   ├── python/                      ← Branded SDK → pip install nrouter-sdk
│   ├── js/                          ← Branded SDK → npm install @nrouter_ai/sdk
│   ├── java/                        ← Branded SDK → Maven ai.nrouter:nrouter-sdk
│   ├── kotlin/                      ← Source-preview Kotlin SDK
│   ├── android/                     ← Source-preview Android AAR
│   ├── swift/                       ← SwiftPM package from the root git tag
│   ├── rust/                        ← Source-preview Rust SDK
│   ├── dart/                        ← Source-preview Dart/Flutter SDK
│   ├── go/                          ← Branded SDK → tagged Go module
│   └── r/                           ← Branded SDK → R-universe public preview
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
