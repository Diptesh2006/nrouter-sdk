package nrouter

import (
	"testing"
)

func TestDiagnoseReasoningExhaustion(t *testing.T) {
	// Exhausted case
	report := DiagnoseReasoningExhaustion("length", 1000, 1000, "")
	if !report.Exhausted {
		t.Fatalf("expected exhaustion detected")
	}
	if report.ReasoningTokens != 1000 {
		t.Errorf("expected 1000 reasoning tokens, got %d", report.ReasoningTokens)
	}

	// Normal case with content
	normal := DiagnoseReasoningExhaustion("stop", 50, 10, "Here is the answer")
	if normal.Exhausted {
		t.Fatalf("did not expect exhaustion when content is present")
	}

	// Length finish but content generated
	withContent := DiagnoseReasoningExhaustion("length", 1000, 200, "Partial answer")
	if withContent.Exhausted {
		t.Fatalf("did not expect exhaustion when text content was produced")
	}
}
