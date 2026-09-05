package nrouter

import (
	"fmt"
	"math"
	"strconv"
)

// ResponseMeta is the per-request metadata the gateway reports on `x-nr-*`
// response headers.
//
// Every numeric field is a POINTER on purpose. The gateway omits a header
// rather than sending a placeholder, and the two that matter most are
// omissions: x-nr-request-cost is ABSENT when the model is unpriced — never
// "0" — and x-nr-response-cache-age is absent on a miss. A float64 zero value
// would render an unpriced request as free, which no enabled model is.
type ResponseMeta struct {
	// RequestID is present on every response; the join key for a spend row or
	// a support ticket.
	RequestID string

	// Cost is the exact settled cost in USD. Nil when unpriced. Never treat
	// nil as 0.
	Cost *float64

	// CostStatus is "exact" or "unpriced".
	CostStatus string

	// Model is the model that actually served the request, which is not
	// always the alias that was asked for.
	Model string

	InputTokens      *uint64
	OutputTokens     *uint64
	TotalTokens      *uint64
	CacheReadTokens  *uint64
	CacheWriteTokens *uint64

	// LimitSource says which limit measured a 429: key, plan, team, user or
	// budget. Empty means the gateway did not say — never guess, or the
	// customer raises the wrong limit.
	LimitSource string

	// BudgetWarning is set when this request crossed a soft budget you
	// configured; the request still served. Its value is
	// "<scope> soft_budget <spend>/<ceiling>", e.g. "org soft_budget 80.00/100.00".
	BudgetWarning string

	// Guardrails is the posture of the PRE-CALL guardrail chain: "none",
	// "monitor", "pass", "partial" or "blocked". Compare it exactly and
	// case-sensitively.
	//
	// Empty means the gateway made NO guardrail claim about this response — a
	// /v1/models call, an auth refusal that never reached preflight — never "no
	// guardrail applied", which is the explicit "none". Not published on the
	// image, audio or video routes.
	//
	// Posture only, by design: the policy name, its id, the detector family,
	// the rule count and, for "partial", which channel went uninspected are all
	// deliberately withheld. A rule count moves when a policy moves, so a
	// caller watching it maps a tenant's controls without ever tripping one.
	Guardrails string

	// AuthReason is the gateway's stable reason for refusing a virtual key on
	// a 401, e.g. "key_route_not_allowed".
	AuthReason string

	// ResponseCache is "hit" or "miss"; empty when the response cache did not
	// participate at all (streaming and the non-text modalities bypass it).
	ResponseCache string

	// ResponseCacheAge is whole seconds since a cached response was produced.
	// Set on hits only.
	ResponseCacheAge *uint64
}

// HeaderNames lists every response header this SDK reads, exactly as the
// gateway spells them. Kept as data so callers can forward the same set
// through their own logging or tracing layer without retyping it.
var HeaderNames = []string{
	"x-nr-request-id",
	"x-nr-request-cost",
	"x-nr-cost-status",
	"x-nr-model",
	"x-nr-input-tokens",
	"x-nr-output-tokens",
	"x-nr-total-tokens",
	"x-nr-cache-read-tokens",
	"x-nr-cache-write-tokens",
	"x-nr-limit-source",
	"x-nr-budget-warning",
	"x-nr-guardrails",
	"x-nr-auth-reason",
	"x-nr-response-cache",
	"x-nr-response-cache-age",
}

// MetaFromLookup builds ResponseMeta from any lowercase-name header lookup.
//
// An unparseable numeric header yields nil rather than a zero: a zero here
// would be indistinguishable from a real measured zero.
func MetaFromLookup(get func(string) string) ResponseMeta {
	num := func(name string) *uint64 {
		raw := get(name)
		if raw == "" {
			return nil
		}
		// No TrimSpace: MEASURED as dead. net/http strips optional whitespace
		// around a header value before Get returns it, and ParseUint rejects a
		// whitespace-only string, a negative and an out-of-range value on its
		// own. A mutation test proved it — deleting the trim changed no result.
		v, err := strconv.ParseUint(raw, 10, 64)
		if err != nil {
			return nil
		}
		return &v
	}
	meta := ResponseMeta{
		RequestID:        get("x-nr-request-id"),
		CostStatus:       get("x-nr-cost-status"),
		Model:            get("x-nr-model"),
		InputTokens:      num("x-nr-input-tokens"),
		OutputTokens:     num("x-nr-output-tokens"),
		TotalTokens:      num("x-nr-total-tokens"),
		CacheReadTokens:  num("x-nr-cache-read-tokens"),
		CacheWriteTokens: num("x-nr-cache-write-tokens"),
		LimitSource:      get("x-nr-limit-source"),
		BudgetWarning:    get("x-nr-budget-warning"),
		Guardrails:       get("x-nr-guardrails"),
		AuthReason:       get("x-nr-auth-reason"),
		ResponseCache:    get("x-nr-response-cache"),
		ResponseCacheAge: num("x-nr-response-cache-age"),
	}
	if raw := get("x-nr-request-cost"); raw != "" {
		if v, err := strconv.ParseFloat(raw, 64); err == nil && isBillableAmount(v) {
			meta.Cost = &v
		}
	}
	return meta
}

// IsPriced reports whether the gateway priced this request exactly. It is
// deliberately not "Cost != nil": a cost with a status of "unpriced" is a
// contradiction the caller should not bill against.
func (m ResponseMeta) IsPriced() bool {
	return m.CostStatus == "exact" && m.Cost != nil
}

// BudgetWarningInfo contains structured soft budget warning details.
type BudgetWarningInfo struct {
	Scope   string
	Spend   float64
	Ceiling float64
}

// ParseBudgetWarning parses BudgetWarning into scope, spend, and ceiling.
func (m ResponseMeta) ParseBudgetWarning() *BudgetWarningInfo {
	if m.BudgetWarning == "" {
		return nil
	}
	var scope string
	var spend, ceiling float64
	n, err := fmt.Sscanf(m.BudgetWarning, "%s soft_budget %f/%f", &scope, &spend, &ceiling)
	if err != nil || n != 3 {
		return nil
	}
	return &BudgetWarningInfo{
		Scope:   scope,
		Spend:   spend,
		Ceiling: ceiling,
	}
}

// IsCacheHit reports whether the response came from the response cache.
func (m ResponseMeta) IsCacheHit() bool {
	return m.ResponseCache == "hit"
}

// IsCacheMiss reports whether the response cache was queried but missed.
func (m ResponseMeta) IsCacheMiss() bool {
	return m.ResponseCache == "miss"
}

// CacheAgeSeconds returns the cached age in seconds, or 0 if absent.
func (m ResponseMeta) CacheAgeSeconds() uint64 {
	if m.ResponseCacheAge != nil {
		return *m.ResponseCacheAge
	}
	return 0
}

// isBillableAmount rejects the values that are syntactically valid floats but
// are not amounts of money.
//
// strconv.ParseFloat accepts "NaN", "Inf", "+Inf" and "Infinity" with a nil
// error, so each one produced a non-nil Cost that a caller would bill against
// — and a NaN then poisons every sum it reaches, silently, forever. A negative
// is rejected for the same reason: the gateway never bills a negative amount,
// so a minus sign means corruption, and a negative quietly netted against a
// bill is worse than a missing one.
//
// A genuine 0 survives. The guard rejects nonsense, not small numbers.
//
// Found by porting this file to TypeScript: Number(”) === 0 forced the same
// question there, and asking it exposed that Go had the wider hole.
func isBillableAmount(v float64) bool {
	return !math.IsNaN(v) && !math.IsInf(v, 0) && v >= 0
}
