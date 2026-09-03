#' Per-request metadata from the nRouter response headers
#'
#' Every field is \code{NULL} when the gateway did not send it. The gateway
#' omits a header rather than sending a placeholder, and the two omissions that
#' matter most are \code{x-nr-request-cost} — ABSENT when the model is unpriced,
#' never \code{0} — and \code{x-nr-limit-source}, absent when nothing measured a
#' refusal.
#'
#' @param headers Named character vector or list of response headers, keyed by
#'   lowercase name.
#' @return An object of class \code{nrouter_meta}.
#' @export
nrouter_meta <- function(headers = list()) {
  names(headers) <- tolower(names(headers))
  get_chr <- function(name) {
    value <- headers[[name]]
    if (is.null(value) || !nzchar(as.character(value))) NULL else as.character(value)
  }
  # suppressWarnings: a non-numeric header yields NA, which becomes NULL. A
  # zero here would be indistinguishable from a real zero.
  get_num <- function(name) {
    raw <- get_chr(name)
    if (is.null(raw)) return(NULL)
    value <- suppressWarnings(as.numeric(raw))
    if (is.na(value)) NULL else value
  }

  structure(
    class = "nrouter_meta",
    list(
      request_id         = get_chr("x-nr-request-id"),
      cost               = get_num("x-nr-request-cost"),
      cost_status        = get_chr("x-nr-cost-status"),
      model              = get_chr("x-nr-model"),
      input_tokens       = get_num("x-nr-input-tokens"),
      output_tokens      = get_num("x-nr-output-tokens"),
      total_tokens       = get_num("x-nr-total-tokens"),
      cache_read_tokens  = get_num("x-nr-cache-read-tokens"),
      cache_write_tokens = get_num("x-nr-cache-write-tokens"),
      limit_source       = get_chr("x-nr-limit-source"),
      budget_warning     = get_chr("x-nr-budget-warning"),
      auth_reason        = get_chr("x-nr-auth-reason"),
      response_cache     = get_chr("x-nr-response-cache"),
      response_cache_age = get_num("x-nr-response-cache-age")
    )
  )
}

#' Every response header this SDK reads
#'
#' Exactly the names in \code{spec/nrouter-sdk-spec.json}.
#' @return A character vector of 14 header names.
#' @export
nrouter_header_names <- function() {
  c(
    "x-nr-request-id",
    "x-nr-request-cost",
    "x-nr-cost-status",
    "x-nr-model",
    "x-nr-input-tokens",
    "x-nr-output-tokens",
    "x-nr-total-tokens",
    "x-nr-cache-read-tokens",
    "x-nr-cache-write-tokens",
    "x-nr-limit-source",
    "x-nr-budget-warning",
    "x-nr-auth-reason",
    "x-nr-response-cache",
    "x-nr-response-cache-age"
  )
}

#' Did the gateway price this request exactly?
#'
#' @param meta An \code{nrouter_meta} object.
#' @return \code{TRUE} only when the cost is both present and exact.
#' @export
nrouter_is_priced <- function(meta) {
  identical(meta$cost_status, "exact") && !is.null(meta$cost)
}

#' @export
print.nrouter_meta <- function(x, ...) {
  cost <- if (is.null(x$cost)) {
    # Unpriced is unknown, not free. Never print it as 0.
    paste0("unpriced", if (!is.null(x$cost_status)) paste0(" (", x$cost_status, ")") else "")
  } else {
    paste0("$", format(x$cost, scientific = FALSE))
  }
  cat("<nrouter_meta>\n")
  cat("  request_id:", x$request_id %||% "-", "\n")
  cat("  model:     ", x$model %||% "-", "\n")
  cat("  cost:      ", cost, "\n")
  invisible(x)
}

`%||%` <- function(a, b) if (is.null(a)) b else a
