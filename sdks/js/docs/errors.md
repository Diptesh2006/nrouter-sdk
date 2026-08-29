# Errors

```ts
import {
  nRouterError,
  nRouterGuardrailBlockedError,
  nRouterRateLimitError,
  isRetryable,
} from '@nrouter_ai/sdk';

try {
  await client.nr.chat({ model, prompt });
} catch (err) {
  if (err instanceof nRouterGuardrailBlockedError) return refuse(err.message);
  if (isRetryable(err)) return backoffAndRetry(err.retryAfter);
  throw err;
}
```

Every failure this SDK raises extends `nRouterError`. Catch the base class to
catch all of them; catch a subclass, or switch on `err.kind`, to act on one.

## The trap: classifying on `code` alone loses conditions

The gateway's **main error path sends no `code`**. It emits:

```json
{ "error": { "type": "gateway_error", "message": "…" } }
```

`type` there is a family name, not one of the stable error codes. So an error
handler written as `switch (body.error.code)` matches nothing on the ordinary
path — and `guardrail_blocked`, which shares HTTP 400 with every other bad
request, becomes **unreachable**. That exact defect shipped in five SDKs at once.

The correct precedence, which this SDK implements for you:

```
1. the stable code, WHEN one was sent
2. the HTTP status
3. the message text, only to split conditions that share a status
```

An unknown code is preserved on `err.code` and never reclassified into a
neighbouring class — guessing a stable code onto an unrecognised condition is how
a caller ends up handling the wrong failure forever.

## The classes

| Kind | Status | Class | Means |
|---|---|---|---|
| `request` | 400 | `nRouterRequestError` | invalid JSON or request shape |
| `guardrail_blocked` | 400 | `nRouterGuardrailBlockedError` | a guardrail denied it |
| `authentication` | 401 | `nRouterAuthenticationError` | the key was refused; see `err.authReason` |
| `credit` | 402 | `nRouterCreditError` | reserve failed; **nothing was spent** |
| `budget_exceeded` | 402 | `nRouterBudgetExceededError` | a configured budget ceiling, not an empty balance |
| `not_found` | 404 | `nRouterNotFoundError` | the model alias is absent, or not visible to this key |
| `rate_limit` | 429 | `nRouterRateLimitError` | see `err.limitSource` and `err.retryAfter` |
| `service` | 502 / 503 / 504 | `nRouterServiceError` | a gateway dependency or the upstream is unavailable |
| `transport` | — | `nRouterTransportError` | the request never got a usable answer |
| `configuration` | — | `nRouterConfigurationError` | a caller-side mistake; permanent |
| `other` | any | `nRouterError` | a condition this SDK version does not name |

Three splits are made from the message text because the status alone cannot make
them, and each one matters:

- **402** — a budget refusal and an empty balance are different problems with
  different remedies. One is a ceiling you set; the other is money.
- **404** — scoped to models. A missing video job or an unknown server is also a
  404, and calling those "model not found" is a confidently wrong answer.
- **502** — an ordinary upstream blip is transient and retryable; an upstream
  response that was too large to process is not, because the same request
  produces the same oversized response forever. That one stays the base
  `nRouterError` and `isRetryable` returns false for it.

## What is retryable

```ts
isRetryable(err);  // rate_limit | service | transport, and never an abort
```

`configuration` is deliberately **not** retryable: it is a caller-side mistake,
and a generic `if (isRetryable(e)) retry` loop must not spin on a condition no
retry improves. This is why a rejected option throws a configuration error rather
than something transient-looking.

An aborted request is never retryable, however it was aborted.

## Fields worth logging

| Field | Use |
|---|---|
| `err.requestId` | joins the failure to a spend row or a log line. Log it on every failure. |
| `err.status` | `null` means the request never reached the gateway |
| `err.code` | `null` on the main error path; that is ordinary, not an anomaly |
| `err.limitSource` | which limit measured a 429; `null` means it did not say |
| `err.authReason` | the stable reason a key was refused on a 401 |
| `err.retryAfter` | whole seconds, parsed from both RFC 9110 forms |

## Two things the SDK will not do

**It never serializes `cause`.** A fetch failure can carry the originating
request, whose headers hold your API key.

**It redacts keys from messages.** An error message is assembled from a body this
SDK does not control, and a key printed once into a log aggregator is a key that
must be rotated.

Do not add your own `JSON.stringify(err)` around a raw cause; that is the path
that defeats both.

## A non-JSON 2xx is a billed response

An unparseable success body is not an empty result. The provider generated it and
billed for it. Handle a parse failure as a delivered-and-paid-for response you
could not read, and use `res.meta.requestId` to find out what it was.
