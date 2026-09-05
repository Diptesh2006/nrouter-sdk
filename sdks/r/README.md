# nRouter SDK for R

[![R-universe version](https://nrouterai.r-universe.dev/nrouter/badges/version)](https://nrouterai.r-universe.dev/nrouter)
[![R-universe checks](https://nrouterai.r-universe.dev/nrouter/badges/checks)](https://nrouterai.r-universe.dev/nrouter)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/nRouterAI/nrouter-sdk/blob/main/LICENSE)

One API key for models across six provider clouds. There is no official OpenAI
SDK for R, so this package calls the gateway's HTTP API directly via `httr`.

**Registry & Package URL:** [https://nrouterai.r-universe.dev/nrouter](https://nrouterai.r-universe.dev/nrouter)  
**Registry Status:** 🧪 Public Preview on R-universe (Package `nrouter` v3.0.0)

```r
# Public preview from R-universe.
install.packages(
  "nrouter",
  repos = c(
    nrouterai = "https://nrouterai.r-universe.dev",
    CRAN = "https://cloud.r-project.org"
  )
)
```

For a development install directly from the monorepo:

```r
remotes::install_github("nRouterAI/nrouter-sdk", subdir = "sdks/r")
```

## Authentication & Setup

Set your API key in your environment or `.Renviron`:

```r
Sys.setenv(NROUTER_API_KEY = "sk-nrouter-your-api-key-here")
```

## Use it

```r
library(nrouter)

client <- nrouter_client()                  # reads NROUTER_API_KEY

result <- nrouter_chat_completions(client, list(
  model = "gpt-5.4-mini",
  messages = list(list(role = "user", content = "Hello!"))
))

result$body$choices[[1]]$message$content
```

## Streaming

The four text-generation wires invoke a callback as each SSE event arrives.
The parser accepts OpenAI `[DONE]` and native Anthropic `message_stop`
terminators, and raises the same classed conditions for in-band gateway errors.

```r
nrouter_messages_stream(client, list(
  model = "claude-haiku-4-5-20251001",
  max_tokens = 64,
  messages = list(list(role = "user", content = "Hello!"))
), function(chunk) {
  cat(chunk$delta)
})
```

The other helpers are `nrouter_chat_completions_stream()`,
`nrouter_completions_stream()`, and `nrouter_responses_stream()`;
`nrouter_stream()` is the generic escape hatch. Return `FALSE` from the callback
to cancel early. Opening response headers carry the request ID, while final
cost normally remains unknown because headers are committed before generation
finishes; unknown stays `NULL`, never zero.

One-call form, when you do not need the metadata:

```r
nrouter_chat(list(list(role = "user", content = "Hello!")))
```

## What a call cost

```r
print(result$meta)
#> <nrouter_meta>
#>   request_id: nrouter-a1b2c3d4
#>   model:      gpt-5.4-mini
#>   cost:       $0.00042

# Branch on the status, never on `cost` being falsy. An unpriced model reports
# cost = NULL, and rendering that as 0 reports a free request — which no
# enabled model is.
if (nrouter_is_priced(result$meta)) {
  sprintf("$%f", result$meta$cost)
} else {
  "unpriced"
}
```

`nrouter_meta` carries every `x-nr-*` header the gateway emits, named in
snake_case — `x-nr-request-cost` becomes `cost` and
`x-nr-cache-read-tokens` becomes `cache_read_tokens`. Any element is `NULL`
when the gateway did not send that header. The authoritative set is
[`spec/gateway-response-headers.json`](../../spec/gateway-response-headers.json),
derived from the gateway and held against this SDK by
`conformance/check_conformance.py`. This page does not restate it: a copied
list of a set that grows is a list that goes stale, and under the word "every"
it becomes a false claim of exhaustiveness rather than a stale number.

## Errors are classed conditions

Every refusal is raised as an R condition whose class vector runs
specific-to-general, so you can catch a family or one kind:

```r
tryCatch(
  nrouter_chat_completions(client, body),

  # One kind.
  nrouter_guardrail_blocked_error = function(e) message("blocked: ", conditionMessage(e)),
  nrouter_credit_error            = function(e) message("out of credits"),

  nrouter_rate_limit_error = function(e) {
    # e$limit_source names WHICH ceiling refused. NULL when the gateway could
    # not attribute it — this SDK does not guess, because sending a customer to
    # raise the wrong limit is worse than saying nothing.
    if (nrouter_is_retryable(e)) retry_later()
  },

  # Or the whole family.
  nrouter_error = function(e) message("nRouter refused: ", conditionMessage(e))
)
```

| Class | Code(s) | HTTP |
|---|---|---|
| `nrouter_request_error` | `invalid_request` | 400 |
| `nrouter_guardrail_blocked_error` | `guardrail_blocked` | 400 |
| `nrouter_authentication_error` | `invalid_api_key` | 401 |
| `nrouter_credit_error` | `insufficient_credits` | 402 |
| `nrouter_not_found_error` | `model_not_found` | 404 |
| `nrouter_rate_limit_error` | `rate_limit_exceeded`, `tpm_limit_exceeded` | 429 |
| `nrouter_service_error` | `credit_check_failed`, `service_unavailable` | 503 |
| `nrouter_other_error` | anything newer than this SDK | — |
| `nrouter_transport_error` | never reached the gateway | — |

Every one also carries `nrouter_error`, `error` and `condition`.
`nrouter_is_retryable()` is true only for rate-limit, service and transport
failures.

## Configuration

```r
nrouter_client(
  api_key  = my_key,                              # else NROUTER_API_KEY
  base_url = "https://api-stage.nrouter.ai/v1"    # stage
)
```

## Endpoints

All 15 gateway operations have named helpers: `nrouter_chat_completions()`,
`nrouter_completions()`, `nrouter_embeddings()`,
`nrouter_images_generations()`, `nrouter_messages()`, `nrouter_count_tokens()`,
`nrouter_responses()`, `nrouter_models()`, `nrouter_model()`,
`nrouter_create_video()`, `nrouter_retrieve_video()`,
`nrouter_download_video_content()`, `nrouter_audio_speech()`,
`nrouter_audio_transcriptions()`, and `nrouter_audio_translations()`.
`nrouter_request()`, `nrouter_bytes()`, and `nrouter_multipart()` remain
available as escape hatches.

**Not JSON:** `nrouter_audio_transcriptions()` and `nrouter_audio_translations()`
send multipart/form-data (the gateway requires a binary `file` part, so the JSON
helpers cannot reach them). `nrouter_audio_speech()` and
`nrouter_download_video_content()` return raw bytes plus metadata;
`nrouter_bytes()` remains available for other non-JSON responses. The JSON
helpers refuse a non-JSON response rather than handing back an empty body for a
request you were billed for.

## Build and test

```bash
cd sdks
R CMD build r && R CMD check nrouter_3.0.0.tar.gz --as-cran   # Status: OK
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
