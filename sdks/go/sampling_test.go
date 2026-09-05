package nrouter

import (
	"math"
	"testing"
)

func TestIsClaudeModel(t *testing.T) {
	if !IsClaudeModel("claude-3-5-sonnet", "") {
		t.Errorf("expected claude-3-5-sonnet to be recognized as claude")
	}
	if !IsClaudeModel("sonnet-4-5", "") {
		t.Errorf("expected sonnet-4-5 to be recognized as claude")
	}
	if !IsClaudeModel("haiku-3-5", "") {
		t.Errorf("expected haiku-3-5 to be recognized as claude")
	}
	if !IsClaudeModel("opus-4", "") {
		t.Errorf("expected opus-4 to be recognized as claude")
	}
	if !IsClaudeModel("custom-alias", "anthropic") {
		t.Errorf("expected anthropic provider to be recognized as claude")
	}
	if IsClaudeModel("gpt-4o", "openai") {
		t.Errorf("expected gpt-4o not to be recognized as claude")
	}
}

func TestNormalizeAnthropicMessages(t *testing.T) {
	input := map[string]any{
		"model": "claude-sonnet-4-5",
		"messages": []any{
			map[string]any{"role": "system", "content": "System turn 1"},
			map[string]any{"role": "user", "content": "Hello"},
		},
		"system": "Initial system",
		"max_completion_tokens": 1024,
		"stop": "Human:",
	}
	normalized := NormalizeAnthropicMessages(input).(map[string]any)
	if normalized["system"] != "Initial system\n\nSystem turn 1" {
		t.Errorf("expected joined system prompt, got %v", normalized["system"])
	}
	msgs := normalized["messages"].([]any)
	if len(msgs) != 1 {
		t.Errorf("expected 1 cleaned message, got %d", len(msgs))
	}
	if normalized["max_tokens"] != 1024 {
		t.Errorf("expected max_tokens to be 1024, got %v", normalized["max_tokens"])
	}
	stops := normalized["stop_sequences"].([]string)
	if len(stops) != 1 || stops[0] != "Human:" {
		t.Errorf("expected stop_sequences [Human:], got %v", stops)
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
