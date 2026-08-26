#' The gateway's customer surface
#'
#' A dynamic value: override it for stage.
#' @return The default base URL.
#' @export
nrouter_default_base_url <- function() "https://api.nrouter.ai/v1"

#' The one environment variable this package reads
#' @return The variable name.
#' @export
nrouter_env_key <- function() "NROUTER_API_KEY"

#' The prefix every nRouter customer key carries
#' @return The key prefix.
#' @export
nrouter_key_prefix <- function() "sk-nrouter-"

#' Resolve and validate an nRouter API key
#'
#' Explicit argument first, then \code{NROUTER_API_KEY}. Validation happens
#' before any request so a malformed key fails here rather than as a 401 that
#' reads like a revoked credential.
#'
#' @param api_key Explicit key, or \code{NULL} to read the environment.
#' @return The validated key.
#' @export
nrouter_resolve_api_key <- function(api_key = NULL) {
  key <- if (is.null(api_key) || !nzchar(api_key)) {
    Sys.getenv(nrouter_env_key())
  } else {
    api_key
  }
  if (!nzchar(key)) {
    stop(nrouter_transport_condition(
      paste0("No nRouter API key: pass api_key or set ", nrouter_env_key(), ".")
    ))
  }
  if (!startsWith(key, nrouter_key_prefix())) {
    stop(nrouter_transport_condition(
      paste0("nRouter API keys start with '", nrouter_key_prefix(),
             "'; got one that does not.")
    ))
  }
  key
}

#' Create an nRouter client
#'
#' The gateway speaks the OpenAI wire format, so request and response bodies are
#' the shapes you already know. There is no official OpenAI SDK for R, so this
#' package calls the HTTP API directly via \pkg{httr}.
#'
#' @param api_key nRouter API key. Defaults to \code{NROUTER_API_KEY}.
#' @param base_url Gateway base URL.
#' @return An object of class \code{nrouter_client}.
#' @examples
#' \dontrun{
#' client <- nrouter_client()
#' result <- nrouter_chat_completions(client, list(
#'   model = "claude-sonnet-4-5",
#'   messages = list(list(role = "user", content = "Hello!"))
#' ))
#' # Unpriced is unknown, not free. Never render a NULL cost as 0.
#' print(result$meta)
#' }
#' @export
nrouter_client <- function(api_key = NULL, base_url = nrouter_default_base_url()) {
  structure(
    class = "nrouter_client",
    list(
      api_key  = nrouter_resolve_api_key(api_key),
      base_url = sub("/+$", "", base_url)
    )
  )
}

#' Pull the gateway's code and message out of an error payload
#'
#' The gateway nests them under \code{error}; a bare object is accepted too, so
#' a proxy that reshapes the envelope cannot downgrade a typed error into a
#' generic one.
#'
#' @param status HTTP status.
#' @param payload Parsed response body.
#' @param meta An \code{nrouter_meta} object.
#' @return A condition object.
#' @export
nrouter_error_from_payload <- function(status, payload, meta) {
  node <- if (is.list(payload) && !is.null(payload$error) && is.list(payload$error)) {
    payload$error
  } else {
    payload
  }
  message <- if (is.list(node) && is.character(node$message)) {
    node$message
  } else {
    "nRouter request failed"
  }
  code <- if (is.list(node) && is.character(node$code)) node$code else NULL

  nrouter_condition(
    message      = message,
    code         = code,
    status       = status,
    request_id   = meta$request_id,
    limit_source = meta$limit_source,
    auth_reason  = meta$auth_reason
  )
}

#' Send a request to the nRouter gateway
#'
#' @param client An \code{nrouter_client}.
#' @param path Path under the gateway's \code{/v1} root, e.g. \code{"/models"}.
#' @param body Named list to send as JSON, or \code{NULL} for a GET.
#' @param method HTTP method; inferred from \code{body} when not given.
#' @return A list with \code{body}, \code{meta} and \code{status_code}.
#' @export
nrouter_request <- function(client, path, body = NULL,
                            method = if (is.null(body)) "GET" else "POST") {
  url <- paste0(client$base_url, "/", sub("^/+", "", path))
  auth <- httr::add_headers(Authorization = paste("Bearer", client$api_key))

  response <- tryCatch(
    if (identical(method, "GET")) {
      httr::GET(url, auth)
    } else {
      httr::POST(
        url, auth, httr::content_type_json(),
        body = jsonlite::toJSON(body, auto_unbox = TRUE, null = "null")
      )
    },
    error = function(e) stop(nrouter_transport_condition(conditionMessage(e)))
  )

  meta <- nrouter_meta(as.list(httr::headers(response)))
  status <- httr::status_code(response)
  parsed <- tryCatch(
    httr::content(response, as = "parsed", type = "application/json"),
    error = function(e) list()
  )

  if (status >= 200 && status < 300) {
    return(list(body = parsed, meta = meta, status_code = status))
  }
  stop(nrouter_error_from_payload(status, parsed, meta))
}

#' POST /chat/completions
#' @param client An \code{nrouter_client}.
#' @param body Named list forming the request body.
#' @return A list with \code{body}, \code{meta} and \code{status_code}.
#' @export
nrouter_chat_completions <- function(client, body) {
  nrouter_request(client, "/chat/completions", body)
}

#' POST /embeddings
#' @inheritParams nrouter_chat_completions
#' @return A list with \code{body}, \code{meta} and \code{status_code}.
#' @export
nrouter_embeddings <- function(client, body) {
  nrouter_request(client, "/embeddings", body)
}

#' POST /messages (the Anthropic wire format the gateway also serves)
#' @inheritParams nrouter_chat_completions
#' @return A list with \code{body}, \code{meta} and \code{status_code}.
#' @export
nrouter_messages <- function(client, body) {
  nrouter_request(client, "/messages", body)
}

#' POST /responses
#' @inheritParams nrouter_chat_completions
#' @return A list with \code{body}, \code{meta} and \code{status_code}.
#' @export
nrouter_responses <- function(client, body) {
  nrouter_request(client, "/responses", body)
}

#' GET /models — what this key is allowed to route to
#' @param client An \code{nrouter_client}.
#' @return A list with \code{body}, \code{meta} and \code{status_code}.
#' @export
nrouter_models <- function(client) {
  nrouter_request(client, "/models")
}

#' Send a chat completion request (convenience wrapper)
#'
#' Kept as the package's original one-call entry point. Prefer
#' \code{nrouter_chat_completions()} when you need the response metadata.
#'
#' @param messages List of message objects, e.g.
#'   \code{list(list(role = "user", content = "Hello!"))}.
#' @param model Model name.
#' @param api_key nRouter API key. Defaults to \code{NROUTER_API_KEY}.
#' @param base_url Gateway base URL.
#' @return The parsed JSON response as an R list.
#' @export
nrouter_chat <- function(messages, model = "claude-sonnet-4-5", api_key = NULL,
                         base_url = nrouter_default_base_url()) {
  client <- nrouter_client(api_key = api_key, base_url = base_url)
  nrouter_chat_completions(client, list(model = model, messages = messages))$body
}
