package nrouter

import (
	"fmt"
	"strings"
)

const (
	PromptTemplateIDField = "nrouter_prompt_template_id"
	PromptVariablesField  = "nrouter_prompt_variables"
)

var (
	PromptWireFields    = []string{PromptTemplateIDField, PromptVariablesField}
	SystemVariableNames = []string{"org_name", "model", "timestamp", "user_id"}
)

// PromptSelection holds prompt template configuration.
type PromptSelection struct {
	TemplateID string
	Variables  map[string]any
}

// PromptTemplate creates a PromptSelection specifying a template ID and optional variables.
func PromptTemplate(id string, variables ...map[string]any) (PromptSelection, error) {
	trimmed := strings.TrimSpace(id)
	if trimmed == "" {
		return PromptSelection{}, fmt.Errorf("prompt_template requires a non-empty template id")
	}
	vars := make(map[string]any)
	if len(variables) > 0 && variables[0] != nil {
		for k, v := range variables[0] {
			vars[k] = v
		}
	}
	return PromptSelection{
		TemplateID: trimmed,
		Variables:  vars,
	}, nil
}

// PromptVariables creates a PromptSelection specifying only variables for the assigned template.
func PromptVariables(variables map[string]any) PromptSelection {
	vars := make(map[string]any)
	if variables != nil {
		for k, v := range variables {
			vars[k] = v
		}
	}
	return PromptSelection{
		Variables: vars,
	}
}

// WithVariables returns a new PromptSelection with merged variables (incoming overrides).
func (p PromptSelection) WithVariables(variables map[string]any) PromptSelection {
	merged := make(map[string]any)
	for k, v := range p.Variables {
		merged[k] = v
	}
	if variables != nil {
		for k, v := range variables {
			merged[k] = v
		}
	}
	return PromptSelection{
		TemplateID: p.TemplateID,
		Variables:  merged,
	}
}

// ApplyTo adds prompt template fields to an extra body map.
func (p PromptSelection) ApplyTo(extra map[string]any) {
	if extra == nil {
		return
	}
	if p.TemplateID != "" {
		extra[PromptTemplateIDField] = p.TemplateID
	}
	if len(p.Variables) > 0 {
		extra[PromptVariablesField] = p.Variables
	}
}

// SystemVariableConflicts checks if any caller variables collide with gateway system variables.
// Returns conflicting variable names in the gateway's deterministic insertion order.
func SystemVariableConflicts(variables map[string]any) []string {
	if variables == nil {
		return nil
	}
	var conflicts []string
	for _, sysVar := range SystemVariableNames {
		if _, exists := variables[sysVar]; exists {
			conflicts = append(conflicts, sysVar)
		}
	}
	return conflicts
}
