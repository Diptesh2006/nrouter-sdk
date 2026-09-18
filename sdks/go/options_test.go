package nrouter

import (
	"testing"
)

func TestBuildExtraBody(t *testing.T) {
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

// The per-request overrides the gateway added on 2026-09-17 (74b6970).
//
// `GuardrailIDs` used to be REFUSED here, and that was correct while no
// gateway read a per-request guardrail field: the SDK sending one bought the
// caller an opaque provider rejection. Now that `nrouter_guardrails` is read,
// a refusal would make a shipped safety control unreachable from Go alone.
func TestBuildExtraBodyMapsGuardrailsAndFallbacks(t *testing.T) {
	body, err := BuildExtraBody(FeatureOptions{
		Guardrails: []string{"pii-strict", "gr_1"},
		Fallbacks:  []string{"gpt-4o-mini", "claude-haiku"},
	})
	if err != nil {
		t.Fatalf("BuildExtraBody failed: %v", err)
	}
	guardrails, ok := body["nrouter_guardrails"].([]string)
	if !ok || len(guardrails) != 2 || guardrails[0] != "pii-strict" {
		t.Errorf("expected nrouter_guardrails to carry both names, got %v", body["nrouter_guardrails"])
	}
	fallbacks, ok := body["nrouter_fallbacks"].([]string)
	if !ok || len(fallbacks) != 2 || fallbacks[1] != "claude-haiku" {
		t.Errorf("expected nrouter_fallbacks to carry both models, got %v", body["nrouter_fallbacks"])
	}
}

// Empty means NO SELECTION, so the key is omitted rather than sent as an empty
// array. An empty array on the wire is a caller asking for something; it is not
// what a zero-valued slice means.
func TestBuildExtraBodyOmitsEmptyOverrides(t *testing.T) {
	body, err := BuildExtraBody(FeatureOptions{
		Guardrails: []string{},
		Fallbacks:  []string{},
	})
	if err != nil {
		t.Fatalf("BuildExtraBody failed: %v", err)
	}
	if len(body) != 0 {
		t.Errorf("expected an empty extra body, got %v", body)
	}
}

// Refused locally, before egress. The gateway refuses an over-long list with a
// 400 naming `fallback_not_allowed`, which costs a round trip and does not name
// the Go field the caller set.
func TestBuildExtraBodyRefusesOverlongOverrides(t *testing.T) {
	if _, err := BuildExtraBody(FeatureOptions{
		Fallbacks: []string{"a", "b", "c", "d", "e"},
	}); err == nil {
		t.Errorf("expected 5 fallbacks to be refused (the ceiling is 4)")
	}
	tooMany := make([]string, 9)
	for i := range tooMany {
		tooMany[i] = "g"
	}
	if _, err := BuildExtraBody(FeatureOptions{Guardrails: tooMany}); err == nil {
		t.Errorf("expected 9 guardrails to be refused (the ceiling is 8)")
	}
}

// ExtraBodyFields IS the spec's field set. Hand-listed here because Go has no
// runtime access to the spec file from a unit test without embedding it, so
// the binding is held by conformance/check_conformance.py's option-builder pin
// as well — this half catches a constant that drifts from what the builder can
// actually emit.
func TestExtraBodyFieldsCoversEveryEmittableField(t *testing.T) {
	cacheOff := false
	body, err := BuildExtraBody(FeatureOptions{
		PromptTemplateID: "tpl",
		PromptVariables:  map[string]any{"k": "v"},
		Guardrails:       []string{"g"},
		Fallbacks:        []string{"m"},
		Cache:            &cacheOff,
	})
	if err != nil {
		t.Fatalf("BuildExtraBody failed: %v", err)
	}
	declared := make(map[string]bool, len(ExtraBodyFields))
	for _, f := range ExtraBodyFields {
		declared[f] = true
	}
	for key := range body {
		if !declared[key] {
			t.Errorf("BuildExtraBody emits %q, which ExtraBodyFields does not declare", key)
		}
	}
	for _, f := range ExtraBodyFields {
		if _, ok := body[f]; !ok {
			t.Errorf("ExtraBodyFields declares %q, which BuildExtraBody never emits", f)
		}
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
