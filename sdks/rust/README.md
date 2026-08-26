# nRouter SDK for Rust

One API key for models across six provider clouds.

```toml
[dependencies]
nrouter = "2.1"
tokio = { version = "1", features = ["macros", "rt-multi-thread"] }
```

## Two entry points, on purpose

**`nrouter::client()`** returns an [`async-openai`] client pointed at the
gateway, so every OpenAI-shaped call you already write keeps working:

```rust
use async_openai::types::{ChatCompletionRequestUserMessageArgs, CreateChatCompletionRequestArgs};

let client = nrouter::client()?;               // reads NROUTER_API_KEY
let request = CreateChatCompletionRequestArgs::default()
    .model("claude-sonnet-4-5")
    .messages(vec![ChatCompletionRequestUserMessageArgs::default()
        .content("Hello!").build()?.into()])
    .build()?;
let response = client.chat().create(request).await?;
```

**`nrouter::http::Client`** is a native client that hands back the `x-nr-*`
metadata. `async-openai` discards the raw response, so per-request cost, token
counts and cache outcome are unreachable through it — that is the whole reason
this second path exists:

```rust
use serde_json::json;

let client = nrouter::http::Client::from_env()?;
let out = client.chat_completions(&json!({
    "model": "claude-sonnet-4-5",
    "messages": [{"role": "user", "content": "Hello!"}]
})).await?;

// Branch on the status, never on `cost` being None-ish. An unpriced model
// reports cost == None, and rendering that as 0.0 reports a free request —
// which no enabled model is.
match out.meta.cost {
    Some(usd) => println!("cost ${usd}"),
    None => println!("unpriced ({:?})", out.meta.cost_status),
}
```

`ResponseMeta` carries all thirteen `x-nr-*` headers: `request_id`, `cost`,
`cost_status`, `model`, `input_tokens`, `output_tokens`, `total_tokens`,
`cache_read_tokens`, `cache_write_tokens`, `limit_source`, `auth_reason`,
`response_cache`, `response_cache_age`.

## Errors

`NRouterError` variants are chosen from the gateway's stable `code` — not the
HTTP status, which cannot separate the two 400s or the two 429s.

```rust
match client.chat_completions(&body).await {
    Err(NRouterError::GuardrailBlocked(b)) => { /* change the request */ }
    Err(NRouterError::Credit(b))           => { /* top up */ }
    Err(e) if e.is_retryable()             => { /* rate limit, service, transport */ }
    Err(e) => return Err(e.into()),
    Ok(out) => { /* ... */ }
}
```

| Variant | Code(s) | HTTP |
|---|---|---|
| `Request` | `invalid_request` | 400 |
| `GuardrailBlocked` | `guardrail_blocked` | 400 |
| `Authentication` | `invalid_api_key` | 401 |
| `Credit` | `insufficient_credits` | 402 |
| `NotFound` | `model_not_found` | 404 |
| `RateLimit` | `rate_limit_exceeded`, `tpm_limit_exceeded` | 429 |
| `Service` | `credit_check_failed`, `service_unavailable` | 503 |
| `Other` | anything newer than this SDK | — |
| `Transport` | never reached the gateway | — |

`is_retryable()` is true only for `RateLimit`, `Service` and `Transport`. Every
other variant names something permanent, where a retry burns quota and cannot
change the answer.

`ErrorBody::limit_source` names WHICH ceiling refused a 429. It is `None` when
the gateway could not attribute the refusal, and this SDK does not guess —
sending a customer to raise the wrong limit is worse than saying nothing.

## Configuration

```rust
let client = nrouter::http::Client::new("sk-nrouter-...")?
    .with_base_url("https://api-stage.nrouter.ai/v1")
    .with_http_client(my_reqwest_client);      // proxy, timeouts, pooling
```

## Endpoints

`chat_completions`, `embeddings`, `messages` (Anthropic wire format),
`responses`, `models`, plus `post(path, body)` and `get(path)` for anything else
under `/v1`.

## Build and test

```bash
cargo test                                   # unit + integration + doc tests
cargo clippy --all-targets -- -D warnings
```

MSRV 1.75. Publishing: [PUBLISHING.md](PUBLISHING.md).

[`async-openai`]: https://crates.io/crates/async-openai
