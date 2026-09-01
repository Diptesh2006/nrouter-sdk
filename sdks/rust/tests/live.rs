//! BILLED acceptance probes. Every test here reaches a real gateway, a real
//! provider and a real credit balance.
//!
//! # Why every test is `#[ignore]` rather than an early `return`
//!
//! These used to open with `if env::var("NROUTER_LIVE") != Ok("1") { return; }`.
//! An early return is a PASS to libtest, so `cargo test` printed
//! `live_claude_stream_reaches_the_configured_gateway ... ok` on a machine with
//! no key, no gateway and no credits — release evidence that could not
//! distinguish a probe that ran from one that never executed a line. Rust's
//! standard harness has no runtime skip status, so the honest signal is the one
//! it does have: `ignored`, decided before the test body runs.
//!
//! ```text
//! cargo test --test live                  # every probe reports `ignored`
//! cargo test --test live -- --ignored     # runs them; needs the env below
//! ```
//!
//! # And why the env guard is a PANIC, not a return
//!
//! Once `--ignored` is passed the caller has asked for the billed probes. A
//! missing variable at that point is a misconfigured live run, not a reason to
//! report `ok` — so [`require`] panics and names the variable. Non-execution can
//! be `ignored` or a failure; it can never be a pass.
//!
//! # The route-family matrix
//!
//! Claude-through-`/v1/messages` was the only live acceptance in this repo, so
//! the wires customers actually reported broken — OpenAI chat completions,
//! `/v1/responses`, and an opaque alias whose provider is not inferable from its
//! name — were outside live evidence entirely. They are separate tests with
//! separate model variables because a model is servable on the wires ITS
//! provider declares and no others: one model cannot certify the matrix, and a
//! single test that tried would fail for a reason that is not a defect.

use nrouter::http::{Client, Response};
use serde_json::{json, Value};

/// The value of `name`, or a panic naming it.
///
/// Reached only under `--ignored`, where the caller has already asked for a
/// billed run — see the module header.
fn require(name: &str) -> String {
    std::env::var(name).unwrap_or_else(|_| {
        panic!(
            "{name} is required for a live probe. Set NROUTER_LIVE=1, \
             NROUTER_API_KEY, and the per-wire model variables, then run \
             `cargo test --test live -- --ignored`."
        )
    })
}

/// A client pointed at the gateway under test.
fn live_client() -> Client {
    assert_eq!(
        require("NROUTER_LIVE"),
        "1",
        "NROUTER_LIVE must be exactly \"1\" for a billed probe"
    );
    let base_url =
        std::env::var("NROUTER_BASE_URL").unwrap_or_else(|_| nrouter::DEFAULT_BASE_URL.to_string());
    Client::from_env()
        .expect("NROUTER_API_KEY must hold a live sk-nrouter- key")
        .with_base_url(base_url)
}

/// Every response must carry `x-nr-request-id`: it is the only handle a customer
/// has at support and the join key for the spend row this call just wrote.
fn assert_correlatable(response: &Response<Value>, wire: &str) {
    assert!(
        response
            .meta
            .request_id
            .as_deref()
            .is_some_and(|id| !id.is_empty()),
        "{wire} answered without x-nr-request-id"
    );
}

/// The `/v1/*` paths `GET /v1/models` says this alias can be called on.
///
/// The gateway renders `nrouter_endpoints` from the provider's own endpoint
/// declaration, so this is the discovery answer an SDK is supposed to use
/// instead of guessing a wire from the model name.
fn advertised_endpoints(catalogue: &Value, model: &str) -> Vec<String> {
    let entry = catalogue["data"]
        .as_array()
        .expect("GET /v1/models returns a data array")
        .iter()
        .find(|item| item["id"] == model)
        .unwrap_or_else(|| panic!("{model} is not in this key's catalogue"));
    entry["nrouter_endpoints"]
        .as_array()
        .unwrap_or_else(|| panic!("{model} carries no nrouter_endpoints"))
        .iter()
        .filter_map(|path| path.as_str().map(str::to_owned))
        .collect()
}

#[tokio::test]
#[ignore = "billed: run with `cargo test --test live -- --ignored`"]
async fn live_claude_stream_reaches_the_configured_gateway() {
    let client = live_client();
    let model = std::env::var("NROUTER_LIVE_MESSAGES_MODEL")
        .unwrap_or_else(|_| "claude-haiku-4-5-20251001".to_owned());
    let mut stream = client
        .messages_stream(&json!({
            "model": model,
            "max_tokens": 2,
            "messages": [{"role": "user", "content": "Reply OK"}]
        }))
        .await
        .expect("open live stream");
    let mut text = String::new();
    while let Some(chunk) = stream.next().await.expect("read live stream") {
        text.push_str(&chunk.delta);
    }
    assert!(!text.is_empty());
    assert!(stream
        .meta
        .request_id
        .as_deref()
        .is_some_and(|id| !id.is_empty()));
}

#[tokio::test]
#[ignore = "billed: run with `cargo test --test live -- --ignored`"]
async fn live_openai_chat_completions_wire_answers() {
    let client = live_client();
    let model = require("NROUTER_LIVE_CHAT_MODEL");
    let response = client
        .chat_completions(&json!({
            "model": model,
            "max_tokens": 2,
            "messages": [{"role": "user", "content": "Reply OK"}]
        }))
        .await
        .expect("/v1/chat/completions must answer for a chat-wire model");
    assert!(
        response.body["choices"].is_array(),
        "/v1/chat/completions returned no choices array"
    );
    assert_correlatable(&response, "/v1/chat/completions");
}

#[tokio::test]
#[ignore = "billed: run with `cargo test --test live -- --ignored`"]
async fn live_responses_wire_answers() {
    let client = live_client();
    let model = require("NROUTER_LIVE_RESPONSES_MODEL");
    let response = client
        .responses(&json!({
            "model": model,
            "input": "Reply OK",
            "max_output_tokens": 16
        }))
        .await
        .expect("/v1/responses must answer for a Responses-wire model");
    assert!(
        !response.body.is_null(),
        "/v1/responses returned a null document"
    );
    assert_correlatable(&response, "/v1/responses");
}

/// An alias whose provider a client cannot infer from the name — a Bedrock GLM
/// or a Gemma alias — must still be callable, and the wire must come from
/// discovery rather than from a guess.
///
/// This is the one probe that proves the matrix is DERIVABLE: it reads the
/// endpoints out of `GET /v1/models` and then calls the wire it was told about.
/// An alias listed with an endpoint it cannot serve fails here.
#[tokio::test]
#[ignore = "billed: run with `cargo test --test live -- --ignored`"]
async fn live_opaque_alias_is_callable_on_the_wire_discovery_advertises() {
    let client = live_client();
    let model = require("NROUTER_LIVE_OPAQUE_MODEL");
    let catalogue = client.models().await.expect("GET /v1/models must answer");
    assert_correlatable(&catalogue, "/v1/models");
    let endpoints = advertised_endpoints(&catalogue.body, &model);
    assert!(
        !endpoints.is_empty(),
        "{model} is listed with an empty nrouter_endpoints — the catalogue \
         advertises a name no wire serves"
    );

    let body = json!({
        "model": model,
        "max_tokens": 2,
        "messages": [{"role": "user", "content": "Reply OK"}]
    });
    let response = if endpoints.iter().any(|path| path == "/v1/chat/completions") {
        client.chat_completions(&body).await
    } else if endpoints.iter().any(|path| path == "/v1/messages") {
        client.messages(&body).await
    } else {
        panic!("{model} advertises no text wire: {endpoints:?}");
    }
    .unwrap_or_else(|error| {
        panic!("{model} advertises {endpoints:?} but the call failed: {error}")
    });
    assert_correlatable(&response, "the discovered text wire");
}
