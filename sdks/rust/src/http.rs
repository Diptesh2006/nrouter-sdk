//! A native client that can SEE the `x-nr-*` headers.
//!
//! `async-openai` gives the ergonomic OpenAI surface but hides the raw
//! response, so per-request cost, token counts and cache outcome are
//! unreachable through it. This client exists for exactly that: it speaks the
//! same OpenAI wire format and hands back the body together with
//! [`ResponseMeta`].

use serde_json::Value;
use std::net::IpAddr;
use std::time::Duration;

use crate::errors::{parse_retry_after, ErrorBody, NRouterError};
use crate::meta::ResponseMeta;
use crate::{resolve_api_key, DEFAULT_BASE_URL};

/// A response body paired with the metadata the gateway reported for it.
#[derive(Debug, Clone)]
pub struct Response<T> {
    pub body: T,
    pub meta: ResponseMeta,
}

/// One provider-native SSE frame plus portable incremental text.
#[derive(Debug, Clone)]
pub struct StreamChunk {
    pub event: Option<String>,
    pub delta: String,
    pub raw: Value,
}

/// An incremental billed response. Dropping it drops the reqwest response and
/// cancels the unread body rather than leaving generation running unseen.
pub struct EventStream {
    pub meta: ResponseMeta,
    response: reqwest::Response,
    buffer: Vec<u8>,
    done: bool,
}

impl EventStream {
    /// Read the next SSE frame. `Ok(None)` means an explicit protocol
    /// terminator; a bare EOF is a retryable transport failure.
    pub async fn next(&mut self) -> Result<Option<StreamChunk>, NRouterError> {
        if self.done {
            return Ok(None);
        }
        loop {
            if let Some(frame) = take_sse_frame(&mut self.buffer) {
                match parse_sse_frame(&frame, &self.meta)? {
                    ParsedFrame::Chunk(chunk) => return Ok(Some(chunk)),
                    ParsedFrame::Done => {
                        self.done = true;
                        return Ok(None);
                    }
                    ParsedFrame::Skip => continue,
                }
            }
            match self
                .response
                .chunk()
                .await
                .map_err(|e| NRouterError::Transport(e.to_string()))?
            {
                Some(bytes) => self.buffer.extend_from_slice(&bytes),
                None => {
                    self.done = true;
                    if !self.buffer.is_empty() {
                        let frame = std::mem::take(&mut self.buffer);
                        match parse_sse_frame(&frame, &self.meta)? {
                            ParsedFrame::Chunk(chunk) => return Ok(Some(chunk)),
                            ParsedFrame::Done => return Ok(None),
                            ParsedFrame::Skip => {}
                        }
                    }
                    return Err(NRouterError::Transport(
                        "the stream ended before its terminal event".into(),
                    ));
                }
            }
        }
    }
}

/// Thin nRouter HTTP client over the OpenAI wire format.
///
/// `Debug` is implemented by hand, NOT derived: a derived one prints `api_key`
/// verbatim, so a single `{:?}` in a caller's log leaks a credential that spends
/// real credits (Rule #5).
#[derive(Clone)]
pub struct Client {
    api_key: String,
    base_url: String,
    http: reqwest::Client,
    trace_id: Option<String>,
    session_id: Option<String>,
}

impl std::fmt::Debug for Client {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Client")
            // Never the key. Only the last four, and only enough to tell two
            // keys apart in a log — the same shape the dashboard shows.
            .field("api_key", &redacted(&self.api_key))
            .field("base_url", &self.base_url)
            .field("trace_id", &self.trace_id)
            .field("session_id", &self.session_id)
            .finish_non_exhaustive()
    }
}

/// `sk-nrouter-...abcd` — enough to identify, never enough to use.
fn redacted(api_key: &str) -> String {
    let tail: String = api_key
        .chars()
        .rev()
        .take(4)
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .collect();
    format!("{}...{}", crate::KEY_PREFIX, tail)
}

/// Parse and enforce the transport boundary before an API key is attached.
/// Plain HTTP is reserved for a gateway on the same machine; every remote
/// gateway must authenticate and encrypt the connection with HTTPS.
pub fn validate_gateway_base_url(value: &str) -> Result<reqwest::Url, NRouterError> {
    let mut url = reqwest::Url::parse(value).map_err(|error| {
        NRouterError::Configuration(format!("invalid nRouter gateway URL: {error}"))
    })?;
    if !url.username().is_empty() || url.password().is_some() {
        return Err(NRouterError::Configuration(
            "nRouter gateway URL must not contain credentials".into(),
        ));
    }

    let host = url.host_str().ok_or_else(|| {
        NRouterError::Configuration("nRouter gateway URL must include a host".into())
    })?;
    let normalized_host = host.trim_start_matches('[').trim_end_matches(']');
    let is_loopback = normalized_host.eq_ignore_ascii_case("localhost")
        || normalized_host
            .parse::<IpAddr>()
            .is_ok_and(|address| address.is_loopback());
    if url.scheme() != "https" && !(url.scheme() == "http" && is_loopback) {
        return Err(NRouterError::Configuration(
            "nRouter gateway URL must use HTTPS; HTTP is allowed only for loopback development"
                .into(),
        ));
    }

    if !url.path().ends_with('/') {
        let path = format!("{}/", url.path());
        url.set_path(&path);
    }
    Ok(url)
}

impl Client {
    /// How long the gateway has to complete the TCP + TLS handshake.
    ///
    /// Named, not buried in a builder chain: an unnamed deadline is infinity,
    /// and `reqwest::Client::new()` — which this client used to be built from —
    /// sets none at all. Ten seconds is generous for a handshake and short
    /// enough that a black-holed gateway address is reported rather than waited
    /// on.
    pub const DEFAULT_CONNECT_TIMEOUT: Duration = Duration::from_secs(10);

    /// How long the gateway may go SILENT — a BETWEEN-BYTES deadline, applied
    /// both to the wait for the first response byte and to every gap inside a
    /// stream.
    ///
    /// # Why this is `read_timeout` and deliberately not `timeout`
    ///
    /// `reqwest`'s `timeout` is a WHOLE-REQUEST deadline that covers the
    /// response body, so a stream served through a client carrying one dies
    /// mid-generation with a partial answer already billed, and a large
    /// `GET /videos/{id}/content` is truncated the same way. An inactivity
    /// deadline bounds the failure that actually matters — a gateway that
    /// accepted the connection and then said nothing — without putting a
    /// ceiling on how long a working stream may legitimately last. The gateway
    /// makes exactly this trade for its own provider client, and for the same
    /// reason; a caller who does want a whole-request ceiling can set one per
    /// call with `tokio::time::timeout`, which a streaming call can opt out of.
    ///
    /// # Why ten minutes, and not the gateway's own 120 s
    ///
    /// `reqwest` has no headers-only bound, so this one number must also cover
    /// the wait for the FIRST byte — and the gateway's worst honest case there
    /// is roughly 410 s: up to three provider attempts, each with a 10 s connect
    /// timeout and a 120 s between-bytes read timeout, plus up to 20 s of
    /// cumulative backoff between them. A client deadline below that aborts a
    /// request the gateway is about to answer, and the customer is billed for it
    /// regardless, because the provider tokens were already spent. Ten minutes
    /// sits above that with margin and is the same order as the OpenAI and
    /// Anthropic clients' own 600 s defaults.
    pub const DEFAULT_READ_TIMEOUT: Duration = Duration::from_secs(600);

    /// How long an idle pooled connection is kept.
    pub const DEFAULT_POOL_IDLE_TIMEOUT: Duration = Duration::from_secs(90);

    /// TCP keepalive interval. Shorter than the read deadline deliberately: a
    /// connection silently reaped by an intermediary is then discovered by the
    /// keepalive rather than by a caller waiting out the full read timeout.
    pub const DEFAULT_TCP_KEEPALIVE: Duration = Duration::from_secs(30);

    /// The HTTP client [`Client::new`] uses when [`Client::with_http_client`]
    /// is not called: explicit connect and between-bytes deadlines, and
    /// deliberately NO whole-request `timeout` (see
    /// [`Client::DEFAULT_READ_TIMEOUT`]).
    pub fn default_http_client() -> Result<reqwest::Client, NRouterError> {
        Self::http_client_with(Self::DEFAULT_CONNECT_TIMEOUT, Self::DEFAULT_READ_TIMEOUT)
    }

    /// [`Client::default_http_client`] with explicit deadlines, so a test can
    /// prove the read deadline FIRES without waiting ten minutes.
    ///
    /// Built by the same chain rather than a second one: every other property
    /// is identical, so a client that differed anywhere else would prove
    /// nothing about the client the SDK actually ships.
    pub fn http_client_with(
        connect_timeout: Duration,
        read_timeout: Duration,
    ) -> Result<reqwest::Client, NRouterError> {
        reqwest::Client::builder()
            .connect_timeout(connect_timeout)
            // BETWEEN-BYTES, never `.timeout()`. See DEFAULT_READ_TIMEOUT.
            .read_timeout(read_timeout)
            .pool_idle_timeout(Self::DEFAULT_POOL_IDLE_TIMEOUT)
            .tcp_keepalive(Self::DEFAULT_TCP_KEEPALIVE)
            .build()
            .map_err(|error| {
                NRouterError::Configuration(format!(
                    "could not build the nRouter HTTP client: {error}"
                ))
            })
    }

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
            http: Self::default_http_client()?,
            trace_id: None,
            session_id: None,
        })
    }

    /// Point the client at a different gateway (stage, or a local run).
    /// Requests require HTTPS except for `localhost` and loopback IPs.
    pub fn with_base_url(mut self, base_url: impl Into<String>) -> Self {
        self.base_url = base_url.into().trim_end_matches('/').to_string();
        self
    }

    /// Point the client at a different gateway and validate the URL immediately.
    pub fn try_with_base_url(mut self, base_url: impl Into<String>) -> Result<Self, NRouterError> {
        let b = base_url.into();
        validate_gateway_base_url(&b)?;
        self.base_url = b.trim_end_matches('/').to_string();
        Ok(self)
    }

    /// Configure a distributed trace ID to forward on outgoing requests.
    pub fn with_trace_id(mut self, trace_id: impl Into<String>) -> Result<Self, NRouterError> {
        let tid = trace_id.into();
        if tid.contains('\r') || tid.contains('\n') {
            return Err(NRouterError::Configuration(
                "trace_id must not contain CRLF characters".into(),
            ));
        }
        self.trace_id = Some(tid);
        Ok(self)
    }

    /// Configure an upstream session ID to forward on outgoing requests.
    pub fn with_session_id(mut self, session_id: impl Into<String>) -> Result<Self, NRouterError> {
        let sid = session_id.into();
        if sid.contains('\r') || sid.contains('\n') {
            return Err(NRouterError::Configuration(
                "session_id must not contain CRLF characters".into(),
            ));
        }
        self.session_id = Some(sid);
        Ok(self)
    }

    pub fn trace_id(&self) -> Option<&str> {
        self.trace_id.as_deref()
    }

    pub fn session_id(&self) -> Option<&str> {
        self.session_id.as_deref()
    }

    /// Override the underlying HTTP client — proxy, timeout, connection pool.
    ///
    /// It replaces [`Client::default_http_client`] entirely, including every
    /// deadline documented there, so the client passed here owns its own
    /// bounds. Two warnings worth carrying:
    ///
    /// - A `reqwest` `.timeout()` is a WHOLE-REQUEST deadline covering the
    ///   response body, so it severs SSE streaming and truncates
    ///   `GET /videos/{id}/content` mid-transfer — already billed. Prefer
    ///   `.read_timeout()`, or a per-call `tokio::time::timeout`.
    /// - This SDK never retries, and a caller must not wrap a billed `POST` in
    ///   a blind retry loop: every attempt is billed again, so a generic
    ///   `if err.is_retryable() { retry }` around one spends real credits in a
    ///   tight loop. `is_retryable()` reports whether an identical retry
    ///   *could* succeed; it is advisory, never an instruction.
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

    /// `POST /completions` — the legacy text-completions wire.
    pub async fn completions(&self, body: &Value) -> Result<Response<Value>, NRouterError> {
        self.post("/completions", body).await
    }

    /// `POST /embeddings`.
    pub async fn embeddings(&self, body: &Value) -> Result<Response<Value>, NRouterError> {
        self.post("/embeddings", body).await
    }

    /// Normalize messages body for the Anthropic Messages wire:
    /// extract system messages into top-level system, map max_completion_tokens,
    /// and normalize stop sequences.
    pub fn normalize_anthropic_messages(body: &Value) -> Value {
        let Some(obj) = body.as_object() else {
            return body.clone();
        };
        let mut out = obj.clone();

        if let Some(Value::Array(messages)) = out.get("messages") {
            let mut cleaned = Vec::new();
            let mut system_chunks: Vec<String> = Vec::new();

            if let Some(existing_sys) = out.get("system").and_then(|s| s.as_str()) {
                if !existing_sys.is_empty() {
                    system_chunks.push(existing_sys.to_string());
                }
            }

            for turn in messages {
                if let Some(t_obj) = turn.as_object() {
                    let role = t_obj.get("role").and_then(|r| r.as_str()).unwrap_or("");
                    if role.eq_ignore_ascii_case("system") || role.eq_ignore_ascii_case("developer")
                    {
                        if let Some(content_str) = t_obj.get("content").and_then(|c| c.as_str()) {
                            if !content_str.is_empty() {
                                system_chunks.push(content_str.to_string());
                            }
                        } else if let Some(parts) = t_obj.get("content").and_then(|c| c.as_array())
                        {
                            for part in parts {
                                if let Some(p_obj) = part.as_object() {
                                    if p_obj.get("type").and_then(|t| t.as_str()) == Some("text") {
                                        if let Some(txt) =
                                            p_obj.get("text").and_then(|t| t.as_str())
                                        {
                                            if !txt.is_empty() {
                                                system_chunks.push(txt.to_string());
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        continue;
                    }
                }
                cleaned.push(turn.clone());
            }

            out.insert("messages".into(), Value::Array(cleaned));
            if !system_chunks.is_empty() {
                out.insert("system".into(), Value::String(system_chunks.join("\n\n")));
            }
        }

        if let Some(max_comp) = out.remove("max_completion_tokens") {
            if !out.contains_key("max_tokens") {
                out.insert("max_tokens".into(), max_comp);
            }
        }

        if let Some(stop_val) = out.remove("stop") {
            if !out.contains_key("stop_sequences") {
                if let Some(s) = stop_val.as_str() {
                    if !s.is_empty() {
                        out.insert(
                            "stop_sequences".into(),
                            Value::Array(vec![Value::String(s.to_string())]),
                        );
                    }
                } else if let Some(arr) = stop_val.as_array() {
                    let valid: Vec<Value> = arr
                        .iter()
                        .filter(|item| item.as_str().is_some_and(|s| !s.is_empty()))
                        .cloned()
                        .collect();
                    if !valid.is_empty() {
                        out.insert("stop_sequences".into(), Value::Array(valid));
                    }
                }
            }
        }

        Value::Object(out)
    }

    /// `POST /messages` — the Anthropic wire format the gateway also serves.
    pub async fn messages(&self, body: &Value) -> Result<Response<Value>, NRouterError> {
        let normalized = Self::normalize_anthropic_messages(body);
        self.post("/messages", &normalized).await
    }

    /// `POST /responses`.
    pub async fn responses(&self, body: &Value) -> Result<Response<Value>, NRouterError> {
        self.post("/responses", body).await
    }

    /// Incremental `POST /chat/completions`.
    pub async fn chat_completions_stream(&self, body: &Value) -> Result<EventStream, NRouterError> {
        self.stream("/chat/completions", body).await
    }

    /// Incremental legacy `POST /completions`.
    pub async fn completions_stream(&self, body: &Value) -> Result<EventStream, NRouterError> {
        self.stream("/completions", body).await
    }

    /// Incremental native Anthropic `POST /messages`.
    pub async fn messages_stream(&self, body: &Value) -> Result<EventStream, NRouterError> {
        let normalized = Self::normalize_anthropic_messages(body);
        self.stream("/messages", &normalized).await
    }

    /// Incremental `POST /responses`.
    pub async fn responses_stream(&self, body: &Value) -> Result<EventStream, NRouterError> {
        self.stream("/responses", body).await
    }

    /// `POST /images/generations`.
    pub async fn images_generations(&self, body: &Value) -> Result<Response<Value>, NRouterError> {
        self.post("/images/generations", body).await
    }

    /// `POST /messages/count_tokens` — counts input without generating.
    pub async fn count_tokens(&self, body: &Value) -> Result<Response<Value>, NRouterError> {
        self.post("/messages/count_tokens", body).await
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

    /// `POST /audio/speech` — generated audio plus response metadata.
    pub async fn audio_speech(&self, body: &Value) -> Result<Response<Vec<u8>>, NRouterError> {
        self.bytes("POST", "/audio/speech", Some(body)).await
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
            .post(self.url(path)?)
            .bearer_auth(&self.api_key)
            .multipart(form);
        self.send(req).await
    }

    /// `GET /models` — what this key is allowed to route to.
    pub async fn models(&self) -> Result<Response<Value>, NRouterError> {
        self.get("/models").await
    }

    /// `GET /models/{model_id}` — one model visible to this key.
    pub async fn model(&self, model_id: &str) -> Result<Response<Value>, NRouterError> {
        self.get(&format!("/models/{}", percent_encode_model_id(model_id)))
            .await
    }

    /// `POST /videos` — starts a video generation job.
    pub async fn create_video(&self, body: &Value) -> Result<Response<Value>, NRouterError> {
        self.post("/videos", body).await
    }

    /// `GET /videos/{id}` — polls one video generation job.
    pub async fn retrieve_video(&self, video_id: &str) -> Result<Response<Value>, NRouterError> {
        self.get(&format!("/videos/{}", percent_encode_segment(video_id)))
            .await
    }

    /// `GET /videos/{id}/content` — generated video bytes.
    pub async fn download_video_content(
        &self,
        video_id: &str,
    ) -> Result<Response<Vec<u8>>, NRouterError> {
        self.bytes(
            "GET",
            &format!("/videos/{}/content", percent_encode_segment(video_id)),
            None,
        )
        .await
    }

    /// Any `POST` path under the gateway's `/v1` root.
    pub async fn post(&self, path: &str, body: &Value) -> Result<Response<Value>, NRouterError> {
        let req = self
            .http
            .post(self.url(path)?)
            .bearer_auth(&self.api_key)
            .json(body);
        self.send(req).await
    }

    /// Stream any JSON `POST` under the gateway's `/v1` root as SSE. The body
    /// is cloned before `stream: true` is inserted.
    pub async fn stream(&self, path: &str, body: &Value) -> Result<EventStream, NRouterError> {
        let mut streamed = body.clone();
        let object = streamed.as_object_mut().ok_or_else(|| {
            NRouterError::Configuration("streaming request body must be a JSON object".into())
        })?;
        object.insert("stream".into(), Value::Bool(true));
        let mut req = self
            .http
            .post(self.url(path)?)
            .bearer_auth(&self.api_key)
            .header(reqwest::header::ACCEPT, "text/event-stream")
            .json(&streamed);
        req = self.apply_custom_headers(req);
        let response = req
            .send()
            .await
            .map_err(|e| NRouterError::Transport(e.to_string()))?;
        let status = response.status().as_u16();
        let meta = ResponseMeta::from_headers(response.headers());
        let content_type = response
            .headers()
            .get(reqwest::header::CONTENT_TYPE)
            .and_then(|v| v.to_str().ok())
            .unwrap_or("")
            .to_ascii_lowercase();
        if !(200..300).contains(&status) {
            let retry_after = response
                .headers()
                .get(reqwest::header::RETRY_AFTER)
                .and_then(|v| parse_retry_after(v.to_str().ok()));
            let raw = response
                .bytes()
                .await
                .map_err(|e| NRouterError::Transport(e.to_string()))?;
            let parsed: Value = serde_json::from_slice(&raw).unwrap_or(Value::Null);
            return Err(NRouterError::from_code(error_body(
                status,
                &parsed,
                &meta,
                retry_after,
            )));
        }
        if !content_type.contains("text/event-stream") {
            return Err(NRouterError::Transport(format!(
                "nRouter returned {status} with content-type '{content_type}', which is not an SSE stream"
            )));
        }
        Ok(EventStream {
            meta,
            response,
            buffer: Vec::new(),
            done: false,
        })
    }

    /// Any `GET` path under the gateway's `/v1` root.
    pub async fn get(&self, path: &str) -> Result<Response<Value>, NRouterError> {
        let req = self.http.get(self.url(path)?).bearer_auth(&self.api_key);
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
            "GET" => self.http.get(self.url(path)?),
            _ => self.http.post(self.url(path)?),
        }
        .bearer_auth(&self.api_key);
        if let Some(json) = body {
            req = req.json(json);
        }
        req = self.apply_custom_headers(req);

        let response = req
            .send()
            .await
            .map_err(|e| NRouterError::Transport(e.to_string()))?;
        let status = response.status().as_u16();
        let meta = ResponseMeta::from_headers(response.headers());
        let retry_after = response
            .headers()
            .get(reqwest::header::RETRY_AFTER)
            .and_then(|v| parse_retry_after(v.to_str().ok()));
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

    fn apply_custom_headers(&self, mut req: reqwest::RequestBuilder) -> reqwest::RequestBuilder {
        req = req.header("x-nr-client-language", "rust");
        if let Some(ref tid) = self.trace_id {
            req = req.header("x-nr-trace-id", tid);
        }
        if let Some(ref sid) = self.session_id {
            req = req.header("x-nr-session-id", sid);
        }
        req
    }

    fn url(&self, path: &str) -> Result<reqwest::Url, NRouterError> {
        let base = validate_gateway_base_url(&self.base_url)?;
        base.join(path.trim_start_matches('/')).map_err(|error| {
            NRouterError::Configuration(format!("invalid nRouter gateway path: {error}"))
        })
    }

    async fn send(&self, req: reqwest::RequestBuilder) -> Result<Response<Value>, NRouterError> {
        let req = self.apply_custom_headers(req);
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
            .and_then(|v| parse_retry_after(v.to_str().ok()));
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

enum ParsedFrame {
    Chunk(StreamChunk),
    Done,
    Skip,
}

fn take_sse_frame(buffer: &mut Vec<u8>) -> Option<Vec<u8>> {
    let lf = buffer.windows(2).position(|w| w == b"\n\n").map(|i| (i, 2));
    let cr = buffer.windows(2).position(|w| w == b"\r\r").map(|i| (i, 2));
    let crlf = buffer
        .windows(4)
        .position(|w| w == b"\r\n\r\n")
        .map(|i| (i, 4));
    let mut candidates = Vec::new();
    if let Some(c) = lf {
        candidates.push(c);
    }
    if let Some(c) = cr {
        candidates.push(c);
    }
    if let Some(c) = crlf {
        candidates.push(c);
    }
    if candidates.is_empty() {
        return None;
    }
    candidates.sort_by_key(|c| c.0);
    let (index, delimiter) = candidates[0];
    let frame = buffer[..index].to_vec();
    buffer.drain(..index + delimiter);
    Some(frame)
}

fn parse_sse_frame(frame: &[u8], meta: &ResponseMeta) -> Result<ParsedFrame, NRouterError> {
    let text = String::from_utf8_lossy(frame);
    let mut event = None;
    let mut data = Vec::new();
    for raw_line in text.split(['\n', '\r']) {
        let line = raw_line.trim_end_matches('\r');
        if line.is_empty() || line.starts_with(':') {
            continue;
        }
        let (name, value) = line.split_once(':').unwrap_or((line, ""));
        let value = value.strip_prefix(' ').unwrap_or(value);
        match name {
            "event" => event = Some(value.to_string()),
            "data" => data.push(value),
            _ => {}
        }
    }
    let data = data.join("\n");
    let trimmed = data.trim();
    if trimmed.is_empty() {
        return Ok(ParsedFrame::Skip);
    }
    if trimmed == "[DONE]" {
        return Ok(ParsedFrame::Done);
    }
    let raw: Value = match serde_json::from_str(trimmed) {
        Ok(value) => value,
        Err(_) if event.as_deref() != Some("error") => return Ok(ParsedFrame::Skip),
        Err(_) => {
            return Err(NRouterError::from_code(ErrorBody {
                message: trimmed.to_string(),
                status: Some(200),
                request_id: meta.request_id.clone(),
                ..ErrorBody::default()
            }))
        }
    };
    if event.as_deref() == Some("error") || raw.get("error").is_some() {
        let node = raw.get("error").unwrap_or(&raw);
        let explicit = node.get("code").and_then(Value::as_str);
        let type_code = node
            .get("type")
            .and_then(Value::as_str)
            .filter(|code| is_known_error_code(code));
        return Err(NRouterError::from_code(ErrorBody {
            message: node
                .get("message")
                .and_then(Value::as_str)
                .unwrap_or(trimmed)
                .to_string(),
            code: explicit.or(type_code).map(str::to_string),
            param: node.get("param").and_then(Value::as_str).map(str::to_owned),
            error_type: node.get("type").and_then(Value::as_str).map(str::to_owned),
            status: Some(200),
            request_id: meta.request_id.clone(),
            limit_source: meta.limit_source.clone(),
            auth_reason: meta.auth_reason.clone(),
            retry_after: None,
        }));
    }
    if matches!(
        raw.get("type").and_then(Value::as_str),
        Some("message_stop" | "response.completed")
    ) {
        return Ok(ParsedFrame::Done);
    }
    let delta = raw
        .get("delta")
        .and_then(Value::as_str)
        .or_else(|| raw.pointer("/delta/text").and_then(Value::as_str))
        .or_else(|| raw.pointer("/choices/0/text").and_then(Value::as_str))
        .or_else(|| {
            raw.pointer("/choices/0/delta/content")
                .and_then(Value::as_str)
        })
        .unwrap_or("")
        .to_string();
    Ok(ParsedFrame::Chunk(StreamChunk { event, delta, raw }))
}

fn is_known_error_code(code: &str) -> bool {
    matches!(
        code,
        "invalid_request"
            | "guardrail_blocked"
            | "invalid_api_key"
            | "insufficient_credits"
            | "model_not_found"
            | "rate_limit_exceeded"
            | "tpm_limit_exceeded"
            | "credit_check_failed"
            | "service_unavailable"
    )
}

fn percent_encode_segment(value: &str) -> String {
    use std::fmt::Write as _;

    let mut encoded = String::with_capacity(value.len());
    for byte in value.bytes() {
        if byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'.' | b'_' | b'~') {
            encoded.push(char::from(byte));
        } else {
            let _ = write!(encoded, "%{byte:02X}");
        }
    }
    encoded
}

// Provider model IDs are wildcard paths (`provider/model`), whereas video IDs
// are single segments. Preserve model namespace separators and encode each
// component independently so the gateway WAF never receives `%2F`.
fn percent_encode_model_id(value: &str) -> String {
    value
        .split('/')
        .map(percent_encode_segment)
        .collect::<Vec<_>>()
        .join("/")
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
        param: node.get("param").and_then(Value::as_str).map(str::to_owned),
        error_type: node.get("type").and_then(Value::as_str).map(str::to_owned),
        status: Some(status),
        request_id: meta.request_id.clone(),
        limit_source: meta.limit_source.clone(),
        auth_reason: meta.auth_reason.clone(),
        retry_after,
    }
}

#[cfg(test)]
mod transport_security_tests {
    use super::validate_gateway_base_url;
    use crate::errors::NRouterError;

    #[test]
    fn cleartext_is_limited_to_loopback_development_gateways() {
        for allowed in [
            "http://127.0.0.1:4000/v1",
            "http://[::1]:4000/v1",
            "http://localhost:4000/v1",
            "https://api.nrouter.ai/v1",
        ] {
            validate_gateway_base_url(allowed).expect(allowed);
        }

        for refused in [
            "http://api.nrouter.ai/v1",
            "http://192.0.2.10:4000/v1",
            "ftp://127.0.0.1/v1",
            "https://user:pass@api.nrouter.ai/v1",
            "not-a-url",
        ] {
            assert!(
                matches!(
                    validate_gateway_base_url(refused),
                    Err(NRouterError::Configuration(_))
                ),
                "cleartext credential transport was accepted: {refused}"
            );
        }
    }
}

#[cfg(test)]
mod transport_deadline_tests {
    use super::Client;

    /// `Client::new` must install [`Client::default_http_client`], not
    /// `reqwest::Client::new()` — which sets no deadline of any kind and waits
    /// forever on a gateway that accepted the connection and then went silent.
    ///
    /// In-file rather than in `tests/`, because `http` is private: an
    /// integration test can prove the DEFAULT CLIENT is bounded and cannot prove
    /// the client `new()` actually installed is the bounded one. That gap is
    /// exactly the defect this fixes, so it is the gap the test has to close.
    #[test]
    fn new_installs_the_bounded_default_client() {
        let client = Client::new("sk-nrouter-test").expect("client");
        let rendered = format!("{:?}", client.http);
        assert!(
            rendered.contains("read_timeout"),
            "Client::new built an unbounded HTTP client: {rendered}"
        );
        // ANTI-VACUITY CONTROL for the negative assertion below.
        //
        // `!rendered.contains(" timeout:")` reads reqwest's UNSTABLE `Debug`
        // rendering. If a future reqwest stops rendering that field at all, the
        // negative assertion starts passing for a client that DOES carry a
        // whole-request timeout — it would go quiet on exactly the regression it
        // exists to catch. So prove the needle still appears when the thing is
        // really set: this control fails loudly on a rendering change and forces
        // the assertion below to be re-derived rather than silently trusted.
        // MEASURED, not guessed: reqwest renders a whole-request timeout as
        // `reqwest::config::TotalTimeout: 7s`. The needle this assertion used to
        // use — `" timeout:"` — appears in NO rendering, so it matched nothing
        // and passed for every client, including one that carried the very
        // timeout it was meant to forbid. A negative assertion on an unstable
        // Debug format is dead the moment the format moves, and it dies SILENT.
        let bounded = reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(1))
            .build()
            .expect("a client with a whole-request timeout builds");
        assert!(
            format!("{bounded:?}").contains(TOTAL_TIMEOUT_NEEDLE),
            "reqwest no longer renders a whole-request timeout as \
             `{TOTAL_TIMEOUT_NEEDLE}`, so the assertion below cannot see one \
             either and has stopped checking anything. Re-derive the needle \
             against the current reqwest — do not delete this control."
        );

        assert!(
            !rendered.contains(TOTAL_TIMEOUT_NEEDLE),
            "Client::new carries a whole-request timeout, which cuts streaming: {rendered}"
        );
    }

    /// How reqwest's `Debug` spells a whole-request timeout, measured against
    /// the pinned version. Named once so the control above and the assertion it
    /// guards can never drift apart.
    const TOTAL_TIMEOUT_NEEDLE: &str = "TotalTimeout";
}
