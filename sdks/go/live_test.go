package nrouter

import (
	"context"
	"os"
	"strings"
	"testing"
	"time"
)

// TestLiveClaude is opt-in because it spends real credits. It is the release
// smoke that mock servers cannot replace: the published request shape, native
// Anthropic stream, response headers and local/stage gateway must agree.
func TestLiveClaude(t *testing.T) {
	if os.Getenv("NROUTER_LIVE") != "1" {
		t.Skip("set NROUTER_LIVE=1 to run the billed gateway acceptance")
	}
	baseURL := os.Getenv("NROUTER_BASE_URL")
	if baseURL == "" {
		baseURL = DefaultBaseURL
	}
	client, err := NewFromEnv(WithBaseURL(baseURL))
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()
	body := map[string]any{
		"model":      "claude-haiku-4-5-20251001",
		"max_tokens": 2,
		"messages": []any{
			map[string]any{"role": "user", "content": "Reply OK"},
		},
	}
	stream, err := client.MessagesStream(ctx, body)
	if err != nil {
		t.Fatal(err)
	}
	defer stream.Close()
	var text strings.Builder
	for stream.Next() {
		text.WriteString(stream.Chunk().Delta)
	}
	if err := stream.Err(); err != nil {
		t.Fatal(err)
	}
	if text.Len() == 0 || stream.Meta.RequestID == "" {
		t.Fatalf("live stream lacked text or request metadata: %#v", stream.Meta)
	}
}
