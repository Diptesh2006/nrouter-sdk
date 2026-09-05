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
      # Posture only: `none`|`monitor`|`pass`|`partial`|`blocked`, matched
      # exactly and case-sensitively. NULL is "no guardrail claim made",
      # never "no guardrail applied" — that is the explicit "none".
      guardrails         = get_chr("x-nr-guardrails"),
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
#' @return A character vector of 15 header names.
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
    "x-nr-guardrails",
    "x-nr-auth-reason",
    "x-nr-response-cache",
    "x-nr-response-cache-age"
  )
}

nrouter_is_priced <- function(meta) {
  identical(meta$cost_status, "exact") && !is.null(meta$cost)
}

#' Parse structured budget warning from response metadata
#'
#' @param meta An \code{nrouter_meta} object or character string.
#' @return A list with scope, spend, ceiling, or NULL if absent/unparseable.
#' @export
nrouter_parse_budget_warning <- function(meta) {
  raw <- if (inherits(meta, "nrouter_meta")) meta$budget_warning else meta
  if (is.null(raw) || !nzchar(as.character(raw))) return(NULL)
  raw <- trimws(as.character(raw))
  parts <- strsplit(raw, "\\s+")[[1]]
  if (length(parts) != 3 || parts[2] != "soft_budget") return(NULL)
  scope <- parts[1]
  amounts <- strsplit(parts[3], "/")[[1]]
  if (length(amounts) != 2) return(NULL)
  spend <- suppressWarnings(as.numeric(amounts[1]))
  ceiling <- suppressWarnings(as.numeric(amounts[2]))
  if (is.na(spend) || is.na(ceiling) || spend < 0 || ceiling <= 0) return(NULL)
  list(scope = scope, spend = spend, ceiling = ceiling)
}

#' Check if response was a cache hit
#'
#' @param meta An \code{nrouter_meta} object.
#' @return Logical TRUE if cache hit.
#' @export
nrouter_is_cache_hit <- function(meta) {
  identical(meta$response_cache, "hit")
}

#' Check if response was a cache miss
#'
#' @param meta An \code{nrouter_meta} object.
#' @return Logical TRUE if cache miss.
#' @export
nrouter_is_cache_miss <- function(meta) {
  identical(meta$response_cache, "miss")
}

#' Cache age in seconds
#'
#' @param meta An \code{nrouter_meta} object.
#' @return Numeric age in seconds, or 0.
#' @export
nrouter_cache_age_seconds <- function(meta) {
  if (!is.null(meta$response_cache_age)) meta$response_cache_age else 0
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
