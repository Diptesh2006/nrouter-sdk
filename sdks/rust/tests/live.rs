use nrouter::http::Client;
use serde_json::json;

#[tokio::test]
async fn live_claude_stream_reaches_the_configured_gateway() {
    if std::env::var("NROUTER_LIVE").as_deref() != Ok("1") {
        return;
    }
    let base_url = std::env::var("NROUTER_BASE_URL")
        .unwrap_or_else(|_| nrouter::DEFAULT_BASE_URL.to_string());
    let client = Client::from_env().expect("configured key").with_base_url(base_url);
    let mut stream = client
        .messages_stream(&json!({
            "model": "claude-haiku-4-5-20251001",
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
    assert!(stream.meta.request_id.as_deref().is_some_and(|id| !id.is_empty()));
}
