use nrouter::http::Client;
use serde_json::json;

#[tokio::main]
async fn main() {
    let client = Client::from_env().expect("Set NROUTER_API_KEY before running.");
    let response = client
        .chat_completions(&json!({
            "model": "typesafe/jev",
            "temperature": 0,
            "max_tokens": 128,
            "messages": [
                {"role": "system", "content": "Classify the incident. Return JSON only with priority, queue, and summary."},
                {"role": "user", "content": "Production payment requests return HTTP 500 in two regions."}
            ]
        }))
        .await
        .expect("nRouter request failed");

    println!("Decision: {}", response.body["choices"][0]["message"]["content"]);
    println!("Request ID: {:?}", response.meta.request_id);
    println!("Served model: {:?}", response.meta.model);
    match response.meta.cost {
        Some(cost) => println!("Exact cost: ${cost:.6}"),
        None => println!("Cost status: {:?}", response.meta.cost_status),
    }
}
