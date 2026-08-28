# nRouter SDK for Dart & Flutter

One API key for models across six provider clouds. One dependency (`http`), so
the same code runs on Flutter mobile, desktop, **web**, and the plain Dart VM.

```yaml
dependencies:
  nrouter: ^2.1.0
```

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

`chatCompletions`, `embeddings`, `messages` (Anthropic wire format), `responses`,
`models`, plus `post(path, body)` and `get(path)` for anything else under `/v1`.

**Not JSON:** `audioTranscriptions` and `audioTranslations` send multipart/form-data
(the gateway requires a binary `file` part, so the JSON helpers cannot reach them);
`bytes(path, body)` returns raw bytes for `/v1/audio/speech`, video content, and
anything else that does not answer in JSON. The JSON helpers refuse a non-JSON
response rather than handing back an empty body for a request you were billed for.

## Build and test

```bash
dart pub get
dart analyze
dart test
```

Publishing: [PUBLISHING.md](PUBLISHING.md).

## How guardrails, budgets and routing work

They are enforced at the **gateway**, not in this package — so they apply to
every request on the key, they behave the same from every nRouter SDK, and this
client cannot turn them off:

- [Guardrails](https://nrouter.ai/docs/guides/guardrails) — PII redaction and
  injection protection, pre-call and post-call.
- [Budget controls](https://nrouter.ai/docs/guides/budget-controls) — spend
  limits per key, team and organization.
- [Routing and fallbacks](https://nrouter.ai/docs/guides/router-settings) —
  failover chains across providers.
- [Observability](https://nrouter.ai/docs/guides/observability) — per-request
  cost and usage.
- [API reference](https://nrouter.ai/docs/api-reference) — the wire
  contract every SDK here implements.
