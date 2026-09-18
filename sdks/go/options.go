package nrouter

import (
	"strings"
)

// ExtraBodyFields are the fields the gateway reads from request bodies.
//
// The set is CLOSED — spec/nrouter-sdk-spec.json `extra_body_fields` is the
// whole of it, and the gateway forwards everything else to the provider
// verbatim. A field this SDK invents is not an error a caller ever sees; it is
// a dead option that looks live.
var ExtraBodyFields = []string{
	"nrouter_prompt_template_id",
	"nrouter_prompt_variables",
	"nrouter_cache",
	"nrouter_fallbacks",
	"nrouter_guardrails",
}

// Published ceilings, from the spec's extra_body_fields entries.
//
// Enforced here rather than left to the gateway: the gateway refuses an
// over-long list with a 400 the caller pays a round trip for, and that refusal
// names the wire field rather than the Go field they set.
const (
	MaxFallbacks  = 4
	MaxGuardrails = 8
)

var forbiddenTenancyKeys = map[string]struct{}{
	"organizationid": {},
	"orgid":          {},
	"teamid":         {},
	"userid":         {},
	"nrouterorg":     {},
}

// FeatureOptions holds caller-supplied nRouter-specific feature toggles.
//
// GuardrailIDs used to live here as a REFUSAL, and that was correct while it
// lasted: measured 2026-08-28, no gateway read any per-request guardrail field,
// so sending one bought the caller an opaque provider rejection. The gateway
// added real per-request overrides on 2026-09-17, so the refusal now inverts
// its own reason and is gone. They are NOT renames of it:
//
//   - Fallbacks REPLACES the organization's fallback policy for this one call;
//     it is not merged with it, and the primary stays whatever `model` names.
//   - Guardrails is ADD-ONLY. It adds to what the key, team and organization
//     already assign and to the platform moderation floor, and can never
//     remove, relax or replace any of them.
type FeatureOptions struct {
	PromptTemplateID string
	PromptVariables  map[string]any
	// Fallbacks is up to MaxFallbacks model names tried in order when the
	// primary cannot be served.
	Fallbacks []string
	// Guardrails is up to MaxGuardrails guardrail ids or names owned by this
	// organization.
	Guardrails []string
	Cache      *bool
}

// BuildExtraBody produces the nRouter extra body map.
//
// A nil or empty override slice is OMITTED rather than sent as an empty array:
// on this wire omission and emptiness mean different things, and a zero-valued
// slice is a caller asking for nothing, not a caller asking for an empty list.
func BuildExtraBody(opts FeatureOptions) (map[string]any, error) {
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
	if len(opts.Fallbacks) > 0 {
		names, err := overrideNames(opts.Fallbacks, "Fallbacks", MaxFallbacks)
		if err != nil {
			return nil, err
		}
		extra["nrouter_fallbacks"] = names
	}
	if len(opts.Guardrails) > 0 {
		names, err := overrideNames(opts.Guardrails, "Guardrails", MaxGuardrails)
		if err != nil {
			return nil, err
		}
		extra["nrouter_guardrails"] = names
	}
	return extra, nil
}

// overrideNames normalizes one override list, or refuses it.
//
// An empty entry is REFUSED rather than trimmed away. Dropping one leaves the
// caller with a shorter list than they wrote and nothing saying so: for
// guardrails that is a safety control the request was never inspected by, and
// for fallbacks it is a chain shorter than the one they reasoned about.
func overrideNames(value []string, field string, ceiling int) ([]string, error) {
	out := make([]string, 0, len(value))
	for _, entry := range value {
		trimmed := strings.TrimSpace(entry)
		if trimmed == "" {
			return nil, configErr("%s contains an empty entry; every entry must be a non-empty name", field)
		}
		out = append(out, trimmed)
	}
	if len(out) > ceiling {
		return nil, configErr("%s carries %d entries; the gateway accepts at most %d, and sends a 400 for the whole request before any provider call", field, len(out), ceiling)
	}
	return out, nil
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
