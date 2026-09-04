# nRouter SDK for Rust

One API key for models across six provider clouds.

## Source installation

Rust is a source preview and declares `publish = false`. From an application
beside a checkout of this repository, use a path dependency:

```toml
[dependencies]
nrouter = { path = "../nrouter-sdk/sdks/rust" }
tokio = { version = "1", features = ["macros", "rt-multi-thread"] }
```

## Authentication & Setup

Set your API key in the environment:

```bash
export NROUTER_API_KEY="sk-nrouter-your-api-key-here"
```

## Two entry points, on purpose

**`nrouter::client()`** returns an [`async-openai`] client pointed at the
gateway, so every OpenAI-shaped call you already write keeps working:

```rust
use async_openai::types::chat::{
    ChatCompletionRequestUserMessageArgs, CreateChatCompletionRequestArgs,
};

let client = nrouter::client()?;               // reads NROUTER_API_KEY
let request = CreateChatCompletionRequestArgs::default()
    .model("gpt-5.4-mini")
    .messages(vec![ChatCompletionRequestUserMessageArgs::default()
        .content("Hello!").build()?.into()])
    .build()?;
let response = client.chat().create(request).await?;
```

**`nrouter::http::Client`** is a native client that hands back the `x-nr-*`
metadata. `async-openai` discards the raw response, so per-request cost, token
counts and cache outcome are unreachable through it — that is the whole reason
this second path exists:

Custom gateway URLs must use HTTPS. Plain HTTP is accepted only for
`localhost` or a loopback IP so local development remains possible without
ever sending an API key unencrypted to a remote host.

```rust
use serde_json::json;

let client = nrouter::http::Client::from_env()?;
let out = client.chat_completions(&json!({
    "model": "gpt-5.4-mini",
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

`ResponseMeta` carries every `x-nr-*` header the gateway emits, named in
snake_case — `x-nr-request-cost` becomes `cost` and
`x-nr-cache-read-tokens` becomes `cache_read_tokens`. The authoritative set is
[`spec/gateway-response-headers.json`](../../spec/gateway-response-headers.json),
derived from the gateway and held against this SDK by
`conformance/check_conformance.py`. This page does not restate it: a copied
list of a set that grows is a list that goes stale, and under the word "every"
it becomes a false claim of exhaustiveness rather than a stale number.

## Streaming

The native client incrementally parses SSE on all four text wires. `delta` is
portable across OpenAI and Anthropic frames; `raw` preserves the complete
provider-native JSON. Dropping the stream drops the response body, cancelling
unread generation:

```rust
let mut stream = client.messages_stream(&serde_json::json!({
    "model": "claude-haiku-4-5-20251001",
    "max_tokens": 256,
    "messages": [{"role": "user", "content": "Hello!"}]
})).await?;

while let Some(chunk) = stream.next().await? {
    print!("{}", chunk.delta);
}
println!("\nrequest {:?}", stream.meta.request_id);
```

`chat_completions_stream`, `completions_stream`, `messages_stream`, and
`responses_stream` clone the request body and force `stream: true`. An in-band
output-guardrail event returns `NRouterError::GuardrailBlocked`; a bare EOF is
a retryable transport failure, never a clean completion.

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

All 15 gateway operations have named buffered helpers: `chat_completions`, `completions`,
`embeddings`, `images_generations`, `messages`, `count_tokens`, `responses`,
`models`, `model`, `create_video`, `retrieve_video`, `download_video_content`,
`audio_speech`, `audio_transcriptions`, and `audio_translations`. `post`, `get`,
`bytes`, `multipart`, and `stream` remain available as escape hatches.

**Not JSON:** `audio_transcriptions` and `audio_translations` send multipart/form-data
(the gateway requires a binary `file` part, so the JSON helpers cannot reach them);
`audio_speech()` and `download_video_content()` return raw bytes plus metadata;
`bytes(method, path, body)` remains available for other non-JSON responses. The
JSON helpers refuse a non-JSON response rather than handing back an empty body
for a request you were billed for.

## Build and test

```bash
cargo test                                   # unit + integration + doc tests
cargo clippy --all-targets -- -D warnings
```

MSRV 1.88 — the effective floor of the dependency graph (`icu_*` via reqwest's
TLS stack declare 1.88). Derive it rather than trusting this line:

```bash
cargo metadata --format-version 1 --locked \
  | python3 -c "import json,sys;print(max((p['rust_version'] for p in json.load(sys.stdin)['packages'] if p.get('rust_version')), key=lambda v:[int(x) for x in v.split('.')]))"
``` Publishing: [PUBLISHING.md](PUBLISHING.md).

[`async-openai`]: https://crates.io/crates/async-openai

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
