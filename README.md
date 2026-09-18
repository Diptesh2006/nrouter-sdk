# nRouter SDK & Examples

[![npm](https://img.shields.io/npm/v/%40nrouter_ai%2Fsdk?logo=npm&label=%40nrouter_ai%2Fsdk)](https://www.npmjs.com/package/@nrouter_ai/sdk)
[![PyPI](https://img.shields.io/pypi/v/nrouter-sdk?logo=pypi&logoColor=white&label=nrouter-sdk)](https://pypi.org/project/nrouter-sdk/)
[![R-universe](https://nroutergateway.r-universe.dev/nrouter/badges/version)](https://nroutergateway.r-universe.dev/nrouter)
[![Go Reference](https://pkg.go.dev/badge/github.com/nRouterGateway/nrouter-sdk/sdks/go/v3.svg)](https://pkg.go.dev/github.com/nRouterGateway/nrouter-sdk/sdks/go/v3)
[![Socket](https://badge.socket.dev/npm/package/@nrouter_ai/sdk/latest)](https://socket.dev/npm/package/@nrouter_ai/sdk)
[![npm publish](https://github.com/nRouterGateway/nrouter-sdk/actions/workflows/publish-npm.yml/badge.svg)](https://github.com/nRouterGateway/nrouter-sdk/actions/workflows/publish-npm.yml)
[![PyPI publish](https://github.com/nRouterGateway/nrouter-sdk/actions/workflows/publish-pypi.yml/badge.svg)](https://github.com/nRouterGateway/nrouter-sdk/actions/workflows/publish-pypi.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

SDK and code examples for the [nRouter](https://nrouter.ai) LLM gateway.

## All Ten SDKs Supported

All ten SDKs are officially maintained, tested against the identical gateway wire contract, and share the single coordinated release version **`3.1.2`** under [Rule #14](https://github.com/nRouterGateway/nrouter-sdk#the-one-rule-that-matters-here). Every package manifest, lockfile, documentation, and installation snippet is synchronized to `3.1.2`.

| SDK | Registry / Distribution | Registry URL | Package | Version |
|---|---|---|---|---|
| JavaScript / TypeScript | npm | [npmjs.com/package/@nrouter_ai/sdk](https://www.npmjs.com/package/@nrouter_ai/sdk) | `@nrouter_ai/sdk` | 3.1.2 |
| Python | PyPI | [pypi.org/project/nrouter-sdk](https://pypi.org/project/nrouter-sdk/) | `nrouter-sdk` | 3.1.2 |
| Java | Maven Central | [central.sonatype.com](https://central.sonatype.com/artifact/ai.nrouter/nrouter-sdk) | `ai.nrouter:nrouter-sdk` | 3.1.2 |
| Kotlin | Maven Central | [central.sonatype.com](https://central.sonatype.com/artifact/ai.nrouter/nrouter-sdk-kotlin) | `ai.nrouter:nrouter-sdk-kotlin` | 3.1.2 |
| Android | Maven Central | [central.sonatype.com](https://central.sonatype.com/artifact/ai.nrouter/nrouter-sdk-android) | `ai.nrouter:nrouter-sdk-android` | 3.1.2 |
| Go | Go Modules (`proxy.golang.org`) | [pkg.go.dev](https://pkg.go.dev/github.com/nRouterGateway/nrouter-sdk/sdks/go/v3) | `github.com/nRouterGateway/nrouter-sdk/sdks/go/v3` | 3.1.2 |
| Rust | crates.io | [crates.io/crates/nrouter](https://crates.io/crates/nrouter) | `nrouter` | 3.1.2 |
| Swift | Swift Package Manager | [github.com/nRouterGateway/nrouter-sdk](https://github.com/nRouterGateway/nrouter-sdk) | `nrouter-sdk` | 3.1.2 |
| Dart / Flutter | pub.dev | [pub.dev/packages/nrouter](https://pub.dev/packages/nrouter) | `nrouter` | 3.1.2 |
| R | R-universe / CRAN | [nroutergateway.r-universe.dev](https://nroutergateway.r-universe.dev/nrouter) | `nrouter` | 3.1.2 |

All ten SDKs are held to the same public wire contract. The conformance gate
accounts for all 150 route-ownership cells (15 routes × 10 SDKs): seven
first-party transports expose native helpers with the exact path and HTTP verb,
Android delegates the exact surface to Kotlin, and the JS/Python hybrid clients
explicitly partition native helpers from their bounded vendor-client
inheritance seam. Python's native route cells require both sync and async
implementations. For inherited routes, the source gate proves ownership and a
compiled resource—not the vendor package's internal HTTP implementation. The
complete local gate compiles and runs the package suites against their locked
dependencies.

The conformance gate derives and compares every manifest to the canonical
version in `spec/nrouter-sdk-spec.json`; release metadata cannot drift silently.


One API key for models across six provider clouds — Alibaba US, OpenAI, AWS Bedrock, Azure Foundry, Google Vertex AI and Anthropic. nRouter serves the OpenAI wire format and Anthropic's Messages API natively, plus embeddings, audio, images and video.

One key. One bill. The live multi-provider catalog. Guardrails, prompt templates, and cost
tracking built in. Browse the exact models available now at
[nrouter.ai/api/public/models](https://nrouter.ai/api/public/models).

### The model decides the route — a Claude id is not callable on every endpoint

The gateway resolves a provider endpoint **per wire**, and a provider that
serves no endpoint for a wire answers `404 model_unavailable_on_route`: the
model exists, just not on the route it was asked for. Anthropic serves
**`/v1/messages` only** — it has neither chat-completions nor Responses — so a
`claude-*` id posted to `/v1/chat/completions` fails for a customer holding a
valid key and a real model id.

| You are calling | Use a model from |
|---|---|
| `/v1/chat/completions`, `/v1/completions`, `/v1/responses` | OpenAI, Azure Foundry, Vertex AI or Alibaba (for example `gpt-5.4-mini`) |
| `/v1/messages`, `/v1/messages/count_tokens` | Anthropic (`claude-sonnet-4-5-20250929`) or any provider serving that wire |

The JS/TS SDK is the one exception: `client.nr.chat()` selects `/v1/messages`
itself for `claude-*` ids and translates the response back, so the examples
below pass a Claude id to it deliberately.

Every example here uses a model measured in the live catalogue on 2026-08-31.
Confirm against your own key before spending — the catalogue is per-org:

```bash
curl -s https://api.nrouter.ai/v1/models -H "Authorization: Bearer $NROUTER_API_KEY"
```

`gpt-5.4-mini` is a reasoning model: give it a real token budget (~1024), or a
small `max_tokens` is spent on hidden reasoning and the reply comes back empty.

`conformance/doc_wires.py` gates every snippet in this repository against that
table.

## Why Use the nRouter SDK?

Rather than juggling separate provider SDKs (OpenAI, Anthropic, Bedrock, Vertex AI, Azure Foundry), nRouter provides:

1. **One API Key Across 6 Provider Clouds**: Call OpenAI, Claude, Vertex, Bedrock, and Azure models with a single client and unified billing.
2. **Built-in Spend & Observability**: Every response captures exact latency, model ID, and request cost (`x-nr-request-cost`) with no extra telemetry instrumentation needed.
3. **Automated Guardrails & Compliance**: PII redaction, prompt injection protection, and keyword scanning configured once in the dashboard apply automatically.
4. **Smart Routing & Automatic Failover**: Route across provider clouds by real-time latency, price, or availability using router aliases.
5. **Universal Enterprise Features**: Unified conversation memory, Jinja2 prompt variable injection, and RFC 9110 retry-after exponential backoff across all 10 SDKs.

---

## Authentication, Environment & `.env` Setup

All nRouter SDKs automatically read your API key from the `NROUTER_API_KEY` environment variable.

### 1. Where to Get Your API Key
1. Sign in to your dashboard: [nrouter.ai/dashboard](https://nrouter.ai/dashboard).
2. Go to **API Keys / Virtual Keys**: [nrouter.ai/dashboard/keys](https://nrouter.ai/dashboard/keys).
3. Click **Create Key**. Virtual keys start with `sk-nrouter-`. Assign key budgets, rate limits, and guardrails directly in the dashboard.

### 2. Configure Local `.env`
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Edit `.env` and set your key:
```bash
NROUTER_API_KEY="sk-nrouter-your-api-key-here"
NROUTER_BASE_URL="https://api.nrouter.ai/v1"
```

### 3. How to Source `.env`
- **Shell (Bash / Zsh)**:
  ```bash
  export $(grep -v '^#' .env | xargs)
  ```
- **Node.js / TypeScript**:
  ```bash
  npm install dotenv
  ```
  ```typescript
  import "dotenv/config";
  import { nRouter } from "@nrouter_ai/sdk";
  const client = new nRouter(); // reads process.env.NROUTER_API_KEY
  ```
- **Python**:
  ```bash
  pip install python-dotenv
  ```
  ```python
  from dotenv import load_dotenv
  load_dotenv()
  from nroutersdk import nRouter
  client = nRouter() # reads os.environ["NROUTER_API_KEY"]
  ```
- **Go**:
  ```go
  import "github.com/joho/godotenv"
  _ = godotenv.Load()
  client, err := nrouter.NewFromEnv()
  ```

All API keys must start with the `sk-nrouter-` prefix. You can also pass the key explicitly in code via `apiKey` / `api_key` in any SDK constructor.

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
    model="gpt-5.4-mini",
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
    <version>3.1.2</version>
</dependency>
```
```java
import ai.nrouter.sdk.NRouter;
import com.openai.client.OpenAIClient;
import com.openai.models.chat.completions.*;

OpenAIClient client = NRouter.create(); // reads NROUTER_API_KEY
ChatCompletion res = client.chat().completions().create(
    ChatCompletionCreateParams.builder()
        .model("gpt-5.4-mini")
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
.package(url: "https://github.com/nRouterGateway/nrouter-sdk.git", from: "3.1.2")
```
```swift
import NRouter

let client = try NRouter() // reads NROUTER_API_KEY
let res = try await client.chatCompletions([
    "model": "gpt-5.4-mini",
    "messages": [["role": "user", "content": "Hello!"]]
])
print(res.meta.isPriced ? "Cost: $\(res.meta.cost!)" : "Cost: unpriced")
```

### Rust
```toml
# Cargo.toml
[dependencies]
nrouter = "3.1.2"
tokio = { version = "1", features = ["macros", "rt-multi-thread"] }
```
```rust
use nrouter::http::Client;
use serde_json::json;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let client = Client::from_env()?; // reads NROUTER_API_KEY
    let out = client.chat_completions(&json!({
        "model": "gpt-5.4-mini",
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
  nrouter: ^3.1.2
```
```dart
import 'package:nrouter/nrouter.dart';

final client = NRouter(apiKey: 'sk-nrouter-...');
final result = await client.chatCompletions({
  'model': 'gpt-5.4-mini',
  'messages': [{'role': 'user', 'content': 'Hello from Dart!'}],
});
print(result.body['choices']);
client.close();
```

### Kotlin
```kotlin
// build.gradle.kts
repositories { mavenCentral() }
dependencies {
    implementation("ai.nrouter:nrouter-sdk-kotlin:3.1.2")
}
```
```kotlin
import ai.nrouter.sdk.NRouter
import org.json.JSONObject

val client = NRouter() // reads NROUTER_API_KEY
val res = client.chatCompletions(
    JSONObject()
        .put("model", "gpt-5.4-mini")
        .put("messages", listOf(mapOf("role" to "user", "content" to "Hello from Kotlin!")))
)
println("Cost: ${res.meta.cost?.let { "$$it" } ?: "unpriced"}")
```

### Android
```kotlin
// app/build.gradle.kts
repositories { mavenCentral() }
dependencies {
    implementation("ai.nrouter:nrouter-sdk-android:3.1.2")
}
```

### SDK Ecosystem & Status

Ten branded packages, each pre-configured for nRouter. Every one validates the
`sk-nrouter-` prefix before any request and points at `https://api.nrouter.ai/v1`; all
but Dart also resolve `NROUTER_API_KEY` (Dart requires an explicit key — `dart:io` does
not exist in a Flutter web build, so an environment fallback would silently resolve to
nothing):

| Language | Install | Registry URL | Registry status | Package | Typed errors | `x-nr-*` metadata |
|----------|---------|--------------|---|---------|---|---|
| **Python** | `pip install nrouter-sdk` | [pypi.org/project/nrouter-sdk](https://pypi.org/project/nrouter-sdk/) | ✅ PUBLISHED `3.1.2` | [`sdks/python/`](sdks/python/) | ✅ typed wrappers | ✅ `client.last_response` |
| **TypeScript / JS** | `npm install @nrouter_ai/sdk` | [npmjs.com/package/@nrouter_ai/sdk](https://www.npmjs.com/package/@nrouter_ai/sdk) | ✅ PUBLISHED `3.1.2` | [`sdks/js/`](sdks/js/) | ✅ 11 codes | ✅ all `x-nr-*` headers |
| **Java** | Maven `ai.nrouter:nrouter-sdk:3.1.2` | [central.sonatype.com](https://central.sonatype.com/artifact/ai.nrouter/nrouter-sdk) | ✅ PUBLISHED `3.1.2` | [`sdks/java/`](sdks/java/) | ✅ 11 codes (native HTTP surface) | ✅ all `x-nr-*` headers (native HTTP surface) |
| **Kotlin** | Maven `ai.nrouter:nrouter-sdk-kotlin:3.1.2` | [central.sonatype.com](https://central.sonatype.com/artifact/ai.nrouter/nrouter-sdk-kotlin) | ✅ PUBLISHED `3.1.2` | [`sdks/kotlin/`](sdks/kotlin/) | ✅ 11 codes | ✅ all `x-nr-*` headers |
| **Android** | Maven `ai.nrouter:nrouter-sdk-android:3.1.2` | [central.sonatype.com](https://central.sonatype.com/artifact/ai.nrouter/nrouter-sdk-android) | 🧪 PUBLIC PREVIEW `3.1.2` | [`sdks/android/`](sdks/android/) | ✅ 11 codes | ✅ all `x-nr-*` headers |
| **Rust** | `cargo add nrouter@3.1.2` | [crates.io/crates/nrouter](https://crates.io/crates/nrouter) | 🧪 PUBLIC PREVIEW `3.1.2` | [`sdks/rust/`](sdks/rust/) | ✅ 11 codes | ✅ all `x-nr-*` headers |
| **Dart / Flutter** | `dart pub add nrouter` | [pub.dev/packages/nrouter](https://pub.dev/packages/nrouter) | 🧪 PUBLIC PREVIEW `3.1.2` | [`sdks/dart/`](sdks/dart/) | ✅ 11 codes | ✅ all `x-nr-*` headers |
| **Swift** | SwiftPM, this repo's URL | [github.com/nRouterGateway/nrouter-sdk](https://github.com/nRouterGateway/nrouter-sdk) | ✅ git tag `3.1.2` | [`sdks/swift/`](sdks/swift/) | ✅ 11 codes | ✅ all `x-nr-*` headers |
| **R** | `install.packages("nrouter", repos = c(nroutergateway = "https://nroutergateway.r-universe.dev", CRAN = "https://cloud.r-project.org"))` | [nroutergateway.r-universe.dev/nrouter](https://nroutergateway.r-universe.dev/nrouter) | 🧪 PUBLIC PREVIEW `3.1.2` | [`sdks/r/`](sdks/r/) | ✅ 11 classed conditions | ✅ all `x-nr-*` headers |
| **Go** | `go get github.com/nRouterGateway/nrouter-sdk/sdks/go/v3@v3.1.2` | [pkg.go.dev/github.com/nRouterGateway/nrouter-sdk/sdks/go/v3](https://pkg.go.dev/github.com/nRouterGateway/nrouter-sdk/sdks/go/v3) | ✅ git tag `sdks/go/v3.1.2` | [`sdks/go/`](sdks/go/) | ✅ 11 codes | ✅ all `x-nr-*` headers |

Verify any row rather than trusting it:

```bash
# Ask each registry what it SERVES, not whether a page exists.
curl -s https://pypi.org/pypi/nrouter-sdk/json | python3 -c 'import sys,json;print("pypi",json.load(sys.stdin)["info"]["version"])'
curl -s https://registry.npmjs.org/@nrouter_ai%2Fsdk | python3 -c 'import sys,json;print("npm",json.load(sys.stdin)["dist-tags"]["latest"])'

# Maven Central. Use repo1 metadata, NOT search.maven.org — its solr index
# returns zero hits for ai.nrouter while the artifacts are demonstrably there,
# so an "empty" search page is an index gap, never proof of an absent release.
for a in nrouter-sdk nrouter-sdk-kotlin nrouter-sdk-android; do
  echo -n "maven $a "
  curl -s "https://repo1.maven.org/maven2/ai/nrouter/$a/maven-metadata.xml" | grep -o '<release>[^<]*'
done

curl -s -H 'User-Agent: nrouter-check' https://crates.io/api/v1/crates/nrouter | python3 -c 'import sys,json;print("crates.io",json.load(sys.stdin)["crate"]["max_version"])'
curl -s https://pub.dev/api/packages/nrouter | python3 -c 'import sys,json;print("pub.dev",json.load(sys.stdin)["latest"]["version"])'

# Go has no registry: proxy.golang.org serves whatever a git tag points at, and
# it case-encodes the path (each uppercase letter becomes '!' + lowercase).
curl -s https://proxy.golang.org/github.com/n!router!a!i/nrouter-sdk/sdks/go/v3/@v/list
curl -s https://nroutergateway.r-universe.dev/src/contrib/PACKAGES | grep -A4 '^Package: nrouter$'
```

Java keeps its vendor-compatible OpenAI factory and adds a Java 11 native HTTP
surface for all 15 gateway operations, four incremental SSE wires, every
`x-nr-*` header and eleven typed gateway errors.
JavaScript/TypeScript and the seven first-party native transports expose the
same contract. Android delegates those guarantees to Kotlin; Python adds the
same nRouter typing and metadata capture around its vendor client.

**Every SDK is held to one contract.** `conformance/check_conformance.py` reads
[`spec/nrouter-sdk-spec.json`](spec/nrouter-sdk-spec.json) and fails if any SDK drifts on
the base URL, the environment variable, the key prefix, a response header, an error code,
one of the 150 route-ownership cells, or one of the four native streaming
helpers per first-party transport.
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
`osv-scanner` and `pip-audit`.

It also runs `scripts/sast.sh`, which is a **different** check and not a
substitute for either direction: `security-audit.sh` looks for known
vulnerabilities in third-party dependencies, `sast.sh` runs static analysis over
the code in this repository. It uses semgrep's `p/default` ruleset:

```bash
brew install semgrep                   # macOS
python3 -m pip install --user semgrep  # any platform
```

Without it the lane is reported `SKIPPED` and named, never passed, and
`scripts/sast.sh` run directly exits `78` with that install command rather than
a bare `command not found`. The three exit states are deliberately distinct —
`0` scanned and clean, `1` scanned and found something, `78` never ran — because
semgrep itself uses `0`/`1`, so absence must be neither or "not installed" reads
as "clean". Prove it bites before trusting a green run:

```bash
scripts/sast.sh --self-test
```

That plants a git-tracked file containing a command injection and fails unless
the scan reports it. Tracked is deliberate: semgrep scans git-tracked files
only, so an untracked probe is skipped and the scan still exits 0.

**This is a mirror, not parity.** It stands in for the GitHub CodeQL default
setup, which is dormant while Actions is unavailable. Measured over this tree,
`p/default` is comparable to CodeQL on **Python, TypeScript, JavaScript, Java
and Go**; it is **thin on Kotlin (18 rules) and Swift (2 rules)**, which nothing
local now replaces; **Rust** is thin in semgrep but genuinely covered by
`cargo clippy -D warnings` in the Rust lane. **Dart and R are scanned by
nothing** — CodeQL never covered them either, so that hole is pre-existing.
CodeQL's `actions` workflow analysis is **not** mirrored. `scripts/sast.sh`
carries the per-language rule counts and how to re-derive them.

Each language is an independent lane, so one absent toolchain no longer blocks
the rest. A lane whose prerequisites are missing is reported `SKIPPED`, named,
and counted separately — it is never a pass, and the summary says so in as many
words. A lane that FAILS exits the script non-zero. For a release, set
`NROUTER_REQUIRE_ALL=1`: a lane that did not run is then not evidence, and the
run reports `INCOMPLETE` and exits non-zero. `scripts/test-all.sh --self-test`
proves those three exit postures against the same engine the real run uses.

The opt-in live tests are intentionally excluded unless `NROUTER_LIVE=1` is
set, because they make billed inference calls.

Publishing is [`PUBLISHING.md`](PUBLISHING.md): bump the canonical version and
all manifests together, merge to `main`, publish the three supported registry
packages, verify every source preview, and create the source tags.

Swift and Go resolve git tags rather than registry uploads. SwiftPM reads
`Package.swift` from the repository ROOT. That is what
[`Package.swift`](Package.swift) here is for — this directory is the root of the
public `nrouter-sdk` repo, and the manifest uses `path:` to reach
`sdks/swift/`, so the Swift sources stay beside the other eight. Consumers use:

```swift
.package(url: "https://github.com/nRouterGateway/nrouter-sdk.git", from: "3.1.2")
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

### Runnable end-to-end example

[`sdks/js/demo/demo-e2e-sdk-example/`](sdks/js/demo/demo-e2e-sdk-example/) is a complete,
runnable npm consumer of the JS SDK: one real request that prints what it cost
and, if it is refused, why. It is the shortest demonstration of the two fields a
production integration has to branch on — `meta.costStatus`, because an unpriced
request reports no cost at all rather than a silent zero, and `err.authReason`,
because "your key is wrong" and "your key is fine but the account is on hold"
need different responses and neither is fixed by retrying. `npm start` sends a
real, billed request. It depends on `file:../..` rather than a published
range, so build `sdks/js` first; the example's own README carries the one-line
change to make once the matching version publishes.

### Voice: three of those endpoints, composed

There is no voice endpoint and no realtime session. A voice turn is a cascade —
`/v1/audio/transcriptions` → a chat wire → `/v1/audio/speech` — so it produces
three request ids and three spend rows, any of which can come back unpriced.
[`sdks/js/demo/voice-agent/`](sdks/js/demo/voice-agent/) is a
runnable one that prints the per-call cost and refuses to report a session total
as complete when a leg was not priced. The JS semantics are in
[`sdks/js/docs/audio.md`](sdks/js/docs/audio.md).

### Three more runnable agents, one per money shape

Each is one file, prices and logs every call it makes, and ships a mock-gateway
suite that runs with no key and no network — so the accounting is checkable
without spending anything.

| Example | Wires | The money question it answers |
|---|---|---|
| [`sdks/js/demo/chat-agent/`](sdks/js/demo/chat-agent/) | the four text wires, buffered and streamed | why a streamed call reports `unpriced` permanently, and why a cache hit is still billed — semantics in [`sdks/js/docs/cost.md`](sdks/js/docs/cost.md) |
| [`sdks/js/demo/image-agent/`](sdks/js/demo/image-agent/) | `/v1/images/generations` | which of two billing units the model measured, and why no header carries the quantity that produced the price — semantics in [`sdks/js/docs/images.md`](sdks/js/docs/images.md) |
| [`sdks/js/demo/video-agent/`](sdks/js/demo/video-agent/) | the three video routes | why the create is the only call that bills, and why a *free* call is not an *unpriced* one — semantics in [`sdks/js/docs/video.md`](sdks/js/docs/video.md) |

### Routing strategies are selected by the model value

Routing strategy is a gateway concern, so there is no separate per-language
strategy API to drift. Put a Smart Router alias in `model` to activate its
configured strategy and fallback chain; put a concrete model id there to pin
the call to that model. Every runnable hello-world example accepts
`NROUTER_MODEL` so the same example demonstrates both modes without inventing
client-only routing behavior.

```bash
NROUTER_MODEL=my-production-router ./run-your-example   # alias: strategy + fallback
NROUTER_MODEL=gpt-5.4-mini ./run-your-example  # concrete: pinned
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
| **Python (branded)** | `pip install nrouter-sdk` | [`sdks/python/`](sdks/python/) · [`sdks/python/demo/`](sdks/python/demo/), [`notebooks/quickstart.ipynb`](notebooks/quickstart.ipynb) |
| **TypeScript / JS (branded)** | `npm install @nrouter_ai/sdk` | [`sdks/js/`](sdks/js/) · [`sdks/js/demo/quickstart.ts`](sdks/js/demo/quickstart.ts), [`sdks/js/demo/quickstart.js`](sdks/js/demo/quickstart.js) |
| **Java (branded)** | `ai.nrouter:nrouter-sdk` | [`sdks/java/`](sdks/java/) · [`sdks/java/demo/quickstart.java`](sdks/java/demo/quickstart.java) |
| **Kotlin (branded)** | Maven `ai.nrouter:nrouter-sdk-kotlin:3.1.2` | [`sdks/kotlin/`](sdks/kotlin/) · [`sdks/kotlin/demo/quickstart.kt`](sdks/kotlin/demo/quickstart.kt) |
| **Android (branded)** | Maven `ai.nrouter:nrouter-sdk-android:3.1.2` | [`sdks/android/`](sdks/android/) · [`sdks/android/demo/`](sdks/android/demo/) |
| **Rust (branded)** | `cargo add nrouter@3.1.2` | [`sdks/rust/`](sdks/rust/) · [`sdks/rust/demo/quickstart.rs`](sdks/rust/demo/quickstart.rs) |
| **Dart / Flutter (branded)** | `dart pub add nrouter` | [`sdks/dart/`](sdks/dart/) · [`sdks/dart/demo/quickstart.dart`](sdks/dart/demo/quickstart.dart) |
| **R (branded)** | `install.packages("nrouter", repos = c(nroutergateway = "https://nroutergateway.r-universe.dev", CRAN = "https://cloud.r-project.org"))` | [`sdks/r/`](sdks/r/) · [`sdks/r/demo/quickstart.R`](sdks/r/demo/quickstart.R) |
| **Node.js / TypeScript (plain openai)** | `npm install openai` | [`sdks/js/demo/node.ts`](sdks/js/demo/node.ts) |
| **Go** | `go get github.com/nRouterGateway/nrouter-sdk/sdks/go/v3@v3.1.2`, or plain `openai-go` | [`sdks/go/demo/quickstart.go`](sdks/go/demo/quickstart.go) |
| **Java (plain openai-java)** | `com.openai:openai-java` | [`sdks/java/demo/quickstart.java`](sdks/java/demo/quickstart.java) |

Every language under `sdks/*/demo/` holds standalone, runnable starter scripts and framework integrations.

### AI Frameworks

| Framework | Install | Example | What Changes |
|-----------|---------|---------|-------------|
| **LangChain** | `pip install langchain-openai` | [`sdks/python/demo/frameworks/langchain.py`](sdks/python/demo/frameworks/langchain.py) | `base_url` + `api_key` on `ChatOpenAI` |
| **LlamaIndex** | `pip install llama-index-llms-openai` | [`sdks/python/demo/frameworks/llamaindex.py`](sdks/python/demo/frameworks/llamaindex.py) | `api_base` + `api_key` on `OpenAI` |
| **Vercel AI SDK** | `npm install ai @ai-sdk/openai` | [`sdks/js/demo/vercel_ai.ts`](sdks/js/demo/vercel_ai.ts) | `baseURL` on `createOpenAI()` |
| **CrewAI** | `pip install crewai` | [`sdks/python/demo/frameworks/crewai.py`](sdks/python/demo/frameworks/crewai.py) | `OPENAI_API_BASE` env var |
| **AutoGen** | `pip install autogen-agentchat` | [`sdks/python/demo/frameworks/autogen.py`](sdks/python/demo/frameworks/autogen.py) | `base_url` in config_list |

**Every framework** that supports OpenAI-compatible endpoints works with nRouter. Set `base_url` to `https://api.nrouter.ai/v1` and `api_key` to your `NROUTER_API_KEY`. That's it.

---

## Response Headers

The gateway's public `x-nr-*` response headers, and what each one means. Most
are conditional; `x-nr-request-id` and `x-nr-latency-ms` are the two present on
every response. The
authoritative set is
[`spec/gateway-response-headers.json`](spec/gateway-response-headers.json),
derived from the gateway and held against all ten SDKs by
`conformance/check_conformance.py` — this table describes the headers, and is
not itself the register of which ones exist.

| Header | Type | Description |
|--------|------|-------------|
| `x-nr-request-id` | string | Unique request ID (always present) |
| `x-nr-latency-ms` | integer | Milliseconds from edge arrival until the response headers are ready; time-to-headers, not time to the final streamed event (always present) |
| `x-nr-trace-id` | string | OpenTelemetry trace ID for this request; absent when no valid trace exists |
| `x-nr-request-cost` | float | Exact cost in USD; absent when the model is unpriced |
| `x-nr-cost-status` | string | `exact` or `unpriced` when cost metadata is available |
| `x-nr-model` | string | Model that served the request |
| `x-nr-input-tokens` | integer | Input token count |
| `x-nr-output-tokens` | integer | Output token count |
| `x-nr-total-tokens` | integer | Total token count, including cache tokens |
| `x-nr-cache-read-tokens` | integer | Cache-read tokens; emitted only when nonzero |
| `x-nr-cache-write-tokens` | integer | Cache-write tokens; emitted only when nonzero |
| `x-nr-limit-source` | string | `key`, `plan`, `team`, `user`, `budget`, `plan_window_h8`, `plan_window_day`, `plan_window_week`, `capacity`, `plan_allowance_exhausted`, or `plan_required` on 429 and 402 responses |
| `x-nr-budget-warning` | string | A soft budget you configured was crossed by this request, which still served; `<scope> soft_budget <spend>/<ceiling>`, e.g. `org soft_budget 80.00/100.00` |
| `x-nr-guardrails` | string | Pre-call guardrail posture — `none`, `monitor`, `redacted`, `pass`, `partial`, `blocked` or `unavailable`; absent means the response makes no guardrail claim, never `none`, which is an explicit token |
| `x-nr-auth-reason` | string | On a 401, the gateway's stable reason for refusing the key |
| `x-nr-response-cache` | string | `hit` or `miss`; absent when the response cache did not participate |
| `x-nr-response-cache-age` | integer | Age of a cache `hit` in seconds |
| `x-nr-funding-source` | string | Which balance paid for this request: the plan's usage allowance or credits (`allowance` or `credits`) |
| `x-nr-allowance-reset` | integer | Seconds until the tightest usage-allowance window resets |

Python SDK captures these automatically in `client.last_response`. Other languages read them from HTTP response headers.

---

## Error Codes

The gateway classifies refusals into typed error codes:

| Code | HTTP | Exception Class | Description |
|------|------|-----------------|-------------|
| `invalid_request` | 400 | `nRouterRequestError` | Invalid JSON or request shape |
| `guardrail_blocked` | 400 | `nRouterGuardrailBlockedError` | A guardrail denied the request (pre-call) or withheld the response (post-call) |
| `invalid_api_key` | 401 | `nRouterAuthenticationError` | Virtual-key authentication refused; see `x-nr-auth-reason` |
| `insufficient_credits` | 402 | `nRouterCreditError` | Reserve failed; nothing was spent |
| `model_not_found` | 404 | `nRouterNotFoundError` | Model alias absent or not visible to this key |
| `rate_limit_exceeded` | 429 | `nRouterRateLimitError` | RPM limit exceeded; see `x-nr-limit-source` |
| `tpm_limit_exceeded` | 429 | `nRouterRateLimitError` | TPM limit exceeded; see `x-nr-limit-source` |
| `credit_check_failed` | 503 | `nRouterServiceError` | Credit system unavailable |
| `service_unavailable` | 503 | `nRouterServiceError` | A required gateway dependency is unavailable |
| `plan_allowance_exhausted` | 402 | `nRouterCreditError` | The plan's usage allowance for this billing period is used up. It resets at the next billing period (see `x-nr-allowance-reset`). |
| `plan_required` | 402 | `nRouterCreditError` | Only plan subscribers can use `nrouter/auto`, or the plan's usage allowance is paused pending payment. Named models are paid from credits. |

---

## Structure

This is the standalone public `nRouterGateway/nrouter-sdk` repository:

```
nrouter-sdk/
├── README.md                        ← You are here (single reference for all)
├── LANGUAGES.md                     ← every-language guide (any OpenAI-format client)
├── spec/nrouter-sdk-spec.json       ← Source of truth (headers, errors, endpoints, Rule #14)
├── sdks/
│   ├── python/                      ← Branded SDK → pip install nrouter-sdk (demo/ included)
│   ├── js/                          ← Branded SDK → npm install @nrouter_ai/sdk (demo/ included)
│   ├── java/                        ← Branded SDK → Maven ai.nrouter:nrouter-sdk (demo/ included)
│   ├── kotlin/                      ← Branded SDK → Maven ai.nrouter:nrouter-sdk-kotlin (demo/ included)
│   ├── android/                     ← Branded SDK → Maven ai.nrouter:nrouter-sdk-android (demo/ included)
│   ├── swift/                       ← SwiftPM package from root git tag (demo/ included)
│   ├── rust/                        ← Branded SDK → crates.io nrouter (demo/ included)
│   ├── dart/                        ← Branded SDK → pub.dev nrouter (demo/ included)
│   ├── go/                          ← Branded SDK → tagged Go module (demo/ included)
│   └── r/                           ← Branded SDK → R-universe public preview (demo/ included)
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
| [CHANGELOG.md](CHANGELOG.md) | Coordinated release history for the shared SDK version train. |
| [PUBLISHING.md](PUBLISHING.md) | How a release actually ships, and which credential each registry needs. |

npm builds **1.1.1 and later** carry [provenance attestations](https://docs.npmjs.com/generating-provenance-statements)
tying the tarball to the exact commit and workflow that produced it — verify
with `npm audit signatures`. 1.0.0 and 1.1.0 were published by hand and have
none; provenance cannot be added to a version after the fact. See
[SECURITY.md](SECURITY.md#release-integrity).
