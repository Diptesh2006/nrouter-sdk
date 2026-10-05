//go:build ignore

// TypeSafe Jev System One decision example.
//
// Usage: NROUTER_API_KEY=sk-nrouter-... go run sdks/go/demo/jev_system_one.go
package main

import (
	"context"
	"fmt"
	"log"

	"github.com/nRouterGateway/nrouter-sdk/sdks/go/v3"
)

func main() {
	client, err := nrouter.NewFromEnv()
	if err != nil {
		log.Fatal(err)
	}

	response, err := client.ChatCompletions(context.Background(), map[string]any{
		"model": "typesafe/jev",
		"messages": []any{
			map[string]any{"role": "system", "content": "Classify the incident. Return JSON only: {\\\"priority\\\":\\\"P0|P1|P2|P3\\\",\\\"queue\\\":string,\\\"summary\\\":string}."},
			map[string]any{"role": "user", "content": "Production payment requests return HTTP 500 in two regions."},
		},
		"temperature": 0,
		"max_tokens": 128,
	})
	if err != nil {
		log.Fatal(err)
	}

	content := ""
	if choices, ok := response.Body["choices"].([]any); ok && len(choices) > 0 {
		if choice, ok := choices[0].(map[string]any); ok {
			if message, ok := choice["message"].(map[string]any); ok {
				content, _ = message["content"].(string)
			}
		}
	}
	fmt.Println("Decision:", content)
	fmt.Println("Request ID:", response.Meta.RequestID)
	fmt.Println("Served model:", response.Meta.Model)
	if response.Meta.Cost != nil {
		fmt.Printf("Exact cost: $%.6f\n", *response.Meta.Cost)
	} else {
		fmt.Println("Cost status:", response.Meta.CostStatus)
	}
}
