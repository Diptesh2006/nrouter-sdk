package main

import (
	"context"
	"errors"
	"fmt"
	"log"
	"os"

	nrouter "github.com/nRouterAI/nrouter-sdk/sdks/go"
)

func main() {
	opts := []nrouter.Option{}
	if baseURL := os.Getenv("NROUTER_BASE_URL"); baseURL != "" {
		opts = append(opts, nrouter.WithBaseURL(baseURL))
	}
	client, err := nrouter.NewFromEnv(opts...)
	if err != nil {
		log.Fatal(err)
	}

	stream, err := client.MessagesStream(context.Background(), map[string]any{
		"model":      "claude-haiku-4-5-20251001",
		"max_tokens": 64,
		"messages": []any{
			map[string]any{"role": "user", "content": "Explain one useful Go concurrency rule."},
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
		if errors.Is(err, nrouter.ErrGuardrailBlocked) {
			log.Fatal("the output was withheld by a guardrail")
		}
		log.Fatal(err)
	}
	fmt.Printf("\nrequest: %s\n", stream.Meta.RequestID)
}
