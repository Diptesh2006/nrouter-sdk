# nRouter SDK for Kotlin

One API key for models across six provider clouds. The gateway speaks the OpenAI
wire format, so the bodies are the shapes you already know.

## Source installation

Kotlin is a source preview, not a Maven Central release. From a checkout of
this repository, publish the verified artifact only to your local Maven cache:

```bash
cd sdks/kotlin
./gradlew clean check publishToMavenLocal
```

```kotlin
repositories { mavenLocal() }
dependencies {
    implementation("ai.nrouter:nrouter-sdk-kotlin:2.2.1")
}
```

## Authentication & Setup

The SDK automatically reads your API key from the `NROUTER_API_KEY` environment variable:

```bash
export NROUTER_API_KEY="sk-nrouter-your-api-key-here"
```

Building an Android app? Use [`nrouter-sdk-android`](../android) instead — it
depends on this artifact and fixes the one thing that does not carry over
(`System.getenv` returns null on Android).

## Use it

```kotlin
import ai.nrouter.sdk.NRouter
import org.json.JSONObject

val client = NRouter()                       // reads NROUTER_API_KEY

val result = client.chatCompletions(
    JSONObject()
        .put("model", "claude-sonnet-4-5")
        .put("messages", listOf(mapOf("role" to "user", "content" to "Hello!")))
)

println(result.body.getJSONArray("choices"))
```

Calls are `suspend` and hop to `Dispatchers.IO` themselves, so calling one from
a UI coroutine will not block the main thread.

## Streaming

The four text wires expose cold, cancellable `Flow`s. Each item carries a
portable `delta`, the untouched provider-native `raw` frame, and the response
metadata. Cancelling collection cancels the underlying OkHttp call immediately:

```kotlin
client.messagesStream(
    JSONObject()
        .put("model", "claude-haiku-4-5-20251001")
        .put("max_tokens", 256)
        .put("messages", listOf(mapOf("role" to "user", "content" to "Hello!")))
).collect { chunk ->
    print(chunk.delta)
}
```

`chatCompletionsStream`, `completionsStream`, `messagesStream`, and
`responsesStream` copy the supplied `JSONObject` and force `stream: true`.
An in-band output-guardrail event terminates collection with
`NRouterError.GuardrailBlocked`; it never looks like a clean truncated answer.

## What a call cost

Every response carries the gateway's `x-nr-*` metadata:

```kotlin
val meta = result.meta
println("request ${meta.requestId} | model ${meta.model}")
println("tokens  ${meta.inputTokens} in / ${meta.outputTokens} out")

// Branch on the status, never on `cost` being null-ish. An unpriced model
// reports cost == null, and rendering that as $0 reports a free request —
// which no enabled model is.
if (meta.isPriced) println("cost $${meta.cost}") else println("cost unpriced")
```

| Property | Header | Meaning |
|---|---|---|
| `requestId` | `x-nr-request-id` | Always present; the id for a support ticket |
| `cost` | `x-nr-request-cost` | Exact USD; **null** when unpriced, never `0` |
| `costStatus` | `x-nr-cost-status` | `exact` or `unpriced` |
| `model` | `x-nr-model` | Model that served the request |
| `inputTokens` / `outputTokens` / `totalTokens` | `x-nr-*-tokens` | Token counts |
| `cacheReadTokens` / `cacheWriteTokens` | `x-nr-cache-*-tokens` | Provider cache tokens |
| `limitSource` | `x-nr-limit-source` | On a 429, which ceiling refused |
| `authReason` | `x-nr-auth-reason` | On a 401, the gateway's stable reason |
| `responseCache` / `responseCacheAge` | `x-nr-response-cache*` | `hit`/`miss` and age in seconds |

## Errors

Every refusal is a typed subclass of `NRouterError`, chosen from the gateway's
stable `code` — not the HTTP status, which cannot separate the two 400s or the
two 429s.

```kotlin
try {
    client.chatCompletions(body)
} catch (e: NRouterError.GuardrailBlocked) {
    // a rule denied it — changing the request is the fix
} catch (e: NRouterError.Credit) {
    // out of credits — topping up is the fix
} catch (e: NRouterError.RateLimit) {
    // e.body?.limitSource names WHICH ceiling. It is null when the gateway
    // could not attribute the refusal, and this SDK does not guess: sending a
    // customer to raise the wrong limit is worse than saying nothing.
    if (e.isRetryable) retryLater()
}
```

| Class | Code(s) | HTTP |
|---|---|---|
| `NRouterError.Request` | `invalid_request` | 400 |
| `NRouterError.GuardrailBlocked` | `guardrail_blocked` | 400 |
| `NRouterError.Authentication` | `invalid_api_key` | 401 |
| `NRouterError.Credit` | `insufficient_credits` | 402 |
| `NRouterError.NotFound` | `model_not_found` | 404 |
| `NRouterError.RateLimit` | `rate_limit_exceeded`, `tpm_limit_exceeded` | 429 |
| `NRouterError.Service` | `credit_check_failed`, `service_unavailable` | 503 |
| `NRouterError.Other` | anything newer than this SDK | — |
| `NRouterError.Transport` | never reached the gateway | — |

`isRetryable` is true only for `RateLimit`, `Service` and `Transport`. Every
other case names something permanent, where a retry burns quota and cannot
change the answer.

## Configuration

```kotlin
NRouter(
    apiKey = myKey,                                  // else NROUTER_API_KEY
    baseURL = "https://api-stage.nrouter.ai/v1",     // stage
    http = OkHttpClient.Builder()                    // your own proxy/timeouts
        .callTimeout(Duration.ofSeconds(60))
        .build(),
)
```

## Endpoints

All 15 gateway operations have named buffered helpers: `chatCompletions`, `completions`,
`embeddings`, `imagesGenerations`, `messages`, `countTokens`, `responses`,
`models`, `model`, `createVideo`, `retrieveVideo`, `downloadVideoContent`,
`audioSpeech`, `audioTranscriptions`, and `audioTranslations`. `post`, `get`,
`bytes`, `multipart`, and `stream` remain available as escape hatches.

**Not JSON:** `audioTranscriptions` and `audioTranslations` send multipart/form-data
(the gateway requires a binary `file` part, so the JSON helpers cannot reach them);
`audioSpeech()` and `downloadVideoContent()` return raw bytes plus metadata;
`bytes(path, body)` remains available for other non-JSON responses. The JSON
helpers refuse a non-JSON response rather than handing back an empty body for a
request you were billed for.

## Build and test

```bash
./gradlew build      # compile + tests
./gradlew test
```

Publishing: [PUBLISHING.md](PUBLISHING.md).

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
- [API reference](https://nrouter.ai/docs/api-reference) — the wire
  contract every SDK here implements.
