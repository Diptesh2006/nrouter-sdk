package nrouter

import (
	"testing"
)

func TestMemoryStoreAndTenancyValidation(t *testing.T) {
	mem := NewMemory()

	// 1. Valid messages
	err := mem.Add(ChatMessage{"role": "user", "content": "Hello"})
	if err != nil {
		t.Fatalf("unexpected error adding valid message: %v", err)
	}

	err = mem.Add(ChatMessage{"role": "assistant", "content": "Hi there!"})
	if err != nil {
		t.Fatalf("unexpected error adding assistant message: %v", err)
	}

	msgs, err := mem.Messages()
	if err != nil {
		t.Fatalf("failed to retrieve messages: %v", err)
	}
	if len(msgs) != 2 {
		t.Fatalf("expected 2 messages, got %d", len(msgs))
	}

	// 2. Reject missing or invalid role
	err = mem.Add(ChatMessage{"content": "No role"})
	if err == nil {
		t.Fatal("expected error for message without role")
	}

	// 3. Reject forbidden tenancy keys
	forbidden := []string{"organization_id", "org_id", "team_id", "user_id", "nrouter_org"}
	for _, fk := range forbidden {
		err = mem.Add(ChatMessage{"role": "user", "content": "hack", fk: "injected-tenant"})
		if err == nil {
			t.Fatalf("expected error for forbidden tenancy key %q", fk)
		}
	}

	// 4. Clear
	err = mem.Clear()
	if err != nil {
		t.Fatalf("failed to clear memory: %v", err)
	}

	msgs, err = mem.Messages()
	if err != nil || len(msgs) != 0 {
		t.Fatalf("expected 0 messages after clear, got %d (err: %v)", len(msgs), err)
	}

	// 5. Developer and tool roles
	if err := mem.Add(ChatMessage{"role": "developer", "content": "instructions"}); err != nil {
		t.Fatalf("expected developer role to succeed, got %v", err)
	}
	if err := mem.Add(ChatMessage{"role": "tool", "content": "tool-res", "tool_call_id": "c1"}); err != nil {
		t.Fatalf("expected tool role to succeed, got %v", err)
	}

	// 6. Assistant with tool_calls and null content
	if err := mem.Add(ChatMessage{
		"role":       "assistant",
		"content":    nil,
		"tool_calls": []any{map[string]any{"id": "c1"}},
	}); err != nil {
		t.Fatalf("expected assistant message with null content and tool_calls to succeed, got %v", err)
	}
}

func TestSlidingWindow(t *testing.T) {
	msgs := []ChatMessage{
		{"role": "system", "content": "sys"},
		{"role": "user", "content": "1"},
		{"role": "assistant", "content": "2"},
		{"role": "user", "content": "3"},
		{"role": "assistant", "content": "4"},
	}

	pruned := SlidingWindow(msgs, 3, true)
	if len(pruned) != 3 {
		t.Fatalf("expected 3 messages, got %d", len(pruned))
	}
	if pruned[0]["role"] != "system" || pruned[0]["content"] != "sys" {
		t.Fatalf("expected system message preserved, got %v", pruned[0])
	}
	if pruned[1]["content"] != "3" || pruned[2]["content"] != "4" {
		t.Fatalf("expected last 2 non-system turns, got %v and %v", pruned[1], pruned[2])
	}

	noPreserve := SlidingWindow(msgs, 2, false)
	if len(noPreserve) != 2 || noPreserve[0]["content"] != "3" || noPreserve[1]["content"] != "4" {
		t.Fatalf("expected last 2 turns strictly, got %v", noPreserve)
	}
}
