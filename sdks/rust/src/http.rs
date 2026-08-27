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

    /// `POST /audio/transcriptions` — Whisper-style speech to text.
    ///
    /// multipart/form-data, not JSON: the gateway requires a binary `file` part
    /// here, so the JSON helpers cannot reach this endpoint at all.
    ///
    /// `file_name` must carry the real extension — the upstream providers pick
    /// their decoder from it, so `"audio"` is rejected where `"speech.mp3"` is
    /// not.
    pub async fn audio_transcriptions(
        &self,
        file: Vec<u8>,
        file_name: &str,
        fields: &[(&str, &str)],
    ) -> Result<Response<Value>, NRouterError> {
        self.multipart("/audio/transcriptions", file, file_name, fields)
            .await
    }

    /// `POST /audio/translations` — speech in any language to English text.
    pub async fn audio_translations(
        &self,
        file: Vec<u8>,
        file_name: &str,
        fields: &[(&str, &str)],
    ) -> Result<Response<Value>, NRouterError> {
        self.multipart("/audio/translations", file, file_name, fields)
            .await
    }

    /// Any multipart `POST` under the gateway's `/v1` root.
    pub async fn multipart(
        &self,
        path: &str,
        file: Vec<u8>,
        file_name: &str,
        fields: &[(&str, &str)],
    ) -> Result<Response<Value>, NRouterError> {
        let mut form = reqwest::multipart::Form::new();
        for (key, value) in fields {
            form = form.text((*key).to_string(), (*value).to_string());
        }
        let part = reqwest::multipart::Part::bytes(file).file_name(file_name.to_string());
        form = form.part("file", part);

        let req = self
            .http
            .post(self.url(path))
            .bearer_auth(&self.api_key)
            .multipart(form);
        self.send(req).await
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

    /// Raw bytes plus metadata, for the endpoints that do not return JSON.
    ///
    /// `/v1/audio/speech` returns audio, `/v1/videos/{id}/content` returns a
    /// video, and `stream: true` returns SSE. The JSON helpers refuse those
    /// rather than handing back an empty body for a request you were billed
    /// for; this is the method that returns them.
    pub async fn bytes(
        &self,
        method: &str,
        path: &str,
        body: Option<&Value>,
    ) -> Result<Response<Vec<u8>>, NRouterError> {
        let mut req = match method.to_ascii_uppercase().as_str() {
            "GET" => self.http.get(self.url(path)),
            _ => self.http.post(self.url(path)),
        }
        .bearer_auth(&self.api_key);
        if let Some(json) = body {
            req = req.json(json);
        }

        let response = req
            .send()
            .await
            .map_err(|e| NRouterError::Transport(e.to_string()))?;
        let status = response.status().as_u16();
        let meta = ResponseMeta::from_headers(response.headers());
        let retry_after = response
            .headers()
            .get(reqwest::header::RETRY_AFTER)
            .and_then(|v| v.to_str().ok())
            .and_then(|v| v.trim().parse::<u64>().ok());
        let raw = response
            .bytes()
            .await
            .map_err(|e| NRouterError::Transport(e.to_string()))?;

        if (200..300).contains(&status) {
            return Ok(Response {
                body: raw.to_vec(),
                meta,
            });
        }
        let parsed: Value = serde_json::from_slice(&raw).unwrap_or(Value::Null);
        Err(NRouterError::from_code(error_body(
            status,
            &parsed,
            &meta,
            retry_after,
        )))
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
        // Read Retry-After BEFORE consuming the body — `response.json()` takes
        // ownership, and the header is unreachable afterwards. That is why this
        // field used to be hard-coded to None.
        let retry_after = response
            .headers()
            .get(reqwest::header::RETRY_AFTER)
            .and_then(|v| v.to_str().ok())
            .and_then(|v| v.trim().parse::<u64>().ok());
        let content_type = response
            .headers()
            .get(reqwest::header::CONTENT_TYPE)
            .and_then(|v| v.to_str().ok())
            .unwrap_or("")
            .to_ascii_lowercase();
        let bytes = response
            .bytes()
            .await
            .map_err(|e| NRouterError::Transport(e.to_string()))?;

        if (200..300).contains(&status) {
            // A 2xx that is not JSON is a REAL RESPONSE the caller was billed
            // for — `/v1/audio/speech` returns audio, video content returns
            // bytes, and `stream: true` returns SSE. Parsing those as JSON
            // yields an empty object, so the caller pays and receives nothing
            // while the call reports success. Refuse loudly and point at the
            // method that can actually return it.
            if !content_type.contains("json") {
                return Err(NRouterError::Transport(format!(
                    "nRouter returned {status} with content-type '{content_type}', which is \
                     not JSON. Use `bytes()` for binary or streaming endpoints \
                     (/v1/audio/speech, /v1/videos/{{id}}/content, or stream: true); \
                     the JSON helpers would report success with an empty body."
                )));
            }
            // A 2xx whose JSON does not parse is NOT an empty response — it is
            // a truncated or corrupted one, for a request that was billed.
            // Returning Null here reports success with nothing in it.
            let body: Value = serde_json::from_slice(&bytes).map_err(|e| {
                NRouterError::Transport(format!(
                    "nRouter returned {status} with unparseable JSON ({e}); the request was \
                     billed but the body did not arrive intact."
                ))
            })?;
            return Ok(Response { body, meta });
        }
        let body: Value = serde_json::from_slice(&bytes).unwrap_or(Value::Null);
        Err(NRouterError::from_code(error_body(
            status,
            &body,
            &meta,
            retry_after,
        )))
    }
}

/// Pull the gateway's stable `code` and message out of an error payload.
///
/// The gateway nests them under `error`; a bare object is accepted too so a
/// proxy that reshapes the envelope does not turn a typed error into a generic
/// one.
fn error_body(
    status: u16,
    body: &Value,
    meta: &ResponseMeta,
    retry_after: Option<u64>,
) -> ErrorBody {
    let node = body.get("error").unwrap_or(body);
    ErrorBody {
        message: node
            .get("message")
            .and_then(Value::as_str)
            .unwrap_or("nRouter request failed")
            .to_string(),
        code: node.get("code").and_then(Value::as_str).map(str::to_owned),
        status: Some(status),
        request_id: meta.request_id.clone(),
        limit_source: meta.limit_source.clone(),
        auth_reason: meta.auth_reason.clone(),
        retry_after,
    }
}
