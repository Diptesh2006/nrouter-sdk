package nrouter

import (
	"fmt"
	"math"
	"strings"
)

const NeutralTopP = 1.0

// IsClaudeModel returns true if the model or provider indicates an Anthropic Claude model.
func IsClaudeModel(model string, provider string) bool {
	m := strings.ToLower(model)
	p := strings.ToLower(provider)
	return strings.Contains(m, "claude") || strings.Contains(p, "anthropic")
}

// BuildSamplingParams implements the Claude sampling mutual exclusion policy.
// If advanced is false, it returns an empty map.
// If top_p != 1.0 on a Claude model, temperature is suppressed.
func BuildSamplingParams(advanced bool, model, provider string, temperature, topP *float64) (map[string]any, error) {
	if !advanced {
		return map[string]any{}, nil
	}

	if temperature != nil {
		if err := requireUsable("temperature", *temperature, nil); err != nil {
			return nil, err
		}
	}
	if topP != nil {
		max := 1.0
		if err := requireUsable("top_p", *topP, &max); err != nil {
			return nil, err
		}
	}

	topPSet := topP != nil && *topP != NeutralTopP
	suppressTemperature := topPSet && IsClaudeModel(model, provider)

	out := make(map[string]any)
	if temperature != nil && !suppressTemperature {
		out["temperature"] = *temperature
	}
	if topP != nil && topPSet {
		out["top_p"] = *topP
	}
	return out, nil
}

func requireUsable(name string, value float64, max *float64) error {
	if math.IsNaN(value) || math.IsInf(value, 0) {
		return fmt.Errorf("%s must be a finite number; sent as-is it serializes to JSON null", name)
	}
	if value < 0.0 || (max != nil && value > *max) {
		if max != nil {
			return fmt.Errorf("%s must be between 0 and %v, got %v", name, *max, value)
		}
		return fmt.Errorf("%s must be 0 or greater, got %v", name, value)
	}
	return nil
}
