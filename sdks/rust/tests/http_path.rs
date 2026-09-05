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
            // Read until the whole request is in hand. A single read() takes
            // only the first TCP segment, so a multipart body split across
            // segments would be captured half-formed — the assertions would
            // flake, and replying early can reset the connection while the
            // client is still writing.
            let mut raw: Vec<u8> = Vec::new();
            let mut chunk = [0u8; 8192];
            loop {
                let n = match stream.read(&mut chunk) {
                    Ok(0) | Err(_) => break,
                    Ok(n) => n,
                };
                raw.extend_from_slice(&chunk[..n]);

                // Headers complete?
                let Some(head_end) = find(&raw, b"\r\n\r\n") else {
                    continue;
                };
                let head = String::from_utf8_lossy(&raw[..head_end]).to_lowercase();
                let want: usize = head
                    .lines()
                    .find_map(|l| l.strip_prefix("content-length:"))
                    .and_then(|v| v.trim().parse().ok())
                    .unwrap_or(0);
                if raw.len() >= head_end + 4 + want {
                    break;
                }
            }

            let _ = tx.send(String::from_utf8_lossy(&raw).to_string());
            let _ = stream.write_all(response.as_bytes());
            let _ = stream.flush();
        }
    });

    (format!("http://{addr}/v1"), rx)
}

/// First index of `needle` in `haystack`.
fn find(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    haystack
        .windows(needle.len())
        .position(|window| window == needle)
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
async fn messages_stream_yields_anthropic_delta_and_forces_stream_true() {
    let body = concat!(
        "event: content_block_delta\n",
        "data: {\"type\":\"content_block_delta\",\"delta\":{\"type\":\"text_delta\",\"text\":\"Claude\"}}\n\n",
        "event: message_stop\n",
        "data: {\"type\":\"message_stop\"}\n\n"
    );
    let (base, rx) = serve_once(200, "text/event-stream", body);
    let original = json!({"model": "claude"});
    let mut stream = client(&base)
        .messages_stream(&original)
        .await
        .expect("open stream");
    assert_eq!(stream.meta.request_id.as_deref(), Some("req_42"));
    let mut text = String::new();
    while let Some(chunk) = stream.next().await.expect("stream frame") {
        text.push_str(&chunk.delta);
    }
    assert_eq!(text, "Claude");
    assert!(original.get("stream").is_none(), "caller body was mutated");
    let sent = rx.recv().expect("request");
    assert!(sent.contains("POST /v1/messages"), "{sent}");
    assert!(sent.contains("\"stream\":true"), "{sent}");
}

#[tokio::test]
async fn stream_guardrail_event_is_a_typed_failure() {
    let body = concat!(
        "event: error\n",
        "data: {\"error\":{\"type\":\"guardrail_blocked\",\"message\":\"the response was withheld by an output guardrail\"}}\n\n"
    );
    let (base, _rx) = serve_once(200, "text/event-stream", body);
    let mut stream = client(&base)
        .messages_stream(&json!({}))
        .await
        .expect("open stream");
    let err = stream.next().await.expect_err("must refuse");
    assert!(matches!(err, NRouterError::GuardrailBlocked(_)), "{err:?}");
    assert_eq!(
        err.body().and_then(|b| b.request_id.as_deref()),
        Some("req_42")
    );
}

#[tokio::test]
async fn stream_handles_keepalive_cr_boundaries_and_trailing_event() {
    let body = concat!(
        ": keep-alive\r\r",
        "data: ping\r\r",
        "data: {\"choices\":[{\"delta\":{\"content\":\"  def foo():\"}}]}\n\n",
        "data: [DONE]"
    );
    let (base, _rx) = serve_once(200, "text/event-stream", body);
    let mut stream = client(&base)
        .chat_completions_stream(&json!({}))
        .await
        .expect("open stream");
    let chunk = stream.next().await.expect("ok").expect("chunk");
    assert_eq!(chunk.delta, "  def foo():");
    let term = stream.next().await.expect("ok");
    assert!(term.is_none());
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
async fn named_helpers_cover_every_remaining_gateway_operation() {
    macro_rules! assert_body_call {
        ($method:ident, $expected:literal) => {{
            let (base, rx) = serve_once(200, "application/json", r#"{}"#);
            client(&base).$method(&json!({})).await.expect("ok");
            let sent = rx.recv().expect("request");
            assert!(sent.contains($expected), "{sent}");
        }};
    }

    macro_rules! assert_id_call {
        ($method:ident, $id:literal, $expected:literal) => {{
            let (base, rx) = serve_once(200, "application/json", r#"{}"#);
            client(&base).$method($id).await.expect("ok");
            let sent = rx.recv().expect("request");
            assert!(sent.contains($expected), "{sent}");
        }};
    }

    assert_body_call!(completions, "POST /v1/completions");
    assert_body_call!(images_generations, "POST /v1/images/generations");
    assert_body_call!(count_tokens, "POST /v1/messages/count_tokens");
    assert_id_call!(
        model,
        "provider/model one",
        "GET /v1/models/provider/model%20one"
    );
    assert_body_call!(create_video, "POST /v1/videos");
    assert_id_call!(retrieve_video, "video/one", "GET /v1/videos/video%2Fone");

    let (base, rx) = serve_once(200, "audio/mpeg", "audio");
    client(&base)
        .audio_speech(&json!({}))
        .await
        .expect("audio speech");
    assert!(rx
        .recv()
        .expect("request")
        .contains("POST /v1/audio/speech"));

    let (base, rx) = serve_once(200, "video/mp4", "video");
    client(&base)
        .download_video_content("video/one")
        .await
        .expect("video content");
    assert!(rx
        .recv()
        .expect("request")
        .contains("GET /v1/videos/video%2Fone/content"));
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

// --- transport deadlines ----------------------------------------------------
//
// `reqwest::Client::new()` sets no timeout of any kind, so a gateway that
// accepts the connection and then goes silent hangs the caller forever. These
// pin the replacement: the between-bytes deadline fires, a long body is NOT cut
// by it (which is what a whole-request `.timeout()` would do to SSE and to
// `GET /videos/{id}/content`), and `with_http_client` still wins outright.

/// Read one whole HTTP request off the socket — headers, then `Content-Length`
/// bytes. A single `read()` takes only the first segment, and replying early
/// can reset the connection while the client is still writing.
fn read_full_request(stream: &mut std::net::TcpStream) -> Vec<u8> {
    let mut raw: Vec<u8> = Vec::new();
    let mut chunk = [0u8; 8192];
    loop {
        let n = match stream.read(&mut chunk) {
            Ok(0) | Err(_) => break,
            Ok(n) => n,
        };
        raw.extend_from_slice(&chunk[..n]);
        let Some(head_end) = find(&raw, b"\r\n\r\n") else {
            continue;
        };
        let head = String::from_utf8_lossy(&raw[..head_end]).to_lowercase();
        let want: usize = head
            .lines()
            .find_map(|l| l.strip_prefix("content-length:"))
            .and_then(|v| v.trim().parse().ok())
            .unwrap_or(0);
        if raw.len() >= head_end + 4 + want {
            break;
        }
    }
    raw
}

/// A gateway that accepted the connection and then said nothing.
fn serve_after_silence(silence: std::time::Duration) -> String {
    let listener = TcpListener::bind("127.0.0.1:0").expect("bind");
    let addr = listener.local_addr().expect("addr");
    thread::spawn(move || {
        if let Ok((mut stream, _)) = listener.accept() {
            let _ = read_full_request(&mut stream);
            thread::sleep(silence);
            let _ = stream.write_all(
                b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\
                  Connection: close\r\n\r\n{}",
            );
            let _ = stream.flush();
        }
    });
    format!("http://{addr}/v1")
}

/// Headers immediately, then a body that trickles: each gap is short, the TOTAL
/// is long. Exactly the shape of a stream and of a large download.
fn serve_dribbled_body(chunks: usize, gap: std::time::Duration) -> String {
    let listener = TcpListener::bind("127.0.0.1:0").expect("bind");
    let addr = listener.local_addr().expect("addr");
    thread::spawn(move || {
        if let Ok((mut stream, _)) = listener.accept() {
            let _ = read_full_request(&mut stream);
            let head = format!(
                "HTTP/1.1 200 OK\r\nContent-Type: video/mp4\r\nContent-Length: {chunks}\r\n\
                 x-nr-request-id: req_42\r\nConnection: close\r\n\r\n"
            );
            let _ = stream.write_all(head.as_bytes());
            let _ = stream.flush();
            for _ in 0..chunks {
                thread::sleep(gap);
                let _ = stream.write_all(b"x");
                let _ = stream.flush();
            }
        }
    });
    format!("http://{addr}/v1")
}

#[tokio::test]
async fn a_gateway_that_says_nothing_is_cut_at_the_read_timeout() {
    let base = serve_after_silence(std::time::Duration::from_secs(5));
    // The shipped constructor, one deadline shortened — so this proves the real
    // mechanism rather than a test-only lookalike.
    let http = Client::http_client_with(
        Client::DEFAULT_CONNECT_TIMEOUT,
        std::time::Duration::from_millis(150),
    )
    .expect("client");
    let client = Client::new("sk-nrouter-test")
        .expect("client")
        .with_base_url(&base)
        .with_http_client(http);

    let started = std::time::Instant::now();
    let err = client
        .chat_completions(&json!({"model": "claude"}))
        .await
        .expect_err("a silent gateway must not hang the caller");
    let elapsed = started.elapsed();

    assert!(
        matches!(err, NRouterError::Transport(_)),
        "want a transport failure, got {err:?}"
    );
    assert!(
        elapsed < std::time::Duration::from_secs(3),
        "waited {elapsed:?}; the read deadline never fired"
    );
}

#[tokio::test]
async fn a_body_slower_in_total_than_the_read_timeout_is_not_cut() {
    // Eight 80 ms gaps = ~640 ms of body against a 300 ms BETWEEN-BYTES
    // deadline. It completes only because no whole-request `.timeout()` is set:
    // one of 300 ms would sever it, already billed.
    const CHUNKS: usize = 8;
    let base = serve_dribbled_body(CHUNKS, std::time::Duration::from_millis(80));
    let http = Client::http_client_with(
        Client::DEFAULT_CONNECT_TIMEOUT,
        std::time::Duration::from_millis(300),
    )
    .expect("client");
    let client = Client::new("sk-nrouter-test")
        .expect("client")
        .with_base_url(&base)
        .with_http_client(http);

    let out = client
        .bytes("GET", "/videos/v_1/content", None)
        .await
        .expect("a trickling download must not be cut");
    assert_eq!(
        String::from_utf8_lossy(&out.body),
        "x".repeat(CHUNKS),
        "the download was truncated"
    );
}

#[tokio::test]
async fn the_default_client_names_its_deadlines_and_sets_no_whole_request_timeout() {
    assert!(
        !Client::DEFAULT_CONNECT_TIMEOUT.is_zero(),
        "an unnamed connect deadline is infinity"
    );
    assert!(
        !Client::DEFAULT_READ_TIMEOUT.is_zero(),
        "an unnamed read deadline is infinity"
    );
    // Above the gateway's ~410 s worst honest time-to-first-byte: three provider
    // attempts x (10 s connect + 120 s silence) plus 20 s of cumulative backoff.
    // Below that, the SDK aborts a request the gateway is about to answer — and
    // the customer is billed for it anyway.
    assert!(
        Client::DEFAULT_READ_TIMEOUT >= std::time::Duration::from_secs(410),
        "read deadline {:?} is under the gateway's worst honest case",
        Client::DEFAULT_READ_TIMEOUT
    );

    // `reqwest`'s Debug prints a deadline only when it is SET, which makes both
    // halves of the design assertable on the real default client: the
    // between-bytes deadline is present, and the whole-request one — which would
    // sever streaming — is absent. (It does not render `connect_timeout`; that
    // one is covered by the constant above plus the single shared constructor,
    // which is also what `a_gateway_that_says_nothing_is_cut_at_the_read_timeout`
    // exercises.)
    let rendered = format!("{:?}", Client::default_http_client().expect("client"));
    assert!(
        rendered.contains("read_timeout"),
        "no read deadline on the default client — it would wait forever: {rendered}"
    );
    assert!(
        !rendered.contains(" timeout:"),
        "the default client carries a whole-request timeout, which cuts streaming: {rendered}"
    );
}

#[tokio::test]
async fn with_http_client_fully_overrides_the_default_deadlines() {
    let base = serve_after_silence(std::time::Duration::from_secs(5));
    // A whole-request timeout the SDK deliberately does not set. If the override
    // is total, this cuts the call; if the default leaked through, the call
    // would sit on the 600 s read deadline instead.
    let custom = reqwest::Client::builder()
        .timeout(std::time::Duration::from_millis(150))
        .build()
        .expect("custom client");
    let client = Client::new("sk-nrouter-test")
        .expect("client")
        .with_base_url(&base)
        .with_http_client(custom);

    let started = std::time::Instant::now();
    let err = client
        .chat_completions(&json!({}))
        .await
        .expect_err("the caller's timeout must apply");
    assert!(
        matches!(err, NRouterError::Transport(_)),
        "want a transport failure, got {err:?}"
    );
    assert!(
        started.elapsed() < std::time::Duration::from_secs(3),
        "the caller's client was not in force"
    );
}

#[test]
fn compute_jittered_backoff_bounds() {
    let base = std::time::Duration::from_millis(1000);
    let max = std::time::Duration::from_millis(10000);

    // Exponential bounds
    let d0 = nrouter::compute_jittered_backoff(0, base, max, None);
    assert!(
        d0 >= std::time::Duration::from_millis(500) && d0 <= std::time::Duration::from_millis(1000)
    );

    let d2 = nrouter::compute_jittered_backoff(2, base, max, None);
    assert!(
        d2 >= std::time::Duration::from_millis(2000)
            && d2 <= std::time::Duration::from_millis(4000)
    );

    // Attempt capping prevents overflow
    let dhuge =
        nrouter::compute_jittered_backoff(100, base, std::time::Duration::from_millis(8000), None);
    assert!(
        dhuge >= std::time::Duration::from_millis(4000)
            && dhuge <= std::time::Duration::from_millis(8000)
    );

    // Retry-After precedence
    let d_retry = nrouter::compute_jittered_backoff(0, base, max, Some(5));
    assert!(
        d_retry >= std::time::Duration::from_millis(2500)
            && d_retry <= std::time::Duration::from_millis(5000)
    );

    // Retry-After capped by max_delay
    let d_retry_capped = nrouter::compute_jittered_backoff(
        0,
        base,
        std::time::Duration::from_millis(4000),
        Some(20),
    );
    assert!(
        d_retry_capped >= std::time::Duration::from_millis(2000)
            && d_retry_capped <= std::time::Duration::from_millis(4000)
    );
}
