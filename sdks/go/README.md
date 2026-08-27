# nRouter SDK for Go

One API key for models across six provider clouds — Alibaba US, OpenAI, AWS
Bedrock, Azure Foundry, Google Vertex AI and Anthropic. The gateway serves the
OpenAI wire format and Anthropic's Messages API natively, plus embeddings,
audio, images and video.

> **Not published yet.** `go get` will fail until the module is tagged — see
> [PUBLISHING.md](PUBLISHING.md). Until then, vendor it or use a `replace`
> directive against a local checkout. The status table in the repo
> [README](../../README.md) is the one to trust.

```bash
go get github.com/nRouterAI/nrouter-sdk/sdks/go
```

## Use

```go
package main

import (
	"context"
	"fmt"
	"log"

	nrouter "github.com/nRouterAI/nrouter-sdk/sdks/go"
)

func main() {
	client, err := nrouter.NewFromEnv() // reads NROUTER_API_KEY
	if err != nil {
		log.Fatal(err)
	}

	res, err := client.ChatCompletions(context.Background(), map[string]any{
		"model": "claude-sonnet-4-5",
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

You can, and [`examples/go.go`](../../examples/go.go) shows exactly that — it
keeps working and stays supported. The vendor client owns its own transport and
discards the raw response, so the `x-nr-*` metadata is out of reach without
`.WithRawResponse()` plumbing at every call site. This SDK exists for the
metadata: cost, tokens, cache outcome and limit source come back beside every
response, and the gateway's nine error codes arrive as typed values.

## Response metadata

`Response.Meta` carries all thirteen `x-nr-*` headers. Every numeric field is a
pointer, deliberately:

| Field | Header | Nil means |
|---|---|---|
| `RequestID` | `x-nr-request-id` | — (always present) |
| `Cost` | `x-nr-request-cost` | **unpriced, not free** |
| `CostStatus` | `x-nr-cost-status` | `exact` or `unpriced` |
| `Model` | `x-nr-model` | the model that served it |
| `InputTokens` / `OutputTokens` / `TotalTokens` | `x-nr-*-tokens` | not measured |
| `CacheReadTokens` / `CacheWriteTokens` | `x-nr-cache-*-tokens` | zero, so omitted |
| `LimitSource` | `x-nr-limit-source` | the gateway did not say which limit |
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

## Binary and streaming endpoints

The JSON helpers refuse a non-JSON 2xx rather than handing back an empty body
for a request you were billed for. Use `Bytes` for `/audio/speech`,
`/videos/{id}/content`, and any request with `"stream": true`:

```go
audio, err := client.Bytes(ctx, "POST", "/audio/speech", map[string]any{
	"model": "gpt-4o-mini-tts", "voice": "alloy", "input": "Hello",
})
```

## Test

```bash
cd sdks/go
gofmt -l .            # expect no output
go vet ./...
go test ./... -race
python3 ../../conformance/check_conformance.py
```
