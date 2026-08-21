# nrouter (Rust)

OpenAI-compatible SDK for the [nRouter](https://nrouter.ai) LLM gateway. A thin wrapper
around the `async-openai` crate — same API surface, pre-configured for nRouter.

## Install

```toml
[dependencies]
nrouter = "1.0.0"
tokio = { version = "1", features = ["full"] }
```

## Usage

```rust
use async_openai::types::{ChatCompletionRequestUserMessageArgs, CreateChatCompletionRequestArgs};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let client = nrouter::client()?; // reads NROUTER_API_KEY from env

    let request = CreateChatCompletionRequestArgs::default()
        .model("claude-sonnet-4-20250514")
        .messages(vec![ChatCompletionRequestUserMessageArgs::default()
            .content("Hello!")
            .build()?
            .into()])
        .build()?;

    let response = client.chat().create(request).await?;
    println!("{}", response.choices[0].message.content.as_ref().unwrap());
    Ok(())
}
```

`nrouter::client()` returns a real `async_openai::Client<OpenAIConfig>`, so every
resource `async-openai` supports works unmodified.

## Basic only, for now

This is a minimal wrapper: API key resolution/validation (`sk-nrouter-...`) and a
default API base of `https://api.nrouter.ai/v1`. It doesn't yet have the typed errors,
automatic cost-header capture, or `credits`/`guardrails`/`prompts` namespaces that
[`sdks/python/`](../python/) has — see that package for the fuller pattern this one will
grow into.
