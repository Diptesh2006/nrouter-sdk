//! A native client that can SEE the `x-nr-*` headers.
//!
//! `async-openai` gives the ergonomic OpenAI surface but hides the raw
//! response, so per-request cost, token counts and cache outcome are
//! unreachable through it. This client exists for exactly that: it speaks the
//! same OpenAI wire format and hands back the body together with
//! [`ResponseMeta`].

use serde_json::Value;

use crate::errors::{ErrorBody, NRouterError};
use crate::meta::ResponseMeta;
use crate::{resolve_api_key, DEFAULT_BASE_URL};

/// A response body paired with the metadata the gateway reported for it.
#[derive(Debug, Clone)]
pub struct Response<T> {
    pub body: T,
    pub meta: ResponseMeta,
}

/// Thin nRouter HTTP client over the OpenAI wire format.
#[derive(Debug, Clone)]
pub struct Client {
    api_key: String,
    base_url: String,
    http: reqwest::Client,
}

impl Client {
    /// Build a client, reading `NROUTER_API_KEY` from the environment.
    pub fn from_env() -> Result<Self, NRouterError> {
        Self::new(resolve_api_key(None)?)
    }

    /// Build a client with an explicit key. The key is validated up front so a
    /// malformed one fails here rather than as a 401 after a network round trip.
    pub fn new(api_key: impl Into<String>) -> Result<Self, NRouterError> {
        Ok(Self {
            api_key: resolve_api_key(Some(&api_key.into()))?,
            base_url: DEFAULT_BASE_URL.to_string(),
            http: reqwest::Client::new(),
        })
    }

    /// Point the client at a different gateway (stage, or a local run).
    pub fn with_base_url(mut self, base_url: impl Into<String>) -> Self {
        self.base_url = base_url.into().trim_end_matches('/').to_string();
        self
    }

    /// Override the underlying HTTP client — proxy, timeout, connection pool.
    pub fn with_http_client(mut self, http: reqwest::Client) -> Self {
        self.http = http;
        self
    }

    pub fn base_url(&self) -> &str {
        &self.base_url
    }

    /// `POST /chat/completions`.
    pub async fn chat_completions(&self, body: &Value) -> Result<Response<Value>, NRouterError> {
        self.post("/chat/completions", body).await
    }

    /// `POST /embeddings`.
    pub async fn embeddings(&self, body: &Value) -> Result<Response<Value>, NRouterError> {
        self.post("/embeddings", body).await
    }

    /// `POST /messages` — the Anthropic wire format the gateway also serves.
    pub async fn messages(&self, body: &Value) -> Result<Response<Value>, NRouterError> {
        self.post("/messages", body).await
    }

    /// `POST /responses`.
    pub async fn responses(&self, body: &Value) -> Result<Response<Value>, NRouterError> {
        self.post("/responses", body).await
    }

    /// `GET /models` — what this key is allowed to route to.
    pub async fn models(&self) -> Result<Response<Value>, NRouterError> {
        self.get("/models").await
    }

    /// Any `POST` path under the gateway's `/v1` root.
    pub async fn post(&self, path: &str, body: &Value) -> Result<Response<Value>, NRouterError> {
        let req = self
            .http
            .post(self.url(path))
            .bearer_auth(&self.api_key)
            .json(body);
        self.send(req).await
    }

    /// Any `GET` path under the gateway's `/v1` root.
    pub async fn get(&self, path: &str) -> Result<Response<Value>, NRouterError> {
        let req = self.http.get(self.url(path)).bearer_auth(&self.api_key);
        self.send(req).await
    }

    fn url(&self, path: &str) -> String {
        format!("{}/{}", self.base_url, path.trim_start_matches('/'))
    }

    async fn send(&self, req: reqwest::RequestBuilder) -> Result<Response<Value>, NRouterError> {
        let response = req
            .send()
            .await
            .map_err(|e| NRouterError::Transport(e.to_string()))?;

        let status = response.status().as_u16();
        let meta = ResponseMeta::from_headers(response.headers());
        let body: Value = response.json().await.unwrap_or(Value::Null);

        if (200..300).contains(&status) {
            return Ok(Response { body, meta });
        }
        Err(NRouterError::from_code(error_body(status, &body, &meta)))
    }
}

/// Pull the gateway's stable `code` and message out of an error payload.
///
/// The gateway nests them under `error`; a bare object is accepted too so a
/// proxy that reshapes the envelope does not turn a typed error into a generic
/// one.
fn error_body(status: u16, body: &Value, meta: &ResponseMeta) -> ErrorBody {
    let node = body.get("error").unwrap_or(body);
    ErrorBody {
        message: node
            .get("message")
            .and_then(Value::as_str)
            .unwrap_or("nRouter request failed")
            .to_string(),
        code: node
            .get("code")
            .and_then(Value::as_str)
            .map(str::to_owned),
        status: Some(status),
        request_id: meta.request_id.clone(),
        limit_source: meta.limit_source.clone(),
        auth_reason: meta.auth_reason.clone(),
        retry_after: None,
    }
}
