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

# Used only when the gateway supplied no code at all.
NROUTER_STATUS_CLASSES <- c(
  "400" = "nrouter_request_error",
  "401" = "nrouter_authentication_error",
  "402" = "nrouter_credit_error",
  "404" = "nrouter_not_found_error",
  "429" = "nrouter_rate_limit_error",
  "503" = "nrouter_service_error"
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
#' @return A condition object.
#' @export
nrouter_condition <- function(message, code = NULL, status = NULL,
                              request_id = NULL, limit_source = NULL,
                              auth_reason = NULL) {
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

  structure(
    class = c(specific, "nrouter_error", "error", "condition"),
    list(
      message = if (!is.null(code) && nzchar(code)) {
        paste0(message, " (", code, ")")
      } else {
        message
      },
      call = NULL,
      code = code,
      status = status,
      request_id = request_id,
      limit_source = limit_source,
      auth_reason = auth_reason
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
  any(class(cond) %in% NROUTER_RETRYABLE)
}
