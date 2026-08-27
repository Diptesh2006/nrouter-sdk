package nrouter

import (
	"errors"
	"fmt"
	"strings"
)

// Kind classifies why a request failed, one value per entry in the `errors`
// block of spec/nrouter-sdk-spec.json plus the two conditions that never
// reach the gateway.
type Kind string

const (
	// KindRequest is invalid_request (400) — invalid JSON or request shape.
	KindRequest Kind = "request"
	// KindGuardrailBlocked is guardrail_blocked (400) — a guardrail rule denied it.
	KindGuardrailBlocked Kind = "guardrail_blocked"
	// KindAuthentication is invalid_api_key (401); see ResponseMeta.AuthReason.
	KindAuthentication Kind = "authentication"
	// KindCredit is insufficient_credits (402) — the reserve failed, nothing spent.
	KindCredit Kind = "credit"
	// KindBudgetExceeded is a BUDGET ceiling (402), not a shortfall.
	//
	// Two conditions share 402 and their fixes are opposites: raise the
	// budget, versus top up the balance. Telling a customer whose budget is
	// exhausted to add money is a wrong answer delivered confidently.
	KindBudgetExceeded Kind = "budget_exceeded"
	// KindNotFound is model_not_found (404) — alias absent or invisible to this key.
	KindNotFound Kind = "not_found"
	// KindRateLimit is rate_limit_exceeded or tpm_limit_exceeded (429).
	KindRateLimit Kind = "rate_limit"
	// KindService is credit_check_failed or service_unavailable (503).
	KindService Kind = "service"
	// KindOther is a code this SDK version does not know. Never reclassified.
	KindOther Kind = "other"
	// KindTransport means the request left this process and got no answer —
	// DNS, TLS, a dropped connection, a timeout. Retryable.
	KindTransport Kind = "transport"
	// KindConfiguration means the SDK refused before sending anything: no key,
	// or a key not shaped like an nRouter key.
	//
	// Separate from KindTransport on purpose. Both are raised locally, but
	// this one is PERMANENT — a caller retrying on IsRetryable would spin
	// forever without ever making a request.
	KindConfiguration Kind = "configuration"
)

// Sentinels for errors.Is. Callers match on the condition, not on a string:
//
//	if errors.Is(err, nrouter.ErrRateLimit) { backOff() }
var (
	ErrRequest          = errors.New("nrouter: invalid request")
	ErrGuardrailBlocked = errors.New("nrouter: guardrail blocked")
	ErrAuthentication   = errors.New("nrouter: authentication failed")
	ErrCredit           = errors.New("nrouter: insufficient credits")
	ErrBudgetExceeded   = errors.New("nrouter: budget exceeded")
	ErrNotFound         = errors.New("nrouter: model not found")
	ErrRateLimit        = errors.New("nrouter: rate limit exceeded")
	ErrService          = errors.New("nrouter: service unavailable")
	ErrOther            = errors.New("nrouter: unrecognized gateway error")
	ErrTransport        = errors.New("nrouter: transport failure")
	ErrConfiguration    = errors.New("nrouter: configuration error")
)

var sentinels = map[Kind]error{
	KindRequest:          ErrRequest,
	KindGuardrailBlocked: ErrGuardrailBlocked,
	KindAuthentication:   ErrAuthentication,
	KindCredit:           ErrCredit,
	KindBudgetExceeded:   ErrBudgetExceeded,
	KindNotFound:         ErrNotFound,
	KindRateLimit:        ErrRateLimit,
	KindService:          ErrService,
	KindOther:            ErrOther,
	KindTransport:        ErrTransport,
	KindConfiguration:    ErrConfiguration,
}

// Error is every failure this SDK returns. Inspect it with errors.As.
type Error struct {
	Kind Kind
	// Message is the gateway's wording, or the local reason for a transport
	// or configuration failure.
	Message string
	// Code is the gateway's stable error code when it sent one. The gateway's
	// main error path sends {"error":{"type","message"}} with NO code, so an
	// empty Code is the ordinary case rather than an anomaly.
	Code string
	// Status is the HTTP status, 0 when the request never reached the gateway.
	Status int
	// RequestID joins this failure to a gateway spend row or log line.
	RequestID string
	// LimitSource is which limit measured a 429. Empty means the gateway did
	// not say; never guessed.
	LimitSource string
	// AuthReason is the gateway's stable reason on a 401.
	AuthReason string
	// RetryAfter is the Retry-After header in whole seconds, when sent.
	RetryAfter *uint64
}

func (e *Error) Error() string {
	if e.Code != "" {
		return fmt.Sprintf("nrouter: %s (%s)", e.Message, e.Code)
	}
	return "nrouter: " + e.Message
}

// Unwrap exposes the sentinel so errors.Is works on the condition.
func (e *Error) Unwrap() error { return sentinels[e.Kind] }

// IsRetryable reports whether retrying the identical request could plausibly
// succeed. Deliberately false for every 4xx naming a permanent condition: a
// retry there burns quota and cannot change the answer.
func (e *Error) IsRetryable() bool {
	return e.Kind == KindRateLimit || e.Kind == KindService || e.Kind == KindTransport
}

func configErr(format string, args ...any) *Error {
	return &Error{Kind: KindConfiguration, Message: fmt.Sprintf(format, args...)}
}

func transportErr(format string, args ...any) *Error {
	return &Error{Kind: KindTransport, Message: fmt.Sprintf(format, args...)}
}

// classify turns a gateway refusal into a Kind.
//
// Three signals, in order, because no single one is sufficient:
//
//  1. Code, when present — the only thing separating rate_limit_exceeded from
//     tpm_limit_exceeded. The gateway's WAF and its upstream passthrough send one.
//  2. Status, otherwise. The gateway's main error path emits no code at all,
//     so this is the ordinary route, not the fallback it looks like.
//  3. The message, to split the two 400s and the two 402s. Classifying every
//     400 as a request error makes KindGuardrailBlocked unreachable, telling a
//     caller to fix a body that was never the problem.
func classify(code, message string, status int) Kind {
	switch code {
	case "invalid_request":
		return KindRequest
	case "guardrail_blocked":
		return KindGuardrailBlocked
	case "invalid_api_key":
		return KindAuthentication
	case "insufficient_credits":
		return KindCredit
	case "model_not_found":
		return KindNotFound
	case "rate_limit_exceeded", "tpm_limit_exceeded":
		return KindRateLimit
	case "credit_check_failed", "service_unavailable":
		return KindService
	case "":
		// fall through to status dispatch below
	default:
		return KindOther
	}

	lower := strings.ToLower(message)
	switch status {
	case 400:
		if strings.Contains(lower, "guardrail") {
			return KindGuardrailBlocked
		}
		return KindRequest
	case 401:
		return KindAuthentication
	case 402:
		// The gateway's own wording is the only discriminator it gives us, and
		// it is stable: GatewayError::{BudgetExceeded, ScopedBudgetExceeded}
		// both begin their Display with "budget".
		if strings.HasPrefix(strings.TrimSpace(lower), "budget") {
			return KindBudgetExceeded
		}
		return KindCredit
	case 404:
		// Scoped to MODELS. A 404 is also a missing video job, an unknown MCP
		// server or an unknown agent run; calling those model_not_found is a
		// wrong answer with a confident stable code on it.
		if strings.Contains(lower, "model") {
			return KindNotFound
		}
		return KindOther
	case 429:
		return KindRateLimit
	case 503:
		return KindService
	}
	return KindOther
}
