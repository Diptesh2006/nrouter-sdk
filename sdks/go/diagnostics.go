package nrouter

import (
	"strings"
)

// ReasoningExhaustionReport contains diagnostic details when reasoning tokens exhaust the generation budget.
type ReasoningExhaustionReport struct {
	Exhausted       bool   `json:"exhausted"`
	FinishReason    string `json:"finish_reason"`
	ReasoningTokens int    `json:"reasoning_tokens"`
	OutputTokens    int    `json:"output_tokens"`
	Message         string `json:"message"`
}

// DiagnoseReasoningExhaustion analyzes completion output to determine if reasoning tokens consumed
// the entire token budget before any final response text could be generated.
func DiagnoseReasoningExhaustion(finishReason string, outputTokens, reasoningTokens int, content string) ReasoningExhaustionReport {
	f := strings.ToLower(strings.TrimSpace(finishReason))
	if (f == "length" || f == "max_tokens") && strings.TrimSpace(content) == "" {
		if reasoningTokens > 0 || outputTokens > 0 {
			return ReasoningExhaustionReport{
				Exhausted:       true,
				FinishReason:    finishReason,
				ReasoningTokens: reasoningTokens,
				OutputTokens:    outputTokens,
				Message:         "Reasoning consumed the entire token budget before completion text could be generated. Increase max_tokens or max_completion_tokens.",
			}
		}
	}
	return ReasoningExhaustionReport{
		Exhausted:    false,
		FinishReason: finishReason,
	}
}
