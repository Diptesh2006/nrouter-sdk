# nRouter SDK for R

One API key for models across six provider clouds. There is no official OpenAI
SDK for R, so this package calls the gateway's HTTP API directly via `httr`.

```r
# From R-universe (binaries for macOS and Windows)
install.packages("nrouter", repos = "https://nrouterai.r-universe.dev")

# Or from source
remotes::install_github("nRouterAI/nrouter-sdk", subdir = "nrouter-sdk/sdks/r")
```

## Use it

```r
library(nrouter)

client <- nrouter_client()                  # reads NROUTER_API_KEY

result <- nrouter_chat_completions(client, list(
  model = "claude-sonnet-4-5",
  messages = list(list(role = "user", content = "Hello!"))
))

result$body$choices[[1]]$message$content
```

One-call form, when you do not need the metadata:

```r
nrouter_chat(list(list(role = "user", content = "Hello!")))
```

## What a call cost

```r
print(result$meta)
#> <nrouter_meta>
#>   request_id: nrouter-a1b2c3d4
#>   model:      claude-sonnet-4-5
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

`nrouter_meta` carries all thirteen `x-nr-*` headers: `request_id`, `cost`,
`cost_status`, `model`, `input_tokens`, `output_tokens`, `total_tokens`,
`cache_read_tokens`, `cache_write_tokens`, `limit_source`, `auth_reason`,
`response_cache`, `response_cache_age`. Each is `NULL` when the gateway did not
send it.

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

`nrouter_chat_completions()`, `nrouter_embeddings()`, `nrouter_messages()`
(Anthropic wire format), `nrouter_responses()`, `nrouter_models()`, plus
`nrouter_request()` for anything else under `/v1`.

## Build and test

```bash
cd sdks
R CMD build r && R CMD check nrouter_2.1.0.tar.gz --as-cran   # Status: OK
```

Publishing: [PUBLISHING.md](PUBLISHING.md).
