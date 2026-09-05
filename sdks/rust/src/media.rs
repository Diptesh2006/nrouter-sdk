//! Media helpers for audio format validation and video polling.

use crate::errors::{ErrorBody, NRouterError};
use crate::http::{Client, Response};
use serde_json::Value;
use std::time::Duration;

/// Valid audio formats supported by the nRouter speech endpoint.
pub const VALID_AUDIO_FORMATS: &[&str] = &["mp3", "opus", "aac", "flac", "wav", "pcm"];

/// Validates an audio format string against the supported speech formats.
pub fn validate_audio_format(format: &str) -> Result<(), NRouterError> {
    let clean = format.trim().to_ascii_lowercase();
    if VALID_AUDIO_FORMATS.iter().any(|&f| f == clean) {
        Ok(())
    } else {
        Err(NRouterError::Configuration(format!(
            "invalid audio format {:?}; must be one of: {}",
            format,
            VALID_AUDIO_FORMATS.join(", ")
        )))
    }
}

impl Client {
    /// Polls a video generation job until it reaches a terminal status
    /// ("completed", "succeeded", "failed", "cancelled") or times out.
    pub async fn wait_for_video(
        &self,
        video_id: &str,
        poll_interval: Duration,
        timeout: Duration,
    ) -> Result<Response<Value>, NRouterError> {
        let trimmed = video_id.trim();
        if trimmed.is_empty() {
            return Err(NRouterError::Configuration(
                "video_id must not be empty".to_string(),
            ));
        }

        let start = std::time::Instant::now();
        while start.elapsed() < timeout {
            let resp = self.retrieve_video(trimmed).await?;
            if let Some(status) = resp.body.get("status").and_then(|s| s.as_str()) {
                let s = status.to_ascii_lowercase();
                if s == "completed" || s == "succeeded" {
                    return Ok(resp);
                }
                if s == "failed" || s == "cancelled" {
                    return Err(NRouterError::Service(Box::new(ErrorBody {
                        message: format!("video job {} ended with status: {}", trimmed, status),
                        code: Some("video_failed".to_string()),
                        status: Some(500),
                        request_id: resp.meta.request_id.clone(),
                        limit_source: None,
                        auth_reason: None,
                        retry_after: None,
                    })));
                }
            }
            tokio::time::sleep(poll_interval).await;
        }

        Err(NRouterError::Transport(format!(
            "Timeout waiting for video job {}",
            trimmed
        )))
    }
}
