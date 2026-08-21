#' Send a chat completion request to nRouter
#'
#' Thin wrapper around the nRouter (\url{https://nrouter.ai}) OpenAI-compatible
#' chat completions endpoint. No official OpenAI SDK exists for R, so this
#' calls the HTTP API directly via \pkg{httr}.
#'
#' @param messages List of message objects, e.g.
#'   \code{list(list(role = "user", content = "Hello!"))}.
#' @param model Model name. Defaults to \code{"gpt-4o"}.
#' @param api_key nRouter API key. Defaults to the \code{NROUTER_API_KEY}
#'   environment variable.
#' @param base_url Gateway base URL. Defaults to
#'   \code{"https://api.nrouter.ai/v1"}.
#'
#' @return The parsed JSON response as an R list.
#' @export
nrouter_chat <- function(messages, model = "gpt-4o", api_key = NULL,
                          base_url = "https://api.nrouter.ai/v1") {
  key <- resolve_api_key(api_key)

  response <- httr::POST(
    url = paste0(base_url, "/chat/completions"),
    httr::add_headers(Authorization = paste("Bearer", key)),
    httr::content_type_json(),
    body = jsonlite::toJSON(
      list(model = model, messages = messages),
      auto_unbox = TRUE
    )
  )

  httr::content(response, as = "parsed", type = "application/json")
}

resolve_api_key <- function(api_key) {
  key <- if (is.null(api_key)) Sys.getenv("NROUTER_API_KEY") else api_key
  if (!nzchar(key) || !startsWith(key, "sk-nrouter-")) {
    stop("nRouter API keys must start with 'sk-nrouter-'; pass api_key or set NROUTER_API_KEY.")
  }
  key
}
