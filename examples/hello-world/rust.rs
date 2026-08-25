// nRouter — Rust hello world
// Cargo.toml:
//   async-openai = "0.25"
//   tokio = { version = "1", features = ["full"] }

use async_openai::{
    config::OpenAIConfig,
    types::{ChatCompletionRequestUserMessageArgs, CreateChatCompletionRequestArgs},
    Client,
};

#[tokio::main]
async fn main() {
    let config = OpenAIConfig::new()
        .with_api_key(std::env::var("NROUTER_API_KEY").expect("NROUTER_API_KEY not set"))
        .with_api_base("https://api.nrouter.ai/v1");

    let client = Client::with_config(config);

    let request = CreateChatCompletionRequestArgs::default()
        .model("claude-sonnet-4-5")
        .messages(vec![ChatCompletionRequestUserMessageArgs::default()
            .content("Hello, nRouter!")
            .build()
            .unwrap()
            .into()])
        .build()
        .unwrap();

    let response = client.chat().create(request).await.unwrap();
    println!("{}", response.choices[0].message.content.as_ref().unwrap());
}
