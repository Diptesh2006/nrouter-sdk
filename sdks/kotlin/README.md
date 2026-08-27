# nRouter SDK for Kotlin

One API key for models across six provider clouds. The gateway speaks the OpenAI
wire format, so the bodies are the shapes you already know.

```kotlin
dependencies {
    implementation("ai.nrouter:nrouter-sdk-kotlin:2.1.0")
}
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

`chatCompletions`, `embeddings`, `messages` (Anthropic wire format), `responses`,
`models`, plus `post(path, body)` and `get(path)` for anything else under `/v1`.

## Build and test

```bash
./gradlew build      # compile + tests
./gradlew test
```

Publishing: [PUBLISHING.md](PUBLISHING.md).
