package nrouter

import (
	"reflect"
	"testing"
)

func TestPromptHelpersAndConflicts(t *testing.T) {
	// 1. Valid template
	sel, err := PromptTemplate("tpl_abc", map[string]any{"customer": "Acme"})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if sel.TemplateID != "tpl_abc" {
		t.Fatalf("expected template ID tpl_abc, got %s", sel.TemplateID)
	}
	if sel.Variables["customer"] != "Acme" {
		t.Fatalf("expected variable customer=Acme")
	}

	// 2. Reject empty template id
	_, err = PromptTemplate("   ")
	if err == nil {
		t.Fatal("expected error for empty template id")
	}

	// 3. WithVariables merges
	merged := sel.WithVariables(map[string]any{"user": "Alice", "customer": "Beta"})
	if merged.Variables["user"] != "Alice" || merged.Variables["customer"] != "Beta" {
		t.Fatalf("unexpected merged variables: %v", merged.Variables)
	}

	// 4. ApplyTo
	extra := make(map[string]any)
	merged.ApplyTo(extra)
	if extra[PromptTemplateIDField] != "tpl_abc" {
		t.Fatalf("expected extra prompt template id")
	}
	if extra[PromptVariablesField] == nil {
		t.Fatalf("expected extra prompt variables")
	}

	// 5. System variable conflicts in gateway insertion order
	conflicts := SystemVariableConflicts(map[string]any{
		"user_id":   "u123",
		"custom":    "val",
		"org_name":  "orgX",
		"timestamp": 123456,
	})
	expected := []string{"org_name", "timestamp", "user_id"}
	if !reflect.DeepEqual(conflicts, expected) {
		t.Fatalf("expected conflicts %v, got %v", expected, conflicts)
	}
}
