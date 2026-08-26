//! Typed errors, derived from `spec/nrouter-sdk-spec.json`.
//!
//! The gateway states a stable `code` in the error body. That code — not the
//! HTTP status alone — decides the variant, because two codes share 400 and two
//! share 429, and a caller reacts differently to each.

use std::fmt;

/// Why the gateway refused a request.
///
/// Variants map one-to-one to the `errors` block of the SDK spec. A code the
/// SDK does not know is preserved as [`NRouterError::Other`] rather than being
/// forced into a neighbouring variant — guessing here would tell a caller to
/// retry something permanent.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum NRouterError {
    /// `invalid_request` (400) — invalid JSON or request shape.
    Request(ErrorBody),
    /// `guardrail_blocked` (400) — a guardrail rule denied the request.
    GuardrailBlocked(ErrorBody),
    /// `invalid_api_key` (401) — virtual-key authentication refused.
    Authentication(ErrorBody),
    /// `insufficient_credits` (402) — the credit reserve failed.
    Credit(ErrorBody),
    /// `model_not_found` (404) — alias absent or invisible to this tenant.
    NotFound(ErrorBody),
    /// `rate_limit_exceeded` / `tpm_limit_exceeded` (429).
    RateLimit(ErrorBody),
    /// `credit_check_failed` / `service_unavailable` (503).
    Service(ErrorBody),
    /// A code this SDK version does not know. Never re-classified.
    Other(ErrorBody),
    /// The request never reached the gateway.
    Transport(String),
}

/// The parsed gateway error payload plus the metadata worth acting on.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct ErrorBody {
    pub message: String,
    pub code: Option<String>,
    pub status: Option<u16>,
    pub request_id: Option<String>,
    /// Present on a 429: which limit measured the refusal. Never guessed —
    /// absent means the gateway did not say, and reporting a guess sends a
    /// customer to raise the wrong limit.
    pub limit_source: Option<String>,
    /// Present on a 401: the gateway's stable reason, e.g. `key_route_not_allowed`.
    pub auth_reason: Option<String>,
    /// Present on a 429 when the gateway supplied `retry-after`, in seconds.
    pub retry_after: Option<u64>,
}

impl NRouterError {
    /// Build the variant the gateway's `code` names.
    ///
    /// The status is used only when no code was supplied; a code always wins,
    /// because the status alone cannot separate `invalid_request` from
    /// `guardrail_blocked`, nor `rate_limit_exceeded` from `tpm_limit_exceeded`.
    pub fn from_code(body: ErrorBody) -> Self {
        match body.code.as_deref() {
            Some("invalid_request") => Self::Request(body),
            Some("guardrail_blocked") => Self::GuardrailBlocked(body),
            Some("invalid_api_key") => Self::Authentication(body),
            Some("insufficient_credits") => Self::Credit(body),
            Some("model_not_found") => Self::NotFound(body),
            Some("rate_limit_exceeded") | Some("tpm_limit_exceeded") => Self::RateLimit(body),
            Some("credit_check_failed") | Some("service_unavailable") => Self::Service(body),
            Some(_) => Self::Other(body),
            None => match body.status {
                Some(400) => Self::Request(body),
                Some(401) => Self::Authentication(body),
                Some(402) => Self::Credit(body),
                Some(404) => Self::NotFound(body),
                Some(429) => Self::RateLimit(body),
                Some(503) => Self::Service(body),
                _ => Self::Other(body),
            },
        }
    }

    /// The gateway payload, when the request actually reached the gateway.
    pub fn body(&self) -> Option<&ErrorBody> {
        match self {
            Self::Request(b)
            | Self::GuardrailBlocked(b)
            | Self::Authentication(b)
            | Self::Credit(b)
            | Self::NotFound(b)
            | Self::RateLimit(b)
            | Self::Service(b)
            | Self::Other(b) => Some(b),
            Self::Transport(_) => None,
        }
    }

    /// Whether retrying the identical request could plausibly succeed.
    ///
    /// Deliberately false for every 4xx that names a permanent condition: a
    /// retry there burns quota and cannot change the answer.
    pub fn is_retryable(&self) -> bool {
        matches!(self, Self::RateLimit(_) | Self::Service(_) | Self::Transport(_))
    }
}

impl fmt::Display for NRouterError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Transport(m) => write!(f, "nRouter transport error: {m}"),
            other => {
                let b = other.body().expect("non-transport variants carry a body");
                match &b.code {
                    Some(code) => write!(f, "{} ({code})", b.message),
                    None => write!(f, "{}", b.message),
                }
            }
        }
    }
}

impl std::error::Error for NRouterError {}
