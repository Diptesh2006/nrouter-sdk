package nrouter

import (
	"math"
	"testing"
)

func TestIsClaudeModel(t *testing.T) {
	if !IsClaudeModel("claude-3-5-sonnet", "") {
		t.Errorf("expected claude-3-5-sonnet to be recognized as claude")
	}
	if !IsClaudeModel("custom-alias", "anthropic") {
		t.Errorf("expected anthropic provider to be recognized as claude")
	}
	if IsClaudeModel("gpt-4o", "openai") {
		t.Errorf("expected gpt-4o not to be recognized as claude")
	}
}

func TestBuildSamplingParams(t *testing.T) {
	temp := 0.7
	topP := 0.9

	// Advanced false returns empty
	empty, err := BuildSamplingParams(false, "claude-3", "", &temp, &topP)
	if err != nil || len(empty) != 0 {
		t.Fatalf("expected empty params when advanced is false")
	}

	// Claude model with topP suppresses temperature
	claudeParams, err := BuildSamplingParams(true, "claude-3", "", &temp, &topP)
	if err != nil {
		t.Fatalf("BuildSamplingParams failed: %v", err)
	}
	if _, ok := claudeParams["temperature"]; ok {
		t.Errorf("expected temperature to be suppressed for Claude when top_p is set")
	}
	if v, ok := claudeParams["top_p"]; !ok || v != 0.9 {
		t.Errorf("expected top_p to be 0.9, got %v", v)
	}

	// Non-claude keeps both
	gptParams, err := BuildSamplingParams(true, "gpt-4o", "openai", &temp, &topP)
	if err != nil {
		t.Fatalf("BuildSamplingParams failed: %v", err)
	}
	if v, ok := gptParams["temperature"]; !ok || v != 0.7 {
		t.Errorf("expected temperature to be preserved for GPT")
	}
	if v, ok := gptParams["top_p"]; !ok || v != 0.9 {
		t.Errorf("expected top_p to be preserved for GPT")
	}

	// Validation errors
	nan := math.NaN()
	if _, err := BuildSamplingParams(true, "gpt-4o", "", &nan, nil); err == nil {
		t.Errorf("expected error for NaN temperature")
	}

	badTopP := 1.5
	if _, err := BuildSamplingParams(true, "gpt-4o", "", nil, &badTopP); err == nil {
		t.Errorf("expected error for top_p > 1.0")
	}
}
