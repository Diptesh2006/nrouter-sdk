//! Per-request metadata carried on nRouter response headers.
//!
//! Every field is optional on purpose. The gateway omits a header rather than
//! sending a placeholder, and the two that matter most are omissions:
//! `x-nr-request-cost` is ABSENT when the model is unpriced — never `0` — and
//! `x-nr-limit-source` is absent when nothing measured the refusal.

/// Metadata from the `x-nr-*` headers of one response.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct ResponseMeta {
    /// Present on every response; the join key for a spend row or a log line.
    pub request_id: Option<String>,
    /// Exact USD cost. `None` when unpriced — treating that as `0.0` would
    /// report a free request, which no enabled model is.
    pub cost: Option<f64>,
    /// `exact` or `unpriced`.
    pub cost_status: Option<String>,
    pub model: Option<String>,
    pub input_tokens: Option<u64>,
    pub output_tokens: Option<u64>,
    pub total_tokens: Option<u64>,
    pub cache_read_tokens: Option<u64>,
    pub cache_write_tokens: Option<u64>,
    /// On a 429, which limit measured the refusal.
    pub limit_source: Option<String>,
    /// Set when this request crossed a soft budget you configured; it still
    /// served. `<scope> soft_budget <spend>/<ceiling>`, e.g.
    /// `org soft_budget 80.00/100.00`.
    pub budget_warning: Option<String>,
    /// Posture of the PRE-CALL guardrail chain: `none`, `monitor`, `pass`,
    /// `partial` or `blocked`, matched exactly and case-sensitively.
    ///
    /// `None` means the gateway made NO guardrail claim about this response —
    /// never "no guardrail applied", which is the explicit `none`. Posture only
    /// by design: policy name, policy id, detector family, rule count and (for
    /// `partial`) which channel went uninspected are deliberately withheld.
    pub guardrails: Option<String>,
    /// On a 401, the gateway's stable reason.
    pub auth_reason: Option<String>,
    /// `hit` or `miss`; absent when the response cache did not participate.
    pub response_cache: Option<String>,
    /// Age in seconds of a response-cache hit.
    pub response_cache_age: Option<u64>,
}

/// Every header this SDK reads, exactly as the spec names them.
pub const HEADER_NAMES: [&str; 15] = [
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
];

impl ResponseMeta {
    /// Parse from anything that can look a header up by lowercase name.
    ///
    /// An unparseable numeric header yields `None` rather than a default: a
    /// zero here would be indistinguishable from a real zero.
    pub fn from_lookup<F>(get: F) -> Self
    where
        F: Fn(&str) -> Option<String>,
    {
        let num = |name: &str| get(name).and_then(|v| v.parse::<u64>().ok());
        Self {
            request_id: get("x-nr-request-id"),
            cost: get("x-nr-request-cost").and_then(|v| v.parse::<f64>().ok()),
            cost_status: get("x-nr-cost-status"),
            model: get("x-nr-model"),
            input_tokens: num("x-nr-input-tokens"),
            output_tokens: num("x-nr-output-tokens"),
            total_tokens: num("x-nr-total-tokens"),
            cache_read_tokens: num("x-nr-cache-read-tokens"),
            cache_write_tokens: num("x-nr-cache-write-tokens"),
            limit_source: get("x-nr-limit-source"),
            budget_warning: get("x-nr-budget-warning"),
            guardrails: get("x-nr-guardrails"),
            auth_reason: get("x-nr-auth-reason"),
            response_cache: get("x-nr-response-cache"),
            response_cache_age: num("x-nr-response-cache-age"),
        }
    }

    /// Parse from a `reqwest`/`http` header map.
    pub fn from_headers(headers: &reqwest::header::HeaderMap) -> Self {
        Self::from_lookup(|name| {
            headers
                .get(name)
                .and_then(|v| v.to_str().ok())
                .map(str::to_owned)
        })
    }

    /// True when the gateway priced this request exactly.
    pub fn is_priced(&self) -> bool {
        self.cost_status.as_deref() == Some("exact") && self.cost.is_some()
    }

    /// True when the response came from the nRouter response cache.
    pub fn is_cache_hit(&self) -> bool {
        self.response_cache.as_deref() == Some("hit")
    }

    /// True when the response was a cache miss.
    pub fn is_cache_miss(&self) -> bool {
        self.response_cache.as_deref() == Some("miss")
    }

    /// Parses structured budget warning information if present.
    pub fn parse_budget_warning(&self) -> Option<BudgetWarningInfo> {
        let warning = self.budget_warning.as_deref()?.trim();
        let parts: Vec<&str> = warning.split_whitespace().collect();
        if parts.len() != 3 || parts[1] != "soft_budget" {
            return None;
        }
        let amounts: Vec<&str> = parts[2].split('/').collect();
        if amounts.len() != 2 {
            return None;
        }
        let spend = amounts[0].parse::<f64>().ok()?;
        let ceiling = amounts[1].parse::<f64>().ok()?;
        Some(BudgetWarningInfo {
            scope: parts[0].to_string(),
            spend,
            ceiling,
        })
    }
}

/// Structured details from an `x-nr-budget-warning` header.
#[derive(Debug, Clone, PartialEq)]
pub struct BudgetWarningInfo {
    pub scope: String,
    pub spend: f64,
    pub ceiling: f64,
}
