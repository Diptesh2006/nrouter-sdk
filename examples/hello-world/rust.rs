// nRouter — Rust hello world
// Cargo.toml:
//   nrouter = "2.1"
//   serde_json = "1"
//   tokio = { version = "1", features = ["full"] }

use nrouter::http::Client;
use serde_json::json;

#[tokio::main]
async fn main() {
    let client = Client::from_env().expect("NROUTER_API_KEY not set");
    // A Smart Router alias activates its strategy/fallback chain; a concrete
    // model id pins the request to that model.
    let model = std::env::var("NROUTER_MODEL")
        .unwrap_or_else(|_| "claude-sonnet-4-5-20250929".to_string());
    let response = client.chat_completions(&json!({
        "model": model,
        "messages": [{"role": "user", "content": "Hello, nRouter!"}]
    })).await.unwrap();
    println!("{}", response.body["choices"][0]["message"]["content"]);
    println!("request {:?}, cost {:?}", response.meta.request_id, response.meta.cost);
}
