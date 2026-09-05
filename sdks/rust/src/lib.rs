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
pub mod media;
pub mod memory;
pub mod meta;
pub mod options;
pub mod prompts;
pub mod sampling;

pub use errors::{
    compute_jittered_backoff, parse_retry_after, parse_retry_after_at, ErrorBody, NRouterError,
    MAX_RETRY_AFTER_SECONDS,
};
pub use media::{validate_audio_format, VALID_AUDIO_FORMATS};
pub use memory::{sliding_window, ArrayStore, ChatMessage, Memory, MemoryStore};
pub use meta::{BudgetWarningInfo, ResponseMeta, HEADER_NAMES};
pub use prompts::{render_prompt, RenderPromptOptions};

/// True when a model family is served on /v1/messages rather than /v1/chat/completions.
pub fn uses_messages_wire(model: &str, provider: Option<&str>) -> bool {
    let m = model.to_ascii_lowercase();
    if m.contains("claude")
        || m.contains("anthropic")
        || m.contains("haiku")
        || m.contains("sonnet")
        || m.contains("opus")
    {
        return true;
    }
    if let Some(p) = provider {
        if p.to_ascii_lowercase().contains("anthropic") {
            return true;
        }
    }
    false
}

use async_openai::{config::OpenAIConfig, middleware::ReqwestService, Client as OpenAIClient};

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
    client_with_key_and_base_url(api_key, DEFAULT_BASE_URL)
}

/// An `async-openai` client pointed at an explicit nRouter gateway.
///
/// The public facade uses the same finite connect and between-bytes deadlines
/// as [`http::Client`]. Its executor is a bare [`ReqwestService`], deliberately
/// excluding `async-openai`'s default retry layer: the gateway already owns a
/// single three-attempt provider budget, while replaying a billed customer
/// `POST` here creates a new reservation and can charge the customer twice.
pub fn client_with_key_and_base_url(
    api_key: &str,
    base_url: &str,
) -> Result<OpenAIClient<OpenAIConfig>, NRouterError> {
    client_with_key_base_url_and_http_client(
        api_key,
        base_url,
        http::Client::default_http_client()?,
    )
}

/// The public `async-openai` facade over a caller-supplied HTTP transport.
///
/// Supplying the transport customizes proxy, pool and deadlines. It does not
/// restore automatic retries: every billed request still gets one SDK attempt.
pub fn client_with_key_base_url_and_http_client(
    api_key: &str,
    base_url: &str,
    transport: reqwest::Client,
) -> Result<OpenAIClient<OpenAIConfig>, NRouterError> {
    let key = resolve_api_key(Some(api_key))?;
    let config = OpenAIConfig::new()
        .with_api_key(key)
        .with_api_base(base_url.trim_end_matches('/'));
    // `build` installs the bounded client in the request factory; the service
    // installs the same client in the executor while omitting its retry layer.
    Ok(OpenAIClient::build(transport.clone(), config)
        .with_http_service(ReqwestService::new(transport)))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_uses_messages_wire() {
        assert!(uses_messages_wire("claude-3-5-sonnet-20241022", None));
        assert!(uses_messages_wire("anthropic/claude-3-haiku", None));
        assert!(uses_messages_wire("custom-model", Some("anthropic")));
        assert!(!uses_messages_wire("gpt-4o", None));
        assert!(!uses_messages_wire("llama-3", Some("meta")));
    }
}
