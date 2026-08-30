# nRouter SDK for Swift

One API key for models across six provider clouds. Zero external dependencies —
URLSession and async/await only.

```swift
// Package.swift
dependencies: [
    .package(url: "https://github.com/nRouterAI/nrouter-sdk.git", from: "2.1.0")
]
```

Or in Xcode: **File → Add Package Dependencies** and paste the URL.

| Platform | Minimum |
|---|---|
| macOS | 12 |
| iOS / tvOS | 15 |
| watchOS | 8 |
| visionOS | 1 |

## Use it

```swift
import NRouter

let client = try NRouter()                     // reads NROUTER_API_KEY

let result = try await client.chatCompletions([
    "model": "claude-sonnet-4-5",
    "messages": [["role": "user", "content": "Hello!"]],
])
```

On iOS there is no environment to read, so pass the key: `try NRouter(apiKey:)`.
See the key-handling note below before you hardcode one.

## What a call cost

```swift
let meta = result.meta
print("request \(meta.requestID ?? "-") | model \(meta.model ?? "-")")

// Branch on the status, never on `cost` being nil-ish. An unpriced model
// reports cost == nil, and rendering that as $0 reports a free request —
// which no enabled model is.
print(meta.isPriced ? "cost $\(meta.cost!)" : "cost unpriced")
```

`NRouterResponseMeta` carries all thirteen `x-nr-*` headers: `requestID`,
`cost`, `costStatus`, `model`, `inputTokens`, `outputTokens`, `totalTokens`,
`cacheReadTokens`, `cacheWriteTokens`, `limitSource`, `authReason`,
`responseCache`, `responseCacheAge`.

`meta` is `Sendable`, so cost and token counts cross actor boundaries freely.
`Response.body` is `[String: Any]` and deliberately is **not** `Sendable` —
`@unchecked` there would silence a real question rather than answer it. Decode
the body into your own `Sendable` type to send that across actors.

## Errors

Every refusal is a case of `NRouterError`, chosen from the gateway's stable
`code` — not the HTTP status, which cannot separate the two 400s or the two
429s.

```swift
do {
    _ = try await client.chatCompletions(body)
} catch let error as NRouterError {
    switch error {
    case .guardrailBlocked:  // a rule denied it; change the request
    case .credit:            // out of credits; top up
    case .rateLimit(let b):
        // b.limitSource names WHICH ceiling refused. nil when the gateway
        // could not attribute it — this SDK does not guess, because sending a
        // customer to raise the wrong limit is worse than saying nothing.
        if error.isRetryable { await retryLater() }
    default: throw error
    }
}
```

| Case | Code(s) | HTTP |
|---|---|---|
| `.request` | `invalid_request` | 400 |
| `.guardrailBlocked` | `guardrail_blocked` | 400 |
| `.authentication` | `invalid_api_key` | 401 |
| `.credit` | `insufficient_credits` | 402 |
| `.notFound` | `model_not_found` | 404 |
| `.rateLimit` | `rate_limit_exceeded`, `tpm_limit_exceeded` | 429 |
| `.service` | `credit_check_failed`, `service_unavailable` | 503 |
| `.other` | anything newer than this SDK | — |
| `.transport` | never reached the gateway | — |

`isRetryable` is true only for `.rateLimit`, `.service` and `.transport`.

## Do not ship a key in the app bundle

Anything compiled into an iOS/macOS app — `Info.plist`, a constant, an asset —
is readable by anyone who downloads it. For a shipped app, mint a short-lived
key on your backend and pass it to `NRouter(apiKey:)`.

## Configuration

```swift
try NRouter(
    apiKey: myKey,
    baseURL: "https://api-stage.nrouter.ai/v1",
    session: URLSession(configuration: myConfiguration)   // proxy, timeouts
)
```

## Endpoints

`chatCompletions`, `embeddings`, `messages` (Anthropic wire format), `responses`,
`models`, plus `post(_:_:)` and `get(_:)` for anything else under `/v1`.

**Not JSON:** `audioTranscriptions` and `audioTranslations` send multipart/form-data
(the gateway requires a binary `file` part, so the JSON helpers cannot reach them);
`bytes(_:_:)` returns raw `Data` for `/v1/audio/speech`, video content, and anything
else that does not answer in JSON. The JSON helpers refuse a non-JSON response
rather than handing back an empty body for a request you were billed for.

## Build and test

```bash
swift build
swift test
swift build -Xswiftc -strict-concurrency=complete   # Swift 6 clean
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
