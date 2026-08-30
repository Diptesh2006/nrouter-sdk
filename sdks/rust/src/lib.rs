//! nRouter SDK for Rust — one API key for models across six provider clouds.
//!
//! Two entry points, deliberately:
//!
//! * [`client`] returns an [`async_openai`] client pointed at the gateway, so
//!   every OpenAI-shaped call you already write keeps working unmodified.
//! * [`http::Client`] is a native client that hands back the `x-nr-*`
//!   metadata — per-request cost, tokens, cache outcome — which the
//!   `async-openai` surface cannot expose because it discards the raw response.
//!
//! ```no_run
//! # async fn example() -> Result<(), Box<dyn std::error::Error>> {
//! use async_openai::types::chat::{
//!     ChatCompletionRequestUserMessageArgs, CreateChatCompletionRequestArgs,
//! };
//!
//! let client = nrouter::client()?; // reads NROUTER_API_KEY
//! let request = CreateChatCompletionRequestArgs::default()
//!     .model("claude-sonnet-4-5")
//!     .messages(vec![ChatCompletionRequestUserMessageArgs::default()
//!         .content("Hello!")
//!         .build()?
//!         .into()])
//!     .build()?;
//! let response = client.chat().create(request).await?;
//! println!("{}", response.choices[0].message.content.as_ref().unwrap());
//! # Ok(())
//! # }
//! ```
//!
//! Reading the cost of a call:
//!
//! ```no_run
//! # async fn example() -> Result<(), Box<dyn std::error::Error>> {
//! use serde_json::json;
//!
//! let client = nrouter::http::Client::from_env()?;
//! let out = client
//!     .chat_completions(&json!({
//!         "model": "claude-sonnet-4-5",
//!         "messages": [{"role": "user", "content": "Hello!"}]
//!     }))
//!     .await?;
//!
//! match out.meta.cost {
//!     Some(usd) => println!("cost ${usd}"),
//!     // Unpriced is not free — it is unknown. Never render it as 0.
//!     None => println!("unpriced ({:?})", out.meta.cost_status),
//! }
//! # Ok(())
//! # }
//! ```

#![forbid(unsafe_code)]

pub mod errors;
pub mod http;
pub mod memory;
pub mod meta;
pub mod options;
pub mod prompts;
pub mod sampling;

pub use errors::{ErrorBody, NRouterError};
pub use meta::{ResponseMeta, HEADER_NAMES};

use async_openai::{config::OpenAIConfig, Client as OpenAIClient};

/// The gateway's customer surface. A dynamic value: override it for stage.
pub const DEFAULT_BASE_URL: &str = "https://api.nrouter.ai/v1";
/// The one environment variable this SDK reads.
pub const ENV_KEY: &str = "NROUTER_API_KEY";
/// Every customer key carries this prefix.
pub const KEY_PREFIX: &str = "sk-nrouter-";

/// Resolve and validate a key: explicit argument first, then the environment.
///
/// Validation happens before any request so a malformed key fails locally
/// rather than as a 401 that looks like a revoked credential.
pub fn resolve_api_key(explicit: Option<&str>) -> Result<String, NRouterError> {
    let key = match explicit {
        Some(k) if !k.is_empty() => k.to_string(),
        _ => std::env::var(ENV_KEY).unwrap_or_default(),
    };
    if key.is_empty() {
        return Err(NRouterError::Configuration(format!(
            "No nRouter API key: pass one explicitly or set {ENV_KEY}."
        )));
    }
    if !key.starts_with(KEY_PREFIX) {
        return Err(NRouterError::Configuration(format!(
            "nRouter API keys start with '{KEY_PREFIX}'; got one that does not."
        )));
    }
    Ok(key)
}

/// An `async-openai` client pointed at nRouter, keyed from `NROUTER_API_KEY`.
pub fn client() -> Result<OpenAIClient<OpenAIConfig>, NRouterError> {
    client_with_key(&resolve_api_key(None)?)
}

/// An `async-openai` client pointed at nRouter with an explicit key.
pub fn client_with_key(api_key: &str) -> Result<OpenAIClient<OpenAIConfig>, NRouterError> {
    let key = resolve_api_key(Some(api_key))?;
    let config = OpenAIConfig::new()
        .with_api_key(key)
        .with_api_base(DEFAULT_BASE_URL);
    Ok(OpenAIClient::with_config(config))
}
