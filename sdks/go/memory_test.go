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
}
