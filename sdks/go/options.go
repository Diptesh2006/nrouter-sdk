package nrouter

import (
	"strings"
)

// ExtraBodyFields are the 3 fields the gateway reads from request bodies.
var ExtraBodyFields = []string{
	"nrouter_prompt_template_id",
	"nrouter_prompt_variables",
	"nrouter_cache",
}

var forbiddenTenancyKeys = map[string]struct{}{
	"organizationid": {},
	"orgid":          {},
	"teamid":         {},
	"userid":         {},
	"nrouterorg":     {},
}

// FeatureOptions holds caller-supplied nRouter-specific feature toggles.
type FeatureOptions struct {
	PromptTemplateID string
	PromptVariables  map[string]any
	GuardrailIDs     []string
	Cache            *bool
}

// BuildExtraBody produces the nRouter extra body map and refuses guardrail_ids.
func BuildExtraBody(opts FeatureOptions) (map[string]any, error) {
	if len(opts.GuardrailIDs) > 0 {
		return nil, configErr("guardrail_ids is not supported: guardrails are assigned per key, team, or organization in the nRouter dashboard and already apply automatically to every call.")
	}

	extra := make(map[string]any)
	if trimmed := strings.TrimSpace(opts.PromptTemplateID); trimmed != "" {
		extra["nrouter_prompt_template_id"] = trimmed
	}
	if len(opts.PromptVariables) > 0 {
		extra["nrouter_prompt_variables"] = opts.PromptVariables
	}
	if opts.Cache != nil && !*opts.Cache {
		extra["nrouter_cache"] = false
	}
	return extra, nil
}

// VetExtra verifies that caller-supplied extra keys do not contain forbidden tenancy keys or __proto__.
func VetExtra(extra map[string]any) error {
	for k := range extra {
		norm := strings.ToLower(strings.ReplaceAll(strings.ReplaceAll(k, "_", ""), "-", ""))
		if _, ok := forbiddenTenancyKeys[norm]; ok {
			return configErr("extra must not carry the tenancy field %q. The gateway resolves organization, team, and user from the authenticated API key alone.", k)
		}
		if k == "__proto__" {
			return configErr("extra must not carry a \"__proto__\" key")
		}
	}
	return nil
}
