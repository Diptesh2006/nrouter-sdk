//! The gateway contract this SDK must keep, asserted against the values in
//! `spec/nrouter-sdk-spec.json`. These are the assertions that make "the
//! gateway works across every SDK" checkable rather than asserted.

use nrouter::errors::{ErrorBody, NRouterError};
use nrouter::meta::{ResponseMeta, HEADER_NAMES};
use nrouter::{resolve_api_key, DEFAULT_BASE_URL, ENV_KEY, KEY_PREFIX};

fn body(code: &str) -> ErrorBody {
    ErrorBody {
        message: "boom".into(),
        code: Some(code.into()),
        status: None,
        ..Default::default()
    }
}

#[test]
fn constants_match_the_spec() {
    assert_eq!(DEFAULT_BASE_URL, "https://api.nrouter.ai/v1");
    assert_eq!(ENV_KEY, "NROUTER_API_KEY");
    assert_eq!(KEY_PREFIX, "sk-nrouter-");
}

#[test]
fn every_spec_header_is_read() {
    assert_eq!(HEADER_NAMES.len(), 13);
    for name in [
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
        "x-nr-auth-reason",
        "x-nr-response-cache",
        "x-nr-response-cache-age",
    ] {
        assert!(HEADER_NAMES.contains(&name), "{name} is not read by this SDK");
    }
}

#[test]
fn each_gateway_code_maps_to_its_variant() {
    for (code, want) in [
        ("invalid_request", "Request"),
        ("guardrail_blocked", "GuardrailBlocked"),
        ("invalid_api_key", "Authentication"),
        ("insufficient_credits", "Credit"),
        ("model_not_found", "NotFound"),
        ("rate_limit_exceeded", "RateLimit"),
        ("tpm_limit_exceeded", "RateLimit"),
        ("credit_check_failed", "Service"),
        ("service_unavailable", "Service"),
    ] {
        let got = match NRouterError::from_code(body(code)) {
            NRouterError::Request(_) => "Request",
            NRouterError::GuardrailBlocked(_) => "GuardrailBlocked",
            NRouterError::Authentication(_) => "Authentication",
            NRouterError::Credit(_) => "Credit",
            NRouterError::NotFound(_) => "NotFound",
            NRouterError::RateLimit(_) => "RateLimit",
            NRouterError::Service(_) => "Service",
            NRouterError::Other(_) => "Other",
            NRouterError::Transport(_) => "Transport",
        };
        assert_eq!(got, want, "code {code} mapped to {got}, expected {want}");
    }
}

#[test]
fn an_unknown_code_is_never_reclassified() {
    // Forcing an unrecognised code into a neighbouring variant is how a caller
    // is told to retry something permanent.
    assert!(matches!(
        NRouterError::from_code(body("some_future_code")),
        NRouterError::Other(_)
    ));
}

#[test]
fn only_transient_failures_are_retryable() {
    assert!(NRouterError::from_code(body("rate_limit_exceeded")).is_retryable());
    assert!(NRouterError::from_code(body("service_unavailable")).is_retryable());
    assert!(NRouterError::Transport("dns".into()).is_retryable());

    for permanent in [
        "invalid_request",
        "guardrail_blocked",
        "invalid_api_key",
        "insufficient_credits",
        "model_not_found",
    ] {
        assert!(
            !NRouterError::from_code(body(permanent)).is_retryable(),
            "{permanent} must not be advertised as retryable"
        );
    }
}

#[test]
fn an_unpriced_response_reports_no_cost_rather_than_zero() {
    let meta = ResponseMeta::from_lookup(|n| match n {
        "x-nr-cost-status" => Some("unpriced".into()),
        "x-nr-request-id" => Some("req_1".into()),
        _ => None,
    });
    assert_eq!(meta.cost, None, "unpriced must not become a number");
    assert!(!meta.is_priced());
    assert_eq!(meta.request_id.as_deref(), Some("req_1"));
}

#[test]
fn a_priced_response_parses_its_numbers() {
    let meta = ResponseMeta::from_lookup(|n| match n {
        "x-nr-request-cost" => Some("0.00042".into()),
        "x-nr-cost-status" => Some("exact".into()),
        "x-nr-input-tokens" => Some("11".into()),
        "x-nr-output-tokens" => Some("22".into()),
        "x-nr-response-cache" => Some("hit".into()),
        "x-nr-response-cache-age" => Some("7".into()),
        _ => None,
    });
    assert_eq!(meta.cost, Some(0.00042));
    assert!(meta.is_priced());
    assert_eq!(meta.input_tokens, Some(11));
    assert_eq!(meta.output_tokens, Some(22));
    assert_eq!(meta.response_cache.as_deref(), Some("hit"));
    assert_eq!(meta.response_cache_age, Some(7));
}

#[test]
fn a_key_without_the_prefix_is_refused_before_any_request() {
    assert!(resolve_api_key(Some("sk-openai-nope")).is_err());
    assert!(resolve_api_key(Some("")).is_err() || std::env::var(ENV_KEY).is_ok());
    assert_eq!(
        resolve_api_key(Some("sk-nrouter-abc")).unwrap(),
        "sk-nrouter-abc"
    );
}
