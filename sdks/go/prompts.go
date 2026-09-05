package nrouter

import (
	"fmt"
	"regexp"
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

// RenderPromptOptions controls client-side prompt template interpolation.
type RenderPromptOptions struct {
	Strict          bool
	SystemVariables map[string]string
}

var promptVariableRegex = regexp.MustCompile(`\{\{\s*([a-zA-Z0-9_-]+)\s*\}\}`)

// RenderPrompt safely interpolates `{{variable}}` or `{{ variable }}` tokens in a template.
//
// Security & resiliency features:
// - Single-pass replacement prevents recursive variable expansion loops.
// - Safe interpolation: no metacharacter injection from variable values.
// - Strict mode: returns error if any template variable is missing.
// - System variables: take precedence over caller variables matching gateway rules.
func RenderPrompt(template string, variables map[string]any, opts ...RenderPromptOptions) (string, error) {
	if template == "" {
		return "", nil
	}
	var options RenderPromptOptions
	if len(opts) > 0 {
		options = opts[0]
	}

	var missingKeys []string
	result := promptVariableRegex.ReplaceAllStringFunc(template, func(match string) string {
		submatches := promptVariableRegex.FindStringSubmatch(match)
		if len(submatches) < 2 {
			return match
		}
		key := submatches[1]

		// 1. System variables take precedence
		if options.SystemVariables != nil {
			if sysVal, ok := options.SystemVariables[key]; ok {
				return sysVal
			}
		}

		// 2. Caller variables
		if variables != nil {
			if val, ok := variables[key]; ok {
				if val == nil {
					return ""
				}
				return fmt.Sprintf("%v", val)
			}
		}

		if options.Strict {
			missingKeys = append(missingKeys, key)
		}
		return match
	})

	if options.Strict && len(missingKeys) > 0 {
		return "", fmt.Errorf("missing required prompt template variables: %s", strings.Join(missingKeys, ", "))
	}

	return result, nil
}

