#' Supported audio formats for speech generation
#' @export
VALID_AUDIO_FORMATS <- c("mp3", "opus", "aac", "flac", "wav", "pcm")

#' Validates an audio format string against supported speech formats
#'
#' @param format Format string (e.g. "mp3", "wav")
#' @export
nrouter_validate_audio_format <- function(format) {
  if (!is.character(format) || length(format) != 1 || !nzchar(trimws(format))) {
    stop(nrouter_configuration_condition("Audio format must be a non-empty character string"))
  }
  clean <- tolower(trimws(format))
  if (!(clean %in% VALID_AUDIO_FORMATS)) {
    stop(nrouter_configuration_condition(
      sprintf("Invalid audio format '%s'; must be one of: %s", format, paste(VALID_AUDIO_FORMATS, collapse = ", "))
    ))
  }
  invisible(clean)
}

#' Polls a video generation job until completion, failure, or timeout
#'
#' @param client An nRouter client
#' @param video_id The video job identifier
#' @param poll_interval Seconds between status polls (default 0.05)
#' @param timeout Seconds before timing out (default 30)
#' @return The completed video response
#' @export
nrouter_wait_for_video <- function(client, video_id, poll_interval = 0.05, timeout = 30) {
  if (!is.character(video_id) || length(video_id) != 1 || !nzchar(trimws(video_id))) {
    stop(nrouter_configuration_condition("video_id must be a non-empty character string"))
  }
  clean_id <- trimws(video_id)
  start_time <- Sys.time()

  while (as.numeric(difftime(Sys.time(), start_time, units = "secs")) < timeout) {
    resp <- nrouter_retrieve_video(client, clean_id)
    status <- resp$body[["status"]]
    if (!is.null(status) && nzchar(as.character(status))) {
      s <- tolower(trimws(as.character(status)))
      if (s %in% c("completed", "succeeded")) {
        return(resp)
      } else if (s %in% c("failed", "cancelled")) {
        stop(nrouter_condition(
          message = sprintf("Video job %s ended with status: %s", clean_id, status),
          code = "video_failed",
          status = 500,
          request_id = resp$meta$request_id
        ))
      }
    }
    Sys.sleep(poll_interval)
  }

  stop(nrouter_transport_condition(sprintf("Timeout waiting for video job %s", clean_id)))
}
