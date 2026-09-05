#' nRouter error conditions
#'
#' Every gateway refusal is raised as a classed R condition. The class vector
#' runs specific-to-general — e.g.
#' \code{c("nrouter_rate_limit_error", "nrouter_error", "error", "condition")} —
#' so \code{tryCatch(nrouter_error = ...)} catches everything while
#' \code{tryCatch(nrouter_rate_limit_error = ...)} catches only that.
#'
#' The gateway's stable \code{code} decides the class, not the HTTP status:
#' status alone cannot separate \code{invalid_request} from
#' \code{guardrail_blocked} (both 400), nor \code{rate_limit_exceeded} from
#' \code{tpm_limit_exceeded} (both 429).
#'
#' @name nrouter-errors
NULL

# code -> the specific condition class it raises.
NROUTER_ERROR_CLASSES <- c(
  invalid_request      = "nrouter_request_error",
  guardrail_blocked    = "nrouter_guardrail_blocked_error",
  invalid_api_key      = "nrouter_authentication_error",
  insufficient_credits = "nrouter_credit_error",
  model_not_found      = "nrouter_not_found_error",
  rate_limit_exceeded  = "nrouter_rate_limit_error",
  tpm_limit_exceeded   = "nrouter_rate_limit_error",
  credit_check_failed  = "nrouter_service_error",
  service_unavailable  = "nrouter_service_error"
)

NROUTER_STATUS_CLASSES <- c(
  "400" = "nrouter_request_error",
  "401" = "nrouter_authentication_error",
  "402" = "nrouter_credit_error",
  "404" = "nrouter_not_found_error",
  "408" = "nrouter_transport_error",
  "425" = "nrouter_service_error",
  "429" = "nrouter_rate_limit_error",
  "502" = "nrouter_service_error",
  "503" = "nrouter_service_error",
  "504" = "nrouter_service_error"
)

# Classes a retry could plausibly clear. Every other 4xx names something
# permanent, where a retry burns quota and cannot change the answer.
NROUTER_RETRYABLE <- c(
  "nrouter_rate_limit_error",
  "nrouter_service_error",
  "nrouter_transport_error"
)

#' Build (but do not signal) an nRouter condition
#'
#' @param message Human-readable message.
#' @param code The gateway's stable error code, or \code{NULL}.
#' @param status HTTP status, or \code{NULL}.
#' @param request_id Value of \code{x-nr-request-id}, or \code{NULL}.
#' @param limit_source Value of \code{x-nr-limit-source}, or \code{NULL}.
#' @param auth_reason Value of \code{x-nr-auth-reason}, or \code{NULL}.
#' @param retry_after Value of \code{Retry-After} in seconds, or \code{NULL}.
#' @param param Offending request parameter name, or \code{NULL}.
#' @param type Error category type, or \code{NULL}.
#' @return A condition object.
#' @export
nrouter_condition <- function(message, code = NULL, status = NULL,
                              request_id = NULL, limit_source = NULL,
                              auth_reason = NULL, retry_after = NULL,
                              param = NULL, type = NULL) {
  specific <- NULL
  if (!is.null(code) && nzchar(code)) {
    specific <- unname(NROUTER_ERROR_CLASSES[code])
    # An unrecognised code stays generic. Forcing it into a neighbouring class
    # is how a caller gets told to retry something permanent.
    if (is.na(specific)) specific <- "nrouter_other_error"
  } else if (!is.null(status)) {
    # The gateway's main error path emits {"error":{"type","message"}} with NO
    # code, so this branch is the ORDINARY case, not a fallback. The two 400s
    # share a status, and with no code the message is the only signal present:
    # calling every 400 a request error makes nrouter_guardrail_blocked_error
    # unreachable and tells a caller to fix a body that was never the problem.
    specific <- if (identical(as.character(status), "400") &&
                    grepl("guardrail", message, ignore.case = TRUE)) {
      "nrouter_guardrail_blocked_error"
    } else if (identical(as.character(status), "402") &&
               grepl("^\\s*budget", message, ignore.case = TRUE)) {
      # Three conditions share 402 and two are budget ceilings, whose fix is the
      # OPPOSITE of a shortfall's: raise the budget, not top up.
      "nrouter_budget_exceeded_error"
    } else if (identical(as.character(status), "404") &&
               !grepl("model", message, ignore.case = TRUE)) {
      # A 404 is also a missing video job, MCP server or agent run; calling
      # those model_not_found is a wrong answer with a confident code on it.
      "nrouter_other_error"
    } else {
      unname(NROUTER_STATUS_CLASSES[as.character(status)])
    }
    if (is.na(specific)) specific <- "nrouter_other_error"
  } else {
    specific <- "nrouter_other_error"
  }

  redacted_msg <- nrouter_redact_keys(message)
  structure(
    class = c(specific, "nrouter_error", "error", "condition"),
    list(
      message = if (!is.null(code) && nzchar(code)) {
        paste0(redacted_msg, " (", code, ")")
      } else {
        redacted_msg
      },
      call = NULL,
      code = code,
      param = param,
      type = type,
      status = status,
      request_id = request_id,
      limit_source = limit_source,
      auth_reason = auth_reason,
      retry_after = retry_after
    )
  )
}

#' A configuration failure: the SDK refused before sending anything
#'
#' Separate from \code{nrouter_transport_condition} on purpose. Both are raised
#' locally, but this one is PERMANENT — a caller retrying on
#' \code{nrouter_is_retryable} would spin forever without making a request.
#'
#' @param message Human-readable message.
#' @return A condition object.
#' @export
nrouter_configuration_condition <- function(message) {
  structure(
    class = c("nrouter_configuration_error", "nrouter_error", "error", "condition"),
    list(message = message, call = NULL, code = NULL, status = NULL,
         request_id = NULL, limit_source = NULL, auth_reason = NULL)
  )
}

#' A transport failure: the request left this process and got no answer
#'
#' @param message Human-readable message.
#' @return A condition object.
#' @export
nrouter_transport_condition <- function(message) {
  structure(
    class = c("nrouter_transport_error", "nrouter_error", "error", "condition"),
    list(message = message, call = NULL, code = NULL, status = NULL,
         request_id = NULL, limit_source = NULL, auth_reason = NULL)
  )
}

#' Is this nRouter condition worth retrying?
#'
#' @param cond A condition raised by this package.
#' @return \code{TRUE} when retrying the identical request could succeed.
#' @export
nrouter_is_retryable <- function(cond) {
  if (!is.null(cond$status) && cond$status %in% c(408, 425)) {
    return(TRUE)
  }
  any(class(cond) %in% NROUTER_RETRYABLE)
}

#' Maximum Retry-After delay in seconds (24 hours).
#' @export
NROUTER_MAX_RETRY_AFTER_SECONDS <- 86400L

#' Parse an RFC 9110 / RFC 7231 Retry-After header
#'
#' Supports delta-seconds or HTTP-date format.
#' Clamps return value between 0 and 86400 (24 hours).
#'
#' @param raw Character string from the Retry-After header, or NULL.
#' @param now Current time as POSIXct, defaulting to Sys.time().
#' @return Integer seconds to wait, or NULL if absent/unparseable.
#' @export
nrouter_parse_retry_after <- function(raw, now = Sys.time()) {
  if (is.null(raw) || !is.character(raw) || length(raw) == 0 || is.na(raw[[1]])) {
    return(NULL)
  }
  trimmed <- trimws(raw[[1]])
  if (!nzchar(trimmed)) {
    return(NULL)
  }
  if (grepl("^[0-9]+$", trimmed)) {
    val <- suppressWarnings(as.numeric(trimmed))
    if (is.na(val)) return(NROUTER_MAX_RETRY_AFTER_SECONDS)
    val <- max(0, min(val, NROUTER_MAX_RETRY_AFTER_SECONDS))
    return(as.integer(val))
  }
  parsed_date <- tryCatch(
    as.POSIXct(trimmed, format = "%a, %d %b %Y %H:%M:%S GMT", tz = "GMT"),
    error = function(e) NA
  )
  if (is.na(parsed_date)) {
    parsed_date <- tryCatch(
      as.POSIXct(trimmed, tz = "GMT"),
      error = function(e) NA
    )
  }
  if (is.na(parsed_date)) {
    return(NULL)
  }
  diff_secs <- as.numeric(difftime(parsed_date, now, units = "secs"))
  if (diff_secs <= 0) {
    return(0L)
  }
  diff_secs <- min(diff_secs, NROUTER_MAX_RETRY_AFTER_SECONDS)
  as.integer(ceiling(diff_secs))
}

#' Compute jittered exponential backoff
#'
#' Computes backoff delay in seconds with full jitter.
#' Clamps attempt to [0, 30] to prevent integer overflow.
#' Honors retry_after_seconds if provided and > 0.
#'
#' @param attempt Zero-based retry attempt number.
#' @param base_delay_seconds Base delay in seconds (default 0.5s).
#' @param max_delay_seconds Maximum delay ceiling in seconds (default 30s).
#' @param retry_after_seconds Optional Retry-After delay in seconds.
#' @param jitter_factor Floating point between 0.0 and 1.0 (default 0.5).
#' @return Delay in seconds (numeric).
#' @export
nrouter_compute_jittered_backoff <- function(attempt,
                                             base_delay_seconds = 0.5,
                                             max_delay_seconds = 30.0,
                                             retry_after_seconds = NULL,
                                             jitter_factor = 0.5) {
  safe_attempt <- max(0L, min(as.integer(attempt), 30L))
  safe_jitter <- max(0.0, min(as.numeric(jitter_factor), 1.0))

  if (!is.null(retry_after_seconds) && !is.na(retry_after_seconds) && retry_after_seconds > 0) {
    retry_secs <- min(as.numeric(retry_after_seconds), max_delay_seconds)
    mult <- (1.0 - safe_jitter) + stats::runif(1, 0, safe_jitter)
    return(max(0.0, retry_secs * mult))
  }

  raw_secs <- min(base_delay_seconds * (2^safe_attempt), max_delay_seconds)
  mult <- (1.0 - safe_jitter) + stats::runif(1, 0, safe_jitter)
  max(0.0, raw_secs * mult)
}

#' Redact API keys and credentials from strings
#'
#' Replaces nRouter and upstream provider API keys to prevent credential leaks.
#'
#' @param s Character vector or string.
#' @return Sanitized character vector.
#' @export
nrouter_redact_keys <- function(s) {
  if (is.null(s)) return(NULL)
  if (!is.character(s)) return(s)
  masked <- gsub("\\bsk-nrouter-[A-Za-z0-9._-]{4,}", "sk-nrouter-***", s)
  gsub("\\bsk-(?!nrouter)[A-Za-z0-9._-]{5,}\\b", "sk-***", masked, perl = TRUE)
}

#' Format an nRouter condition into a log-safe diagnostic string
#'
#' @param cond A condition raised by this package.
#' @return A single formatted diagnostic string.
#' @export
nrouter_format_error <- function(cond) {
  if (is.null(cond)) return("")
  cls <- class(cond)
  kind <- if (length(cls) > 0) cls[[1L]] else "error"
  kind_clean <- sub("^nrouter_", "", sub("_error$", "", kind))

  parts <- c(sprintf("[%s]", kind_clean))
  if (!is.null(cond$status) && !is.na(cond$status) && cond$status > 0) {
    parts <- c(parts, sprintf("HTTP %s", cond$status))
  }
  if (!is.null(cond$code) && nzchar(cond$code)) {
    parts <- c(parts, sprintf("code=%s", cond$code))
  }
  if (!is.null(cond$param) && nzchar(cond$param)) {
    parts <- c(parts, sprintf("param=%s", cond$param))
  }
  if (!is.null(cond$type) && nzchar(cond$type)) {
    parts <- c(parts, sprintf("type=%s", cond$type))
  }
  if (!is.null(cond$request_id) && nzchar(cond$request_id)) {
    parts <- c(parts, sprintf("req_id=%s", cond$request_id))
  }
  if (!is.null(cond$message) && nzchar(cond$message)) {
    parts <- c(parts, sprintf(": %s", nrouter_redact_keys(cond$message)))
  }
  paste(parts, collapse = " ")
}

#' @export
format.nrouter_error <- function(x, ...) {
  nrouter_format_error(x)
}

#' @export
print.nrouter_error <- function(x, ...) {
  cat(nrouter_format_error(x), "\n")
  invisible(x)
}

#' Parse a gateway error JSON payload into a structured envelope
#'
#' @param payload A list or JSON character string.
#' @return A named list with elements code, message, param, type.
#' @export
nrouter_parse_gateway_error_envelope <- function(payload) {
  if (is.null(payload)) {
    return(list(code = NULL, message = NULL, param = NULL, type = NULL))
  }
  data <- if (is.character(payload) && length(payload) == 1L) {
    tryCatch(
      jsonlite::fromJSON(payload, simplifyVector = FALSE),
      error = function(e) list(message = payload)
    )
  } else {
    payload
  }
  if (!is.list(data)) {
    return(list(code = NULL, message = nrouter_redact_keys(as.character(data)), param = NULL, type = NULL))
  }
  node <- if (!is.null(data$error) && is.list(data$error)) data$error else data

  get_val <- function(field) {
    v <- node[[field]]
    if (is.null(v)) v <- data[[field]]
    if (is.character(v) && length(v) >= 1L && nzchar(v[[1L]])) v[[1L]] else NULL
  }

  msg <- get_val("message")
  list(
    code    = get_val("code"),
    message = if (!is.null(msg)) nrouter_redact_keys(msg) else NULL,
    param   = get_val("param"),
    type    = get_val("type")
  )
}


