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
    /// `insufficient_credits` (402) — the credit reserve failed. Top up.
    Credit(Box<ErrorBody>),
    /// A BUDGET ceiling (402), not a shortfall.
    ///
    /// Three conditions share 402 and two are budget ceilings, whose fix is the
    /// OPPOSITE of a credit shortfall's: raise the budget, not top up. Telling
    /// a customer whose budget is exhausted to add money is a wrong answer
    /// delivered confidently.
    BudgetExceeded(Box<ErrorBody>),
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
                // The gateway's own wording is the only discriminator it gives
                // us, and it is stable: GatewayError::{BudgetExceeded,
                // ScopedBudgetExceeded} both start their Display with "budget".
                Some(402) => {
                    if body
                        .message
                        .trim_start()
                        .to_lowercase()
                        .starts_with("budget")
                    {
                        Self::BudgetExceeded(body)
                    } else {
                        Self::Credit(body)
                    }
                }
                // Scoped to MODELS. A 404 is also a missing video job, an
                // unknown MCP server or an unknown agent run; calling those
                // `model_not_found` is a wrong answer with a confident stable
                // code on it. Anything unidentifiable stays Other.
                Some(404) => {
                    if body.message.to_lowercase().contains("model") {
                        Self::NotFound(body)
                    } else {
                        Self::Other(body)
                    }
                }
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
            | Self::BudgetExceeded(b)
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
        if let Some(body) = self.body() {
            if matches!(body.status, Some(408) | Some(425)) {
                return true;
            }
        }
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

/// Maximum allowable backoff in seconds (24 hours).
pub const MAX_RETRY_AFTER_SECONDS: u64 = 86400;

/// Parses an RFC 9110 Retry-After header value (delta-seconds or HTTP-date).
pub fn parse_retry_after(raw: Option<&str>) -> Option<u64> {
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    parse_retry_after_at(raw, now)
}

/// Parses an RFC 9110 Retry-After header value relative to a given epoch timestamp in seconds.
pub fn parse_retry_after_at(raw: Option<&str>, now_epoch: u64) -> Option<u64> {
    let raw = raw?.trim();
    if raw.is_empty() {
        return None;
    }
    if let Ok(seconds) = raw.parse::<u64>() {
        return Some(seconds.min(MAX_RETRY_AFTER_SECONDS));
    }
    parse_http_date(raw).map(|epoch| {
        if epoch <= now_epoch {
            0
        } else {
            (epoch - now_epoch).min(MAX_RETRY_AFTER_SECONDS)
        }
    })
}

/// Computes a bounded jittered exponential backoff duration.
///
/// Honors `retry_after_seconds` when present and > 0, bounded by `max_delay`.
/// Clamps `attempt` to 30 to prevent arithmetic overflow on `2^attempt`.
/// Jitter spreads backoff between 50% and 100% of the computed window.
pub fn compute_jittered_backoff(
    attempt: u32,
    base_delay: std::time::Duration,
    max_delay: std::time::Duration,
    retry_after_seconds: Option<u64>,
) -> std::time::Duration {
    let attempt = attempt.min(30);
    if let Some(ra) = retry_after_seconds {
        if ra > 0 {
            let retry_dur = std::time::Duration::from_secs(ra).min(max_delay);
            let nanos = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.subsec_nanos())
                .unwrap_or(0);
            let factor = 0.5 + 0.5 * ((nanos % 1000) as f64 / 1000.0);
            return std::time::Duration::from_secs_f64(retry_dur.as_secs_f64() * factor);
        }
    }

    let mult = 1u64 << attempt;
    let raw = base_delay.saturating_mul(mult as u32);
    let capped = raw.min(max_delay);
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.subsec_nanos())
        .unwrap_or(0);
    let factor = 0.5 + 0.5 * ((nanos % 1000) as f64 / 1000.0);
    std::time::Duration::from_secs_f64(capped.as_secs_f64() * factor)
}

fn parse_http_date(s: &str) -> Option<u64> {
    let parts: Vec<&str> = s.split_whitespace().collect();
    if parts.len() != 6 {
        return None;
    }
    if !parts[0].ends_with(',') {
        return None;
    }
    let day: u32 = parts[1].parse().ok()?;
    let month: u32 = match parts[2].to_ascii_lowercase().as_str() {
        "jan" => 1,
        "feb" => 2,
        "mar" => 3,
        "apr" => 4,
        "may" => 5,
        "jun" => 6,
        "jul" => 7,
        "aug" => 8,
        "sep" => 9,
        "oct" => 10,
        "nov" => 11,
        "dec" => 12,
        _ => return None,
    };
    let year: i64 = parts[3].parse().ok()?;
    if year < 1970 {
        return None;
    }
    let time_parts: Vec<&str> = parts[4].split(':').collect();
    if time_parts.len() != 3 {
        return None;
    }
    let hour: u32 = time_parts[0].parse().ok()?;
    let min: u32 = time_parts[1].parse().ok()?;
    let sec: u32 = time_parts[2].parse().ok()?;
    if hour > 23 || min > 59 || sec > 60 || day == 0 || day > 31 {
        return None;
    }
    let days = days_from_civil(year, month, day)?;
    let total_secs = days as u64 * 86400 + hour as u64 * 3600 + min as u64 * 60 + sec as u64;
    Some(total_secs)
}

fn days_from_civil(y: i64, m: u32, d: u32) -> Option<i64> {
    let mut y = y;
    if m <= 2 {
        y -= 1;
    }
    let era = if y >= 0 { y } else { y - 399 } / 400;
    let yoe = (y - era * 400) as u32;
    let m_adj = if m > 2 { m - 3 } else { m + 9 };
    let doy = (153 * m_adj + 2) / 5 + d - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    let days = era * 146097 + doe as i64 - 719468;
    if days >= 0 {
        Some(days)
    } else {
        None
    }
}
