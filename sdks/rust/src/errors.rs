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
#[allow(clippy::large_enum_variant)] // every payload variant is boxed below
pub enum NRouterError {
    /// `invalid_request` (400) — invalid JSON or request shape.
    Request(Box<ErrorBody>),
    /// `guardrail_blocked` (400) — a guardrail rule denied the request.
    GuardrailBlocked(Box<ErrorBody>),
    /// `invalid_api_key` (401) — virtual-key authentication refused.
    Authentication(Box<ErrorBody>),
    /// `insufficient_credits` (402) — the credit reserve failed.
    Credit(Box<ErrorBody>),
    /// `model_not_found` (404) — alias absent or invisible to this tenant.
    NotFound(Box<ErrorBody>),
    /// `rate_limit_exceeded` / `tpm_limit_exceeded` (429).
    RateLimit(Box<ErrorBody>),
    /// `credit_check_failed` / `service_unavailable` (503).
    Service(Box<ErrorBody>),
    /// A code this SDK version does not know. Never re-classified.
    Other(Box<ErrorBody>),
    /// The request left this process and did not get an answer — DNS, TLS, a
    /// dropped connection, a timeout. Retryable.
    Transport(String),
    /// The SDK refused before sending anything: no key, or a key that is not
    /// shaped like an nRouter key.
    ///
    /// Separate from [`NRouterError::Transport`] on purpose. Both are raised
    /// locally, but this one is PERMANENT — a caller retrying on
    /// `is_retryable()` would spin forever without ever making a request.
    Configuration(String),
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
    /// Classify a gateway refusal.
    ///
    /// Three signals, in order, because no single one is sufficient:
    ///
    /// 1. **`code`**, when present — the only thing that separates
    ///    `rate_limit_exceeded` from `tpm_limit_exceeded`. The gateway's WAF
    ///    and its upstream passthrough send one.
    /// 2. **status**, otherwise. The gateway's main error path
    ///    (`GatewayError::into_response`) emits `{"error":{"type","message"}}`
    ///    with **no code at all**, so this is the ordinary case, not the
    ///    fallback it looks like.
    /// 3. **the message**, to split the two 400s. `invalid_request` and
    ///    `guardrail_blocked` share a status, and with no code the message is
    ///    the only signal present — classifying every 400 as a request error
    ///    would make [`NRouterError::GuardrailBlocked`] unreachable, telling a
    ///    caller to fix a body that was never the problem.
    pub fn from_code(body: ErrorBody) -> Self {
        let boxed = Box::new(body);
        let body = boxed;
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
                Some(400) => {
                    if body.message.to_lowercase().contains("guardrail") {
                        Self::GuardrailBlocked(body)
                    } else {
                        Self::Request(body)
                    }
                }
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
            Self::Transport(_) | Self::Configuration(_) => None,
        }
    }

    /// Whether retrying the identical request could plausibly succeed.
    ///
    /// Deliberately false for every 4xx that names a permanent condition: a
    /// retry there burns quota and cannot change the answer.
    pub fn is_retryable(&self) -> bool {
        matches!(
            self,
            Self::RateLimit(_) | Self::Service(_) | Self::Transport(_)
        )
    }
}

impl fmt::Display for NRouterError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Transport(m) => write!(f, "nRouter transport error: {m}"),
            Self::Configuration(m) => write!(f, "nRouter configuration error: {m}"),
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
