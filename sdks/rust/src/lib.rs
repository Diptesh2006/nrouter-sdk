//! nRouter client — thin wrapper around the `async-openai` crate.
//!
//! ```no_run
//! # async fn example() -> Result<(), Box<dyn std::error::Error>> {
//! use async_openai::types::{ChatCompletionRequestUserMessageArgs, CreateChatCompletionRequestArgs};
//!
//! let client = nrouter::client()?; // reads NROUTER_API_KEY from env
//!
//! let request = CreateChatCompletionRequestArgs::default()
//!     .model("claude-sonnet-4-5")
//!     .messages(vec![ChatCompletionRequestUserMessageArgs::default()
//!         .content("Hello!")
//!         .build()?
//!         .into()])
//!     .build()?;
//!
//! let response = client.chat().create(request).await?;
//! println!("{}", response.choices[0].message.content.as_ref().unwrap());
//! # Ok(())
//! # }
//! ```

use async_openai::{config::OpenAIConfig, Client};

const DEFAULT_BASE_URL: &str = "https://api.nrouter.ai/v1";
const ENV_KEY: &str = "NROUTER_API_KEY";
const KEY_PREFIX: &str = "sk-nrouter-";

/// Build a client using the `NROUTER_API_KEY` environment variable.
pub fn client() -> Result<Client<OpenAIConfig>, String> {
    let api_key = std::env::var(ENV_KEY)
        .map_err(|_| format!("{} is not set; pass a key to client_with_key() instead.", ENV_KEY))?;
    client_with_key(&api_key)
}

/// Build a client with an explicit API key.
pub fn client_with_key(api_key: &str) -> Result<Client<OpenAIConfig>, String> {
    if !api_key.starts_with(KEY_PREFIX) {
        return Err(format!(
            "nRouter API keys must start with '{}'; pass a valid key or set {}.",
            KEY_PREFIX, ENV_KEY
        ));
    }
    let config = OpenAIConfig::new()
        .with_api_key(api_key)
        .with_api_base(DEFAULT_BASE_URL);
    Ok(Client::with_config(config))
}
