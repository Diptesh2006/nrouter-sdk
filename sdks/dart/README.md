# nRouter SDK for Dart & Flutter

[![pub.dev](https://img.shields.io/pub/v/nrouter?logo=dart&label=nrouter)](https://pub.dev/packages/nrouter)

One API key for models across six provider clouds. One dependency (`http`), so
the same code runs on Flutter mobile, desktop, **web**, and the plain Dart VM.

## Installation

```yaml
dependencies:
  nrouter: ^2.1.1
```

Or install via CLI:
```bash
dart pub add nrouter
# or for Flutter:
flutter pub add nrouter
```

## Authentication & Setup

Pass your API key to the `NRouter` constructor:

```dart
final client = NRouter(apiKey: 'sk-nrouter-your-api-key-here');
```

> **Why explicit apiKey is required:** `Platform.environment` requires `dart:io`, which does not exist in Flutter web builds (and is empty on mobile). For Flutter apps, mint a short-lived key on your backend and pass it to the constructor. In plain Dart VM CLI tools, you can pass `Platform.environment['NROUTER_API_KEY']!`.

## Use it

```dart
import 'package:nrouter/nrouter.dart';

final client = NRouter(apiKey: myKey);

final result = await client.chatCompletions({
  'model': 'claude-sonnet-4-5',
  'messages': [{'role': 'user', 'content': 'Hello!'}],
});

print(result.body['choices']);
client.close();
```

## Streaming

The four text-generation wires expose cold, cancellable SSE streams. The SDK
sets `stream: true`, accepts OpenAI `[DONE]` and native Anthropic
`message_stop` terminators, and turns in-band gateway errors into the same
typed exceptions as buffered calls.

```dart
await for (final chunk in client.messagesStream({
  'model': 'claude-haiku-4-5-20251001',
  'max_tokens': 64,
  'messages': [{'role': 'user', 'content': 'Hello!'}],
})) {
  print(chunk.delta);
}
```

Available helpers are `chatCompletionsStream`, `completionsStream`,
`messagesStream`, and `responsesStream`; `stream(path, body)` is the generic
escape hatch. Cancelling the subscription stops consuming the underlying HTTP
response.

Streaming metadata is captured from the opening response headers. The final
request cost is normally unknown there because the headers are sent before
generation completes; `cost` therefore remains `null`, never a misleading
zero.

## Why there is no environment fallback

The server-side nRouter SDKs read `NROUTER_API_KEY`. This one deliberately does
not: `Platform.environment` requires `dart:io`, which **does not exist in a
Flutter web build**, and on mobile it is empty anyway. A fallback that quietly
resolves to nothing is worse than no fallback, so `apiKey` is required.

## Do not ship a key in the app

Anything compiled into a Flutter bundle is readable by anyone who downloads it —
and on web it is served in plain text. **A shipped key is a published key**, and
an nRouter key spends real credits. Mint a short-lived key on your backend and
pass it here.

## What a call cost

```dart
final meta = result.meta;
print('request ${meta.requestId} | model ${meta.model}');

// Branch on the status, never on `cost` being null-ish. An unpriced model
// reports cost == null, and rendering that as $0 reports a free request —
// which no enabled model is.
print(meta.isPriced ? 'cost \$${meta.cost}' : 'cost unpriced');
```

`NRouterResponseMeta` carries all thirteen `x-nr-*` headers: `requestId`,
`cost`, `costStatus`, `model`, `inputTokens`, `outputTokens`, `totalTokens`,
`cacheReadTokens`, `cacheWriteTokens`, `limitSource`, `authReason`,
`responseCache`, `responseCacheAge`.

## Errors

Every refusal is a subclass of the sealed `NRouterError`, chosen from the
gateway's stable `code` — not the HTTP status, which cannot separate the two
400s or the two 429s. Because it is sealed, a `switch` over it is exhaustive and
the analyzer tells you when a new case appears.

```dart
try {
  await client.chatCompletions(body);
} on NRouterGuardrailBlockedError {
  // a rule denied it; changing the request is the fix
} on NRouterCreditError {
  // out of credits; topping up is the fix
} on NRouterRateLimitError catch (e) {
  // e.body?.limitSource names WHICH ceiling. null when the gateway could not
  // attribute the refusal — this SDK does not guess, because sending a
  // customer to raise the wrong limit is worse than saying nothing.
  if (e.isRetryable) await retryLater();
}
```

| Type | Code(s) | HTTP |
|---|---|---|
| `NRouterRequestError` | `invalid_request` | 400 |
| `NRouterGuardrailBlockedError` | `guardrail_blocked` | 400 |
| `NRouterAuthenticationError` | `invalid_api_key` | 401 |
| `NRouterCreditError` | `insufficient_credits` | 402 |
| `NRouterNotFoundError` | `model_not_found` | 404 |
| `NRouterRateLimitError` | `rate_limit_exceeded`, `tpm_limit_exceeded` | 429 |
| `NRouterServiceError` | `credit_check_failed`, `service_unavailable` | 503 |
| `NRouterOtherError` | anything newer than this SDK | — |
| `NRouterTransportError` | never reached the gateway | — |

`isRetryable` is true only for rate-limit, service and transport failures.

## Configuration

```dart
NRouter(
  apiKey: myKey,
  baseUrl: 'https://api-stage.nrouter.ai/v1',
  httpClient: myClient,        // your own http.Client — proxy, retries, mocks
);
```

Pass your own `http.Client` and this SDK will not close it; the one it creates
itself is released by `close()`.

## Endpoints

All 15 gateway operations have named helpers: `chatCompletions`, `completions`,
`embeddings`, `imagesGenerations`, `messages`, `countTokens`, `responses`,
`models`, `model`, `createVideo`, `retrieveVideo`, `downloadVideoContent`,
`audioSpeech`, `audioTranscriptions`, and `audioTranslations`. `post`, `get`,
`bytes`, and `multipart` remain available as escape hatches.

**Not JSON:** `audioTranscriptions` and `audioTranslations` send multipart/form-data
(the gateway requires a binary `file` part, so the JSON helpers cannot reach them);
`audioSpeech()` and `downloadVideoContent()` return raw bytes plus metadata;
`bytes(path, body)` remains available for other non-JSON responses. The JSON
helpers refuse a non-JSON response rather than handing back an empty body for a
request you were billed for.

## Build and test

```bash
dart pub get
dart analyze
dart test
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
