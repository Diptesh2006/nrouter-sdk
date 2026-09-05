package nrouter

import (
	"testing"
)

func TestBuildExtraBody(t *testing.T) {
	// Guardrail IDs refused
	_, err := BuildExtraBody(FeatureOptions{
		GuardrailIDs: []string{"gr_1"},
	})
	if err == nil {
		t.Fatalf("expected error when GuardrailIDs are provided")
	}

	// Normal extra body
	cacheOff := false
	body, err := BuildExtraBody(FeatureOptions{
		PromptTemplateID: "tpl_123",
		PromptVariables:  map[string]any{"customer": "Acme"},
		Cache:            &cacheOff,
	})
	if err != nil {
		t.Fatalf("BuildExtraBody failed: %v", err)
	}
	if body["nrouter_prompt_template_id"] != "tpl_123" {
		t.Errorf("expected tpl_123, got %v", body["nrouter_prompt_template_id"])
	}
	if body["nrouter_cache"] != false {
		t.Errorf("expected nrouter_cache to be false")
	}
}

func TestVetExtra(t *testing.T) {
	err := VetExtra(map[string]any{
		"safe_key": "val",
	})
	if err != nil {
		t.Fatalf("expected safe extra to pass, got: %v", err)
	}

	for _, bad := range []string{"organization_id", "orgId", "TEAM_ID", "user_id", "nrouter_org", "__proto__"} {
		err := VetExtra(map[string]any{bad: "evil"})
		if err == nil {
			t.Errorf("expected %s to be rejected by VetExtra", bad)
		}
	}
}
