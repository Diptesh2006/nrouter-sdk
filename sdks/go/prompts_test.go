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

func TestRenderPrompt(t *testing.T) {
	// 1. Whitespace tolerance & type formatting
	tpl := "Hello {{name}}! Age: {{  age  }}, active: {{ active }}."
	out, err := RenderPrompt(tpl, map[string]any{"name": "Alice", "age": 30, "active": true})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	expected := "Hello Alice! Age: 30, active: true."
	if out != expected {
		t.Fatalf("expected %q, got %q", expected, out)
	}

	// 2. Single-pass non-recursive expansion
	tpl2 := "Value: {{a}}"
	out2, err := RenderPrompt(tpl2, map[string]any{"a": "{{b}}", "b": "final"})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if out2 != "Value: {{b}}" {
		t.Fatalf("expected Value: {{b}}, got %q", out2)
	}

	// 3. Dollar and escape character safety
	tpl3 := "Price: {{price}}, Path: {{path}}"
	out3, err := RenderPrompt(tpl3, map[string]any{"price": "$100", "path": `C:\test\1`})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if out3 != `Price: $100, Path: C:\test\1` {
		t.Fatalf("expected literal escapes preserved, got %q", out3)
	}

	// 4. Non-strict preserves missing tokens
	tpl4 := "Greeting: {{hello}}, missing: {{world}}"
	out4, err := RenderPrompt(tpl4, map[string]any{"hello": "hi"})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if out4 != "Greeting: hi, missing: {{world}}" {
		t.Fatalf("expected missing token preserved, got %q", out4)
	}

	// 5. Strict returns error on missing token
	_, err = RenderPrompt(tpl4, map[string]any{"hello": "hi"}, RenderPromptOptions{Strict: true})
	if err == nil {
		t.Fatal("expected error in strict mode")
	}

	// 6. System variables override
	tpl5 := "Model: {{model}}, User: {{user}}"
	out5, err := RenderPrompt(tpl5, map[string]any{"model": "user-model", "user": "alice"}, RenderPromptOptions{
		SystemVariables: map[string]string{"model": "claude-3-7-sonnet"},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if out5 != "Model: claude-3-7-sonnet, User: alice" {
		t.Fatalf("expected system variable override, got %q", out5)
	}
}

