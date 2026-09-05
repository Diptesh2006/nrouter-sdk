//! The gateway contract this SDK must keep, asserted against the values in
//! `spec/nrouter-sdk-spec.json`. These are the assertions that make "the
//! gateway works across every SDK" checkable rather than asserted.

use nrouter::errors::{ErrorBody, NRouterError};
use nrouter::meta::{BudgetWarningInfo, ResponseMeta, HEADER_NAMES};
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
    assert_eq!(HEADER_NAMES.len(), 15);
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
        "x-nr-budget-warning",
        "x-nr-guardrails",
    ] {
        assert!(
            HEADER_NAMES.contains(&name),
            "{name} is not read by this SDK"
        );
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
            NRouterError::BudgetExceeded(_) => "BudgetExceeded",
            NRouterError::NotFound(_) => "NotFound",
            NRouterError::RateLimit(_) => "RateLimit",
            NRouterError::Service(_) => "Service",
            NRouterError::Other(_) => "Other",
            NRouterError::Transport(_) => "Transport",
            NRouterError::Configuration(_) => "Configuration",
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
    // A local configuration failure is PERMANENT. Marking it retryable makes a
    // caller's retry loop spin forever without ever making a request.
    assert!(!NRouterError::Configuration("no key".into()).is_retryable());

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
        "x-nr-budget-warning" => Some("org soft_budget 80.00/100.00".into()),
        "x-nr-guardrails" => Some("pass".into()),
        _ => None,
    });
    assert_eq!(meta.cost, Some(0.00042));
    assert!(meta.is_priced());
    assert!(meta.is_cache_hit());
    assert!(!meta.is_cache_miss());
    assert_eq!(meta.input_tokens, Some(11));
    assert_eq!(meta.output_tokens, Some(22));
    assert_eq!(meta.response_cache.as_deref(), Some("hit"));
    assert_eq!(meta.response_cache_age, Some(7));
    assert_eq!(
        meta.budget_warning.as_deref(),
        Some("org soft_budget 80.00/100.00")
    );
    let parsed_warning = meta.parse_budget_warning();
    assert_eq!(
        parsed_warning,
        Some(BudgetWarningInfo {
            scope: "org".into(),
            spend: 80.0,
            ceiling: 100.0,
        })
    );
    assert_eq!(meta.guardrails.as_deref(), Some("pass"));
}

#[test]
fn a_key_without_the_prefix_is_refused_before_any_request() {
    assert!(matches!(
        resolve_api_key(Some("sk-openai-nope")),
        Err(NRouterError::Configuration(_))
    ));
    assert!(resolve_api_key(Some("")).is_err() || std::env::var(ENV_KEY).is_ok());
    assert_eq!(
        resolve_api_key(Some("sk-nrouter-abc")).unwrap(),
        "sk-nrouter-abc"
    );
}

#[test]
fn a_codeless_400_is_split_on_the_message() {
    // The gateway's main error path emits {"error":{"type","message"}} with NO
    // code, so this is the ordinary shape — not an edge case. Classifying every
    // codeless 400 as a request error makes GuardrailBlocked unreachable and
    // tells a caller to fix a body that was never the problem.
    let guardrail = ErrorBody {
        message: "blocked by guardrail 'pii'".into(),
        code: None,
        status: Some(400),
        ..Default::default()
    };
    assert!(matches!(
        NRouterError::from_code(guardrail),
        NRouterError::GuardrailBlocked(_)
    ));

    let malformed = ErrorBody {
        message: "invalid request: messages must be an array".into(),
        code: None,
        status: Some(400),
        ..Default::default()
    };
    assert!(matches!(
        NRouterError::from_code(malformed),
        NRouterError::Request(_)
    ));
}

#[test]
fn a_code_still_wins_over_the_status_when_the_gateway_sends_one() {
    // The WAF and the upstream passthrough do send a code; it must beat the
    // status, since status alone cannot separate the two 429s.
    let body = ErrorBody {
        message: "slow down".into(),
        code: Some("tpm_limit_exceeded".into()),
        status: Some(429),
        ..Default::default()
    };
    match NRouterError::from_code(body) {
        NRouterError::RateLimit(b) => assert_eq!(b.code.as_deref(), Some("tpm_limit_exceeded")),
        other => panic!("expected RateLimit, got {other:?}"),
    }
}

#[test]
fn a_codeless_status_the_sdk_does_not_know_stays_other() {
    let body = ErrorBody {
        message: "teapot".into(),
        code: None,
        status: Some(418),
        ..Default::default()
    };
    assert!(matches!(
        NRouterError::from_code(body),
        NRouterError::Other(_)
    ));
}

#[test]
fn a_codeless_402_separates_a_budget_ceiling_from_a_shortfall() {
    // Three conditions share 402 and two are budget ceilings, whose fix is the
    // OPPOSITE of a shortfall's. Telling a customer whose budget is exhausted
    // to top up is a wrong answer delivered confidently.
    let budget = ErrorBody {
        message: "budget exceeded: spend 5.00 of max_budget 5.00".into(),
        code: None,
        status: Some(402),
        ..Default::default()
    };
    assert!(matches!(
        NRouterError::from_code(budget),
        NRouterError::BudgetExceeded(_)
    ));

    let shortfall = ErrorBody {
        message: "insufficient credits: 0.01 available, 0.50 required".into(),
        code: None,
        status: Some(402),
        ..Default::default()
    };
    assert!(matches!(
        NRouterError::from_code(shortfall),
        NRouterError::Credit(_)
    ));
}

#[test]
fn a_codeless_404_is_only_model_not_found_when_it_names_a_model() {
    let model = ErrorBody {
        message: "model 'gpt-9' not found".into(),
        code: None,
        status: Some(404),
        ..Default::default()
    };
    assert!(matches!(
        NRouterError::from_code(model),
        NRouterError::NotFound(_)
    ));

    // A missing video job or MCP server is also a 404. Calling it
    // `model_not_found` is a wrong answer with a confident code on it.
    let other = ErrorBody {
        message: "unknown video job 'vid_123'".into(),
        code: None,
        status: Some(404),
        ..Default::default()
    };
    assert!(matches!(
        NRouterError::from_code(other),
        NRouterError::Other(_)
    ));
}

#[test]
fn debug_never_prints_the_api_key() {
    // A derived Debug prints `api_key` verbatim, so one `{:?}` in a caller's
    // log leaks a credential that spends real credits (Rule #5).
    let client = nrouter::http::Client::new("sk-nrouter-SECRET123").unwrap();
    let rendered = format!("{client:?}");
    assert!(
        !rendered.contains("SECRET123"),
        "the api key leaked into Debug: {rendered}"
    );
    assert!(rendered.contains("sk-nrouter-...T123"), "{rendered}");
}

#[test]
fn parse_retry_after_accepts_delta_seconds_and_http_date() {
    let now = 1770000000u64;
    assert_eq!(nrouter::parse_retry_after_at(Some("120"), now), Some(120));
    assert_eq!(nrouter::parse_retry_after_at(Some("0"), now), Some(0));
    assert_eq!(nrouter::parse_retry_after_at(Some("  45  "), now), Some(45));
    assert_eq!(
        nrouter::parse_retry_after_at(Some("9999999999"), now),
        Some(nrouter::MAX_RETRY_AFTER_SECONDS)
    );
    assert_eq!(nrouter::parse_retry_after_at(None, now), None);
    assert_eq!(nrouter::parse_retry_after_at(Some(""), now), None);
    assert_eq!(nrouter::parse_retry_after_at(Some("invalid"), now), None);

    // IMF-fixdate future
    // 1770000000 corresponds to: 2026-02-02 02:40:00 GMT
    // +60s = 2026-02-02 02:41:00 GMT (Monday)
    assert_eq!(
        nrouter::parse_retry_after_at(Some("Mon, 02 Feb 2026 02:41:00 GMT"), now),
        Some(60)
    );

    // Past date clamps to 0
    assert_eq!(
        nrouter::parse_retry_after_at(Some("Mon, 02 Feb 2026 02:30:00 GMT"), now),
        Some(0)
    );
}
