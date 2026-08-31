// nRouter — Go
// OpenAI Go SDK + guardrails (automatic) + cost tracking via headers.
//
// go get github.com/openai/openai-go

package main

import (
	"context"
	"fmt"
	"os"

	"github.com/openai/openai-go"
	"github.com/openai/openai-go/option"
)

func main() {
	// All requests go through nRouter:
	//   Your code → api.nrouter.ai → Guardrails → Prompt Templates → Model → Response
	client := openai.NewClient(
		option.WithAPIKey(os.Getenv("NROUTER_API_KEY")),
		option.WithBaseURL("https://api.nrouter.ai/v1"),
	)

	// Chat — cache, guardrails, and rate limits auto-apply from org config.
	response, err := client.Chat.Completions.New(context.Background(),
		openai.ChatCompletionNewParams{
			Model: "anthropic/claude-sonnet-4-5-20250929",
			Messages: []openai.ChatCompletionMessageParamUnion{
				openai.UserMessage("Hello!"),
			},
		},
	)
	if err != nil {
		// If guardrail blocks: err contains "guardrail_blocked"
		// If insufficient credits: err contains "insufficient_credits"
		fmt.Printf("Error: %v\n", err)
		return
	}
	fmt.Println(response.Choices[0].Message.Content)

	// Guardrails are assigned per key, team or org in the dashboard and apply
	// automatically — the narrowest assignment wins. There is no per-request
	// override to send in the body.

	// Per-request prompt templates:
	// The Go SDK does not support extra body fields natively — use cURL or
	// a raw HTTP POST with the following in the JSON body:
	//   "nrouter_prompt_template_id": "your-summarizer-id"
	//   "nrouter_prompt_variables": {"language": "Spanish", "max_length": "100"}

	// Disable cache for a single request:
	// Pass "nrouter_cache": false in the JSON body via raw HTTP POST.
	// Cache is enabled by default. Omit the field to use org default.

	// Response headers contain:
	//   x-nr-request-id: nrouter-a1b2c3d4e5f67890
	//   x-nr-request-cost: 0.00347
	//   x-nr-cost-status: exact
	//   x-nr-model: anthropic/claude-sonnet-4-5-20250929
	//   x-nr-total-tokens: 60
}
