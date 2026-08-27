//! Request-path tests against a one-shot server built from `std::net`.
//!
//! No mock-server crate on purpose: a dev-dependency here would be a build cost
//! on every consumer's `cargo test` for behaviour a 40-line listener covers.

use std::io::{Read, Write};
use std::net::TcpListener;
use std::sync::mpsc;
use std::thread;

use nrouter::{http::Client, NRouterError};
use serde_json::json;

/// Serve exactly one request, return what the client sent.
///
/// The captured request is returned through a channel rather than a shared
/// mutex so a test cannot read it before the server has finished writing.
fn serve_once(status: u16, content_type: &str, body: &str) -> (String, mpsc::Receiver<String>) {
    let listener = TcpListener::bind("127.0.0.1:0").expect("bind");
    let addr = listener.local_addr().expect("addr");
    let (tx, rx) = mpsc::channel();
    let response = format!(
        "HTTP/1.1 {status} OK\r\nContent-Type: {content_type}\r\nContent-Length: {}\r\n\
         x-nr-request-id: req_42\r\nx-nr-request-cost: 0.00042\r\nx-nr-cost-status: exact\r\n\
         Connection: close\r\n\r\n{body}",
        body.len()
    );

    thread::spawn(move || {
        if let Ok((mut stream, _)) = listener.accept() {
            let mut buf = vec![0u8; 65536];
            let read = stream.read(&mut buf).unwrap_or(0);
            let _ = tx.send(String::from_utf8_lossy(&buf[..read]).to_string());
            let _ = stream.write_all(response.as_bytes());
            let _ = stream.flush();
        }
    });

    (format!("http://{addr}/v1"), rx)
}

fn client(base: &str) -> Client {
    Client::new("sk-nrouter-test")
        .expect("client")
        .with_base_url(base)
}

#[tokio::test]
async fn a_call_carries_the_key_and_returns_the_gateway_metadata() {
    let (base, rx) = serve_once(200, "application/json", r#"{"choices":[]}"#);
    let out = client(&base)
        .chat_completions(&json!({"model": "claude-sonnet-4-5"}))
        .await
        .expect("ok");

    let sent = rx.recv().expect("request");
    assert!(sent.contains("POST /v1/chat/completions"), "{sent}");
    assert!(
        sent.contains("authorization: Bearer sk-nrouter-test"),
        "{sent}"
    );
    assert_eq!(out.meta.request_id.as_deref(), Some("req_42"));
    assert_eq!(out.meta.cost, Some(0.00042));
    assert!(out.meta.is_priced());
}

#[tokio::test]
async fn a_non_json_2xx_refuses_rather_than_reporting_an_empty_success() {
    // /v1/audio/speech returns audio. Parsed as JSON it becomes Null — the
    // caller is BILLED and receives nothing, while the call reports 200.
    let (base, _rx) = serve_once(200, "audio/mpeg", "ID3binary-audio");
    let err = client(&base)
        .post("/audio/speech", &json!({}))
        .await
        .expect_err("must refuse");
    match err {
        NRouterError::Transport(m) => assert!(m.contains("bytes()"), "{m}"),
        other => panic!("expected Transport, got {other:?}"),
    }
}

#[tokio::test]
async fn a_malformed_json_2xx_is_a_failure_not_an_empty_success() {
    let (base, _rx) = serve_once(200, "application/json", r#"{"choices":[{"#);
    let err = client(&base)
        .chat_completions(&json!({}))
        .await
        .expect_err("must refuse");
    match err {
        NRouterError::Transport(m) => assert!(m.contains("billed"), "{m}"),
        other => panic!("expected Transport, got {other:?}"),
    }
}

#[tokio::test]
async fn bytes_returns_the_raw_body_a_non_json_endpoint_sent() {
    let (base, _rx) = serve_once(200, "audio/mpeg", "binary-audio");
    let out = client(&base)
        .bytes("POST", "/audio/speech", Some(&json!({})))
        .await
        .expect("ok");
    assert_eq!(String::from_utf8_lossy(&out.body), "binary-audio");
    assert_eq!(out.meta.request_id.as_deref(), Some("req_42"));
}

#[tokio::test]
async fn audio_transcriptions_sends_multipart_with_a_named_file_part() {
    // The gateway requires multipart/form-data with a binary `file` here; sent
    // as JSON the endpoint is unreachable.
    let (base, rx) = serve_once(200, "application/json", r#"{"text":"hello"}"#);
    let out = client(&base)
        .audio_transcriptions(
            b"fake-audio".to_vec(),
            "speech.mp3",
            &[("model", "whisper-1")],
        )
        .await
        .expect("ok");

    let sent = rx.recv().expect("request");
    assert!(sent.contains("multipart/form-data"), "{sent}");
    assert!(sent.contains(r#"name="file""#), "no file part: {sent}");
    // The extension is load-bearing: providers pick their decoder from it.
    assert!(sent.contains("speech.mp3"), "file name not sent: {sent}");
    assert!(sent.contains(r#"name="model""#), "no model field: {sent}");
    assert_eq!(out.body["text"], "hello");
}

#[tokio::test]
async fn a_codeless_guardrail_400_raises_the_guardrail_variant() {
    // Byte-for-byte the gateway's real envelope: type + message, NO code.
    let (base, _rx) = serve_once(
        400,
        "application/json",
        r#"{"error":{"type":"gateway_error","message":"blocked by guardrail 'pii'"}}"#,
    );
    let err = client(&base)
        .chat_completions(&json!({}))
        .await
        .expect_err("must refuse");
    assert!(
        matches!(err, NRouterError::GuardrailBlocked(_)),
        "got {err:?}"
    );
    assert!(!err.is_retryable());
}
