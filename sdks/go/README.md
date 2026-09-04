# nRouter SDK for Go

[![Go Reference](https://pkg.go.dev/badge/github.com/nRouterAI/nrouter-sdk/sdks/go/v2.svg)](https://pkg.go.dev/github.com/nRouterAI/nrouter-sdk/sdks/go/v2)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/nRouterAI/nrouter-sdk/blob/main/LICENSE)

One API key for models across six provider clouds — Alibaba US, OpenAI, AWS
Bedrock, Azure Foundry, Google Vertex AI and Anthropic. The gateway serves the
OpenAI wire format and Anthropic's Messages API natively, plus embeddings,
audio, images and video.

**Documentation & Package Reference:** [pkg.go.dev/github.com/nRouterAI/nrouter-sdk/sdks/go/v2](https://pkg.go.dev/github.com/nRouterAI/nrouter-sdk/sdks/go/v2)

## Installation

```bash
go get github.com/nRouterAI/nrouter-sdk/sdks/go/v2@v2.2.1
```

## Authentication & Setup

The SDK automatically reads your API key from the `NROUTER_API_KEY` environment variable:

```bash
export NROUTER_API_KEY="sk-nrouter-your-api-key-here"
```

## Usage

```go
package main

import (
	"context"
	"fmt"
	"log"

	nrouter "github.com/nRouterAI/nrouter-sdk/sdks/go/v2"
)

func main() {
	client, err := nrouter.NewFromEnv() // reads NROUTER_API_KEY
	if err != nil {
		log.Fatal(err)
	}

	res, err := client.ChatCompletions(context.Background(), map[string]any{
		"model": "gpt-5.4-mini",
		"messages": []any{
			map[string]any{"role": "user", "content": "Hello!"},
		},
	})
	if err != nil {
		log.Fatal(err)
	}

	fmt.Println(res.Body["choices"])

	if res.Meta.Cost != nil {
		fmt.Printf("cost $%v (%s)\n", *res.Meta.Cost, res.Meta.CostStatus)
	} else {
		// Unpriced is NOT free — it is unknown. Never render it as 0.
		fmt.Printf("unpriced (%s)\n", res.Meta.CostStatus)
	}
}
```

## Why not just point the OpenAI Go SDK at the gateway

You can, and [`examples/go/quickstart.go`](../../examples/go/quickstart.go) shows exactly that — it
keeps working and stays supported. The vendor client owns its own transport and
discards the raw response, so the `x-nr-*` metadata is out of reach without
`.WithRawResponse()` plumbing at every call site. This SDK exists for the
metadata: cost, tokens, cache outcome and limit source come back beside every
response, and the gateway's nine error codes arrive as typed values.

## Response metadata

`Response.Meta` exposes the gateway's `x-nr-*` headers as typed fields. The
authoritative header set is
[`spec/gateway-response-headers.json`](../../spec/gateway-response-headers.json),
derived from the gateway and held against this SDK by
`conformance/check_conformance.py`; the table below documents what a nil MEANS
per field, which is the part the spec cannot carry. Every numeric
field is a pointer, deliberately:

| Field | Header | Nil means |
|---|---|---|
| `RequestID` | `x-nr-request-id` | — (always present) |
| `Cost` | `x-nr-request-cost` | **unpriced, not free** |
| `CostStatus` | `x-nr-cost-status` | `exact` or `unpriced` |
| `Model` | `x-nr-model` | the model that served it |
| `InputTokens` / `OutputTokens` / `TotalTokens` | `x-nr-*-tokens` | not measured |
| `CacheReadTokens` / `CacheWriteTokens` | `x-nr-cache-*-tokens` | zero, so omitted |
| `LimitSource` | `x-nr-limit-source` | the gateway did not say which limit |
| `BudgetWarning` | `x-nr-budget-warning` | no soft budget was crossed (`<scope> soft_budget <spend>/<ceiling>` when one was) |
| `Guardrails` | `x-nr-guardrails` | this response makes no guardrail claim — never "none", which is an explicit token |
| `AuthReason` | `x-nr-auth-reason` | — |
| `ResponseCache` / `ResponseCacheAge` | `x-nr-response-cache*` | the cache did not participate |

`Meta.IsPriced()` is the safe test before billing anything against `Cost`.

## Errors

Every failure is a `*nrouter.Error`. Match the condition, not a string:

```go
res, err := client.ChatCompletions(ctx, body)
switch {
case errors.Is(err, nrouter.ErrRateLimit):
    // e.RetryAfter and e.LimitSource say how long and which limit
case errors.Is(err, nrouter.ErrCredit):
    // top up the balance
case errors.Is(err, nrouter.ErrBudgetExceeded):
    // raise the budget — the OPPOSITE fix; both are 402
case err != nil:
    var e *nrouter.Error
    errors.As(err, &e)
    if e.IsRetryable() {
        // rate limit, service, or transport — nothing else
    }
}
```

`ErrBudgetExceeded` is separate from `ErrCredit` on purpose. Both arrive as 402
and their remedies are opposites; telling a customer whose budget is exhausted
to add money is a wrong answer delivered confidently.

## Streaming

The four text wires have incremental SSE helpers. `Delta` is portable across
OpenAI-shaped chunks and native Anthropic Messages events; `Raw` preserves the
complete provider-native frame for usage and finish metadata. Always inspect
`Err` after iteration, because an output guardrail arrives as an in-band error
after the HTTP status has already been sent:

```go
stream, err := client.MessagesStream(ctx, map[string]any{
	"model": "claude-sonnet-4-5",
	"max_tokens": 256,
	"messages": []any{
		map[string]any{"role": "user", "content": "Hello!"},
	},
})
if err != nil {
	log.Fatal(err)
}
defer stream.Close()

for stream.Next() {
	fmt.Print(stream.Chunk().Delta)
}
if err := stream.Err(); err != nil {
	log.Fatal(err)
}
fmt.Printf("\nrequest %s\n", stream.Meta.RequestID)
```

`ChatCompletionsStream`, `CompletionsStream`, `MessagesStream`, and
`ResponsesStream` copy the request body and force `stream: true`; they never
mutate the caller's map. `Stream` remains the generic escape hatch.

## Binary endpoints

The JSON helpers refuse a non-JSON 2xx rather than handing back an empty body
for a request you were billed for. Use `Bytes` for `/audio/speech` and
`/videos/{id}/content`:

```go
audio, err := client.AudioSpeech(ctx, map[string]any{
	"model": "gpt-4o-mini-tts", "voice": "alloy", "input": "Hello",
})
```

## Endpoints

All 15 gateway operations have named buffered helpers: `ChatCompletions`, `Completions`,
`Embeddings`, `ImagesGenerations`, `Messages`, `CountTokens`, `Responses`,
`Models`, `Model`, `CreateVideo`, `RetrieveVideo`, `DownloadVideoContent`,
`AudioSpeech`, `AudioTranscriptions`, and `AudioTranslations`. `Post`, `Get`,
`Bytes`, `Multipart`, and `Stream` remain available as escape hatches.

## Test

```bash
cd sdks/go
gofmt -l .            # expect no output
go vet ./...
go test ./... -race
python3 ../../conformance/check_conformance.py
```

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
- [Go quickstart](https://nrouter.ai/docs/sdks/go) and the
  [API reference](https://nrouter.ai/docs/api-reference).
