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

#' True when a model family is served on /v1/messages rather than /v1/chat/completions
#' @param model The model identifier string.
#' @param provider Optional provider name string.
#' @return TRUE when the model uses the messages wire, FALSE otherwise.
#' @export
nrouter_uses_messages_wire <- function(model, provider = NULL) {
  m <- tolower(as.character(model))
  if (grepl("claude|anthropic|haiku|sonnet|opus", m)) {
    return(TRUE)
  }
  if (!is.null(provider) && grepl("anthropic", tolower(as.character(provider)))) {
    return(TRUE)
  }
  FALSE
}

# --- transport deadlines -----------------------------------------------------
#
# \pkg{httr} passes no timeout to libcurl unless one is given, and libcurl's own
# CURLOPT_TIMEOUT defaults to ZERO, which means "wait forever". A gateway that
# accepts the connection and then goes silent hung the calling R session with no
# way out but interrupting it. Every number below is an explicit decision --
# name it, or you have chosen infinity -- sized against the gateway's own budget
# rather than picked for feel.
#
# The gateway's worst HONEST case before a first byte is roughly 410 s: up to
# three provider attempts, each with a 10 s connect timeout and a 120 s
# between-bytes read timeout, plus at most 20 s of cumulative backoff. A client
# deadline below that aborts a request the gateway is about to answer -- and the
# customer is billed anyway, because the provider tokens were already spent.
#
# None of these ever RETRIES. Waiting is bounded here; re-sending is not done at
# all. The gateway reserves credit ONCE per customer request and owns retry and
# failover, so a client retry of a billed POST is a second call and a second
# bill with nothing to dedupe on.

#' Whole-request ceiling for buffered calls, in seconds
#'
#' Applied to \code{nrouter_request()} and \code{nrouter_multipart()} as
#' \code{httr::timeout()}. 600 s is above the gateway's ~410 s worst honest case
#' with margin, and the same order as the OpenAI and Anthropic clients' own
#' 600 s defaults.
#' @return The default request timeout in seconds.
#' @export
nrouter_default_timeout_seconds <- function() 600

#' Connect-phase ceiling, in seconds
#'
#' Bounds DNS resolution plus the TCP handshake and nothing after it, so a
#' black-holed gateway address is reported rather than waited on. Matches the
#' gateway's own 10 s provider connect timeout.
#' @return The default connect timeout in seconds.
#' @export
nrouter_default_connect_timeout_seconds <- function() 10

#' Stall ceiling for streaming and binary transfers, in seconds
#'
#' \code{nrouter_stream()} and \code{nrouter_bytes()} deliberately set NO
#' whole-request timeout: a whole-request ceiling severs an SSE stream
#' mid-generation and truncates a long \code{/v1/videos/\{id\}/content}
#' download, both of them already billed. They bound the transfer with libcurl's
#' low-speed limit instead, so a transfer that STOPS producing bytes for this
#' long is abandoned while a working one runs as long as it needs. 180 s sits
#' above the gateway's own 120 s between-bytes read timeout, so the gateway's
#' honest error reaches the caller instead of a client-side abort racing it.
#' @return The default stall timeout in seconds.
#' @export
nrouter_default_stream_idle_seconds <- function() 180

# One place the deadlines turn into httr/curl options, so no request path can
# quietly acquire a different bound. `%||%`-style fallbacks are deliberate: a
# client list built before these fields existed must still get the defaults
# rather than silently reverting to libcurl's "wait forever".
nrouter_timeout_seconds <- function(client) {
  value <- client$timeout_seconds
  if (is.null(value)) nrouter_default_timeout_seconds() else value
}

nrouter_connect_timeout_seconds <- function(client) {
  value <- client$connect_timeout_seconds
  if (is.null(value)) nrouter_default_connect_timeout_seconds() else value
}

nrouter_stream_idle_seconds <- function(client) {
  value <- client$stream_idle_seconds
  if (is.null(value)) nrouter_default_stream_idle_seconds() else value
}

# Buffered calls: a hard whole-request ceiling plus a connect ceiling.
nrouter_request_config <- function(client) {
  c(
    httr::timeout(nrouter_timeout_seconds(client)),
    httr::config(connecttimeout = nrouter_connect_timeout_seconds(client))
  )
}

# Streaming and binary transfers: a connect ceiling and a STALL ceiling, and
# deliberately no `timeout`. `low_speed_limit = 1` with `low_speed_time = n`
# aborts a transfer averaging under one byte per second for n seconds, which
# bounds the failure that matters without capping a legitimately long transfer.
nrouter_transfer_config <- function(client) {
  httr::config(
    connecttimeout = nrouter_connect_timeout_seconds(client),
    low_speed_limit = 1,
    low_speed_time = nrouter_stream_idle_seconds(client)
  )
}

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
    stop(nrouter_configuration_condition(
      paste0("No nRouter API key: pass api_key or set ", nrouter_env_key(), ".")
    ))
  }
  if (!startsWith(key, nrouter_key_prefix())) {
    stop(nrouter_configuration_condition(
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
#' @param timeout_seconds Whole-request ceiling for buffered calls. See
#'   \code{\link{nrouter_default_timeout_seconds}}.
#' @param connect_timeout_seconds Connect-phase ceiling. See
#'   \code{\link{nrouter_default_connect_timeout_seconds}}.
#' @param stream_idle_seconds Stall ceiling for streaming and binary transfers,
#'   which carry no whole-request ceiling. See
#'   \code{\link{nrouter_default_stream_idle_seconds}}.
#' @return An object of class \code{nrouter_client}.
#' @examples
#' \dontrun{
#' client <- nrouter_client()
#' result <- nrouter_chat_completions(client, list(
#'   model = "gpt-5.4-mini",
#'   messages = list(list(role = "user", content = "Hello!"))
#' ))
#' # Unpriced is unknown, not free. Never render a NULL cost as 0.
#' print(result$meta)
#' }
#' Validate and normalize the nRouter gateway base URL
#'
#' Enforces HTTPS scheme unless targeting loopback addresses (localhost,
#' 127.0.0.1, ::1, 0.0.0.0, or *.local), rejects embedded user credentials,
#' and trims trailing slashes.
#' @param base_url The base URL string to validate.
#' @return Normalized base URL string without trailing slashes.
#' @export
nrouter_validate_gateway_base_url <- function(base_url) {
  cleaned_base <- trimws(as.character(base_url))
  if (grepl("[\r\n\t ]", cleaned_base)) {
    stop(nrouter_configuration_condition("base_url contains invalid control characters or whitespace"))
  }
  if (!grepl("^https?://", cleaned_base, ignore.case = TRUE)) {
    stop(nrouter_configuration_condition("invalid nRouter gateway URL: must start with https:// or http://"))
  }
  scheme <- tolower(sub("://.*$", "", cleaned_base))
  rest <- sub("^https?://", "", cleaned_base, ignore.case = TRUE)
  authority <- sub("[/?#].*$", "", rest)
  if (grepl("@", authority)) {
    stop(nrouter_configuration_condition("nRouter gateway URL must not contain credentials"))
  }
  if (startsWith(authority, "[")) {
    host_part <- sub(":[0-9]+$", "", authority)
    if (!endsWith(host_part, "]")) {
      stop(nrouter_configuration_condition("invalid nRouter gateway URL: malformed IPv6 host"))
    }
    host <- substr(host_part, 2, nchar(host_part) - 1)
  } else {
    host <- sub(":[0-9]+$", "", authority)
    if (grepl(":", host)) {
      stop(nrouter_configuration_condition("invalid nRouter gateway URL: malformed host"))
    }
  }
  host <- tolower(host)
  if (!nzchar(host)) {
    stop(nrouter_configuration_condition("nRouter gateway URL must include a host"))
  }
  is_loopback <- host %in% c("localhost", "127.0.0.1", "::1", "0.0.0.0") || endsWith(host, ".local")
  if (scheme == "http" && !is_loopback) {
    stop(nrouter_configuration_condition("nRouter gateway URL must use HTTPS; HTTP is allowed only for loopback development"))
  }
  sub("/+$", "", cleaned_base)
}

nrouter_request_headers <- function(client, extra = list()) {
  hdr <- list(
    Authorization = paste("Bearer", client$api_key),
    "x-nr-client-language" = "r"
  )
  if (!is.null(client$trace_id) && nzchar(as.character(client$trace_id))) {
    hdr[["x-nr-trace-id"]] <- as.character(client$trace_id)
  }
  if (!is.null(client$session_id) && nzchar(as.character(client$session_id))) {
    hdr[["x-nr-session-id"]] <- as.character(client$session_id)
  }
  if (length(extra) > 0) {
    for (nm in names(extra)) {
      hdr[[nm]] <- extra[[nm]]
    }
  }
  hdr
}

#' @export
nrouter_client <- function(api_key = NULL, base_url = nrouter_default_base_url(),
                           timeout_seconds = nrouter_default_timeout_seconds(),
                           connect_timeout_seconds =
                             nrouter_default_connect_timeout_seconds(),
                           stream_idle_seconds =
                             nrouter_default_stream_idle_seconds(),
                           trace_id = NULL,
                           session_id = NULL) {
  valid_base <- nrouter_validate_gateway_base_url(base_url)
  if (!is.null(trace_id) && grepl("[\r\n]", as.character(trace_id))) {
    stop(nrouter_configuration_condition("trace_id must not contain CRLF characters"))
  }
  if (!is.null(session_id) && grepl("[\r\n]", as.character(session_id))) {
    stop(nrouter_configuration_condition("session_id must not contain CRLF characters"))
  }
  structure(
    class = "nrouter_client",
    list(
      api_key                 = nrouter_resolve_api_key(api_key),
      base_url                = valid_base,
      timeout_seconds         = timeout_seconds,
      connect_timeout_seconds = connect_timeout_seconds,
      stream_idle_seconds     = stream_idle_seconds,
      trace_id                = trace_id,
      session_id              = session_id
    )
  )
}

#' Print an nRouter client without disclosing its key
#'
#' R's default list printer shows every element, so an interactive
#' \code{client} or a \code{print(client)} would display the full API key — a
#' credential that spends real credits, leaked by an ordinary session
#' transcript. Only the prefix and last four characters are shown.
#'
#' @param x An \code{nrouter_client}.
#' @param ... Ignored.
#' @return \code{x}, invisibly.
#' @export
print.nrouter_client <- function(x, ...) {
  key <- x$api_key
  tail4 <- substr(key, max(1, nchar(key) - 3), nchar(key))
  cat("<nrouter_client>\n")
  cat("  base_url:", x$base_url, "\n")
  cat("  api_key: ", paste0(nrouter_key_prefix(), "...", tail4), "\n")
  invisible(x)
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
  param <- if (is.list(node) && is.character(node$param)) node$param else NULL
  type <- if (is.list(node) && is.character(node$type)) node$type else NULL

  nrouter_condition(
    message      = message,
    code         = code,
    status       = status,
    request_id   = meta$request_id,
    limit_source = meta$limit_source,
    auth_reason  = meta$auth_reason,
    retry_after  = meta$retry_after,
    param        = param,
    type         = type
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
  auth <- do.call(httr::add_headers, nrouter_request_headers(client))

  deadlines <- nrouter_request_config(client)

  response <- tryCatch(
    if (identical(method, "GET")) {
      httr::GET(url, auth, deadlines)
    } else {
      httr::POST(
        url, auth, httr::content_type_json(), deadlines,
        body = jsonlite::toJSON(body, auto_unbox = TRUE, null = "null")
      )
    },
    error = function(e) stop(nrouter_transport_condition(conditionMessage(e)))
  )

  meta <- nrouter_meta(as.list(httr::headers(response)))
  status <- httr::status_code(response)
  parse_failed <- FALSE
  parsed <- tryCatch(
    httr::content(response, as = "parsed", type = "application/json"),
    error = function(e) {
      parse_failed <<- TRUE
      list()
    }
  )

  if (status >= 200 && status < 300) {
    # A 2xx that is not JSON is a REAL RESPONSE you were billed for —
    # /v1/audio/speech returns audio, video content returns bytes,
    # stream=TRUE returns SSE. Parsing those as JSON yields an empty list, so
    # the caller pays and receives nothing while the call reports success.
    # Refuse loudly instead.
    content_type <- tolower(paste(httr::http_type(response), collapse = ""))
    if (!grepl("json", content_type, fixed = TRUE)) {
      stop(nrouter_transport_condition(paste0(
        "nRouter returned ", status, " with content-type '", content_type,
        "', which is not JSON. Use nrouter_bytes() for binary or streaming ",
        "endpoints (/v1/audio/speech, /v1/videos/{id}/content, or stream = TRUE); ",
        "the JSON helpers would report success with an empty body."
      )))
    }
    # A 2xx whose JSON does not parse is NOT an empty response — it is a
    # truncated or corrupted one, for a request that was billed. Returning an
    # empty list here reports success with nothing in it.
    if (parse_failed) {
      stop(nrouter_transport_condition(paste0(
        "nRouter returned ", status, " with unparseable JSON; the request was ",
        "billed but the body did not arrive intact."
      )))
    }
    return(list(body = parsed, meta = meta, status_code = status))
  }
  stop(nrouter_error_from_payload(status, parsed, meta))
}

#' Raw bytes plus metadata, for the endpoints that do not return JSON
#'
#' \code{/v1/audio/speech} returns audio, \code{/v1/videos/{id}/content}
#' returns a video, and \code{stream = TRUE} returns SSE. The JSON helpers
#' refuse those rather than handing back an empty body for a request you were
#' billed for; this is the function that returns them.
#'
#' @param client An \code{nrouter_client}.
#' @param path Path under the gateway's \code{/v1} root.
#' @param body Named list to send as JSON, or \code{NULL} for a GET.
#' @return A list with \code{bytes}, \code{meta} and \code{status_code}.
#' @export
nrouter_bytes <- function(client, path, body = NULL) {
  url <- paste0(client$base_url, "/", sub("^/+", "", path))
  auth <- do.call(httr::add_headers, nrouter_request_headers(client))

  # A STALL ceiling, not a whole-request one: generated audio and video are
  # large, and a whole-request timeout truncates a download already billed.
  deadlines <- nrouter_transfer_config(client)

  response <- tryCatch(
    if (is.null(body)) {
      httr::GET(url, auth, deadlines)
    } else {
      httr::POST(url, auth, httr::content_type_json(), deadlines,
                 body = jsonlite::toJSON(body, auto_unbox = TRUE, null = "null"))
    },
    error = function(e) stop(nrouter_transport_condition(conditionMessage(e)))
  )

  meta <- nrouter_meta(as.list(httr::headers(response)))
  status <- httr::status_code(response)
  if (status >= 200 && status < 300) {
    return(list(bytes = httr::content(response, as = "raw"),
                meta = meta, status_code = status))
  }
  parsed <- tryCatch(
    httr::content(response, as = "parsed", type = "application/json"),
    error = function(e) list()
  )
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

# Build the path for one named gateway operation. Keeping dynamic IDs here
# makes every public wrapper use the same segment-only escaping rule.
nrouter_endpoint_path <- function(operation, id = NULL) {
  segment <- function(value) utils::URLencode(value, reserved = TRUE)
  model_id <- function(value) {
    parts <- strsplit(value, "/", fixed = TRUE)[[1]]
    paste(vapply(parts, segment, character(1)), collapse = "/")
  }
  switch(
    operation,
    completions = "/completions",
    images_generations = "/images/generations",
    count_tokens = "/messages/count_tokens",
    model = paste0("/models/", model_id(id)),
    create_video = "/videos",
    retrieve_video = paste0("/videos/", segment(id)),
    audio_speech = "/audio/speech",
    download_video_content = paste0("/videos/", segment(id), "/content"),
    stop(nrouter_configuration_condition(paste("Unknown gateway operation:", operation)))
  )
}

#' POST /completions — the legacy text-completions wire
#' @inheritParams nrouter_chat_completions
#' @return A list with \code{body}, \code{meta} and \code{status_code}.
#' @export
nrouter_completions <- function(client, body) {
  nrouter_request(client, nrouter_endpoint_path("completions"), body)
}

#' POST /embeddings
#' @inheritParams nrouter_chat_completions
#' @return A list with \code{body}, \code{meta} and \code{status_code}.
#' @export
nrouter_embeddings <- function(client, body) {
  nrouter_request(client, "/embeddings", body)
}

#' Normalize an Anthropic Messages request payload
#'
#' - Extracts system/developer turns from \code{messages} into top-level \code{system}
#' - Maps \code{max_completion_tokens} to \code{max_tokens} (with fallback to 4096)
#' - Normalizes \code{stop} to \code{stop_sequences} list of strings
#'
#' @param body A list representing the request body.
#' @return A normalized list suitable for POST /messages.
#' @export
nrouter_normalize_anthropic_messages <- function(body) {
  if (!is.list(body)) {
    return(body)
  }
  out <- body

  if ("messages" %in% names(out) && is.list(out$messages)) {
    cleaned <- list()
    system_chunks <- character(0)

    if ("system" %in% names(out) && is.character(out$system) && any(nzchar(out$system))) {
      system_chunks <- c(system_chunks, out$system[nzchar(out$system)])
    }

    for (turn in out$messages) {
      if (is.list(turn)) {
        role <- tolower(as.character(turn$role %||% ""))
        if (role %in% c("system", "developer")) {
          content <- turn$content
          if (is.character(content) && any(nzchar(content))) {
            system_chunks <- c(system_chunks, content[nzchar(content)])
          } else if (is.list(content)) {
            for (part in content) {
              if (is.list(part) && identical(part$type, "text")) {
                txt <- as.character(part$text %||% "")
                if (nzchar(txt)) {
                  system_chunks <- c(system_chunks, txt)
                }
              }
            }
          }
          next
        }
      }
      cleaned[[length(cleaned) + 1]] <- turn
    }

    out$messages <- cleaned
    if (length(system_chunks) > 0) {
      out$system <- paste(system_chunks, collapse = "\n\n")
    }
  }

  if ("max_completion_tokens" %in% names(out)) {
    max_comp <- out$max_completion_tokens
    out$max_completion_tokens <- NULL
    if (!("max_tokens" %in% names(out))) {
      out$max_tokens <- max_comp
    }
  }
  if (!("max_tokens" %in% names(out))) {
    out$max_tokens <- 4096L
  }

  if ("stop" %in% names(out)) {
    stop_val <- out$stop
    out$stop <- NULL
    if (!("stop_sequences" %in% names(out))) {
      if (is.character(stop_val)) {
        non_empty <- stop_val[nzchar(stop_val)]
        if (length(non_empty) > 0) {
          out$stop_sequences <- as.list(non_empty)
        }
      } else if (is.list(stop_val)) {
        non_empty <- list()
        for (item in stop_val) {
          if (is.character(item) && any(nzchar(item))) {
            for (s in item[nzchar(item)]) {
              non_empty[[length(non_empty) + 1]] <- s
            }
          }
        }
        if (length(non_empty) > 0) {
          out$stop_sequences <- non_empty
        }
      }
    }
  }

  out
}

#' POST /messages (the Anthropic wire format the gateway also serves)
#' @inheritParams nrouter_chat_completions
#' @return A list with \code{body}, \code{meta} and \code{status_code}.
#' @export
nrouter_messages <- function(client, body) {
  body <- nrouter_normalize_anthropic_messages(body)
  nrouter_request(client, "/messages", body)
}

#' POST /responses
#' @inheritParams nrouter_chat_completions
#' @return A list with \code{body}, \code{meta} and \code{status_code}.
#' @export
nrouter_responses <- function(client, body) {
  nrouter_request(client, "/responses", body)
}

#' POST /images/generations
#' @inheritParams nrouter_chat_completions
#' @return A list with \code{body}, \code{meta} and \code{status_code}.
#' @export
nrouter_images_generations <- function(client, body) {
  nrouter_request(client, nrouter_endpoint_path("images_generations"), body)
}

#' POST /messages/count_tokens — counts input without generating
#' @inheritParams nrouter_chat_completions
#' @return A list with \code{body}, \code{meta} and \code{status_code}.
#' @export
nrouter_count_tokens <- function(client, body) {
  nrouter_request(client, nrouter_endpoint_path("count_tokens"), body)
}

#' Send a multipart request to the nRouter gateway
#'
#' multipart/form-data, not JSON: \code{/v1/audio/transcriptions} and
#' \code{/v1/audio/translations} require a binary \code{file} part, so the JSON
#' helpers cannot reach those endpoints at all.
#'
#' @param client An \code{nrouter_client}.
#' @param path Path under the gateway's \code{/v1} root.
#' @param file_path Path to the file to upload. Its EXTENSION is load-bearing —
#'   the upstream providers pick their decoder from it.
#' @param fields Named list of additional form fields, e.g. \code{model}.
#' @return A list with \code{body}, \code{meta} and \code{status_code}.
#' @export
nrouter_multipart <- function(client, path, file_path, fields = list()) {
  url <- paste0(client$base_url, "/", sub("^/+", "", path))
  auth <- do.call(httr::add_headers, nrouter_request_headers(client))
  body <- c(fields, list(file = httr::upload_file(file_path)))

  response <- tryCatch(
    httr::POST(url, auth, nrouter_request_config(client),
               body = body, encode = "multipart"),
    error = function(e) stop(nrouter_transport_condition(conditionMessage(e)))
  )

  meta <- nrouter_meta(as.list(httr::headers(response)))
  status <- httr::status_code(response)
  parse_failed <- FALSE
  parsed <- tryCatch(
    httr::content(response, as = "parsed", type = "application/json"),
    error = function(e) {
      parse_failed <<- TRUE
      list()
    }
  )
  if (status >= 200 && status < 300) {
    # Same rule as nrouter_request(): a 2xx whose JSON does not parse is a
    # truncated response for a request that was BILLED, not an empty one.
    if (parse_failed) {
      stop(nrouter_transport_condition(paste0(
        "nRouter returned ", status, " with unparseable JSON; the request was ",
        "billed but the body did not arrive intact."
      )))
    }
    return(list(body = parsed, meta = meta, status_code = status))
  }
  stop(nrouter_error_from_payload(status, parsed, meta))
}

#' POST /audio/transcriptions - Whisper-style speech to text
#' @inheritParams nrouter_multipart
#' @return A list with \code{body}, \code{meta} and \code{status_code}.
#' @export
nrouter_audio_transcriptions <- function(client, file_path, fields = list()) {
  nrouter_multipart(client, "/audio/transcriptions", file_path, fields)
}

#' POST /audio/translations - speech in any language to English text
#' @inheritParams nrouter_multipart
#' @return A list with \code{body}, \code{meta} and \code{status_code}.
#' @export
nrouter_audio_translations <- function(client, file_path, fields = list()) {
  nrouter_multipart(client, "/audio/translations", file_path, fields)
}

#' POST /audio/speech — generated audio bytes plus response metadata
#' @inheritParams nrouter_chat_completions
#' @return A list with \code{bytes}, \code{meta} and \code{status_code}.
#' @export
nrouter_audio_speech <- function(client, body) {
  nrouter_bytes(client, nrouter_endpoint_path("audio_speech"), body)
}

#' GET /models — what this key is allowed to route to
#' @param client An \code{nrouter_client}.
#' @return A list with \code{body}, \code{meta} and \code{status_code}.
#' @export
nrouter_models <- function(client) {
  nrouter_request(client, "/models")
}

#' GET /models/(model_id)
#' @param client An \code{nrouter_client}.
#' @param model_id Model identifier. It is encoded as one URL path segment.
#' @return A list with \code{body}, \code{meta} and \code{status_code}.
#' @export
nrouter_model <- function(client, model_id) {
  nrouter_request(client, nrouter_endpoint_path("model", model_id))
}

#' POST /videos — starts a video generation job
#' @inheritParams nrouter_chat_completions
#' @return A list with \code{body}, \code{meta} and \code{status_code}.
#' @export
nrouter_create_video <- function(client, body) {
  nrouter_request(client, nrouter_endpoint_path("create_video"), body)
}

#' GET /videos/(id) — polls a video generation job
#' @param client An \code{nrouter_client}.
#' @param video_id Video job identifier. It is encoded as one URL path segment.
#' @return A list with \code{body}, \code{meta} and \code{status_code}.
#' @export
nrouter_retrieve_video <- function(client, video_id) {
  nrouter_request(client, nrouter_endpoint_path("retrieve_video", video_id))
}

#' GET /videos/(id)/content — downloads generated video bytes
#' @inheritParams nrouter_retrieve_video
#' @return A list with \code{bytes}, \code{meta} and \code{status_code}.
#' @export
nrouter_download_video_content <- function(client, video_id) {
  nrouter_bytes(client, nrouter_endpoint_path("download_video_content", video_id))
}

#' Send a chat completion request (convenience wrapper)
#'
#' Kept as the package's original one-call entry point. Prefer
#' \code{nrouter_chat_completions()} when you need the response metadata.
#'
#' @param messages List of message objects, e.g.
#'   \code{list(list(role = "user", content = "Hello!"))}.
#' @param model Model name. The default MUST be a model the gateway serves on
#'   \code{/v1/chat/completions}, because that is the only wire this wrapper
#'   posts to. The gateway resolves a provider endpoint PER WIRE and answers 404
#'   \code{model_unavailable_on_route} when the provider declares none, so an
#'   Anthropic id (Messages-only) was a 404 out of the box for anyone calling
#'   \code{nrouter_chat(messages)} without naming a model. Pinned by
#'   \code{tests/testthat/test-contract.R} and \code{conformance/source_defaults.py}.
#' @param api_key nRouter API key. Defaults to \code{NROUTER_API_KEY}.
#' @param base_url Gateway base URL.
#' @return The parsed JSON response as an R list.
#' @export
nrouter_chat <- function(messages, model = "gpt-5.4-mini", api_key = NULL,
                         base_url = nrouter_default_base_url()) {
  client <- nrouter_client(api_key = api_key, base_url = base_url)
  nrouter_chat_completions(client, list(model = model, messages = messages))$body
}

#' Build an incremental server-sent event parser
#'
#' The parser is public for advanced transports and deterministic testing. Most
#' callers should use one of the named streaming helpers.
#'
#' @param on_chunk Function called with each decoded event. Return \code{FALSE}
#'   to cancel the request early.
#' @return A list with \code{feed(raw)} and \code{finish()} functions.
#' @export
nrouter_sse_parser <- function(on_chunk) {
  if (!is.function(on_chunk)) {
    stop(nrouter_configuration_condition("on_chunk must be a function."))
  }
  buffer <- raw()
  terminated <- FALSE

  boundary <- function(bytes) {
    n <- length(bytes)
    if (n < 2L) return(NULL)
    lf <- which(bytes[-n] == as.raw(10L) & bytes[-1L] == as.raw(10L))
    cr <- which(bytes[-n] == as.raw(13L) & bytes[-1L] == as.raw(13L))
    crlf <- if (n >= 4L) {
      which(bytes[seq_len(n - 3L)] == as.raw(13L) &
            bytes[2L:(n - 2L)] == as.raw(10L) &
            bytes[3L:(n - 1L)] == as.raw(13L) &
            bytes[4L:n] == as.raw(10L))
    } else integer()
    starts <- c(if (length(lf)) lf[[1L]] else integer(),
                if (length(cr)) cr[[1L]] else integer(),
                if (length(crlf)) crlf[[1L]] else integer())
    if (!length(starts)) return(NULL)
    start <- min(starts)
    delimiter_len <- if (start %in% crlf) 4L else 2L
    list(start = start, end = start + delimiter_len - 1L)
  }

  delta_from <- function(data) {
    if (is.character(data$delta) && length(data$delta)) return(data$delta[[1L]])
    if (is.list(data$delta) && is.character(data$delta$text)) {
      return(data$delta$text[[1L]])
    }
    choice <- if (is.list(data$choices) && length(data$choices)) data$choices[[1L]] else NULL
    if (is.list(choice) && is.character(choice$text)) return(choice$text[[1L]])
    if (is.list(choice$delta) && is.character(choice$delta$content)) {
      return(choice$delta$content[[1L]])
    }
    ""
  }

  dispatch <- function(frame) {
    clean_frame <- gsub("\r\n", "\n", frame, fixed = TRUE)
    clean_frame <- gsub("\r", "\n", clean_frame, fixed = TRUE)
    lines <- strsplit(clean_frame, "\n", fixed = TRUE)[[1L]]
    event <- ""
    data_lines <- character()
    for (line in lines) {
      if (!nzchar(line) || startsWith(line, ":")) next
      colon <- regexpr(":", line, fixed = TRUE)[[1L]]
      name <- if (colon < 0L) line else substr(line, 1L, colon - 1L)
      value <- if (colon < 0L) "" else substr(line, colon + 1L, nchar(line))
      value <- sub("^ ", "", value)
      if (identical(name, "event")) event <- value
      if (identical(name, "data")) data_lines <- c(data_lines, value)
    }
    if (!length(data_lines)) return(invisible(NULL))
    encoded <- trimws(paste(data_lines, collapse = "\n"))
    if (!nzchar(encoded)) return(invisible(NULL))
    if (identical(encoded, "[DONE]")) {
      terminated <<- TRUE
      return(invisible(NULL))
    }
    data <- tryCatch(
      jsonlite::fromJSON(encoded, simplifyVector = FALSE),
      error = function(e) {
        if (identical(event, "error")) {
          stop(nrouter_condition(encoded, code = "gateway_error", status = 200L))
        }
        NULL
      }
    )
    if (is.null(data) || !is.list(data)) {
      return(invisible(NULL))
    }
    if (identical(event, "error") || is.list(data$error)) {
      node <- if (is.list(data$error)) data$error else data
      code <- if (is.character(node$code)) node$code[[1L]] else NULL
      type <- if (is.character(node$type)) node$type[[1L]] else NULL
      if (is.null(code) && !is.null(type) && type %in% names(NROUTER_ERROR_CLASSES)) {
        code <- type
      }
      message <- if (is.character(node$message)) node$message[[1L]] else "nRouter stream failed"
      param <- if (is.character(node$param)) node$param[[1L]] else NULL
      stop(nrouter_condition(message, code = code, status = 200L, param = param, type = type))
    }
    type <- if (is.character(data$type)) data$type[[1L]] else NULL
    if (!is.null(type) && type %in% c("message_stop", "response.completed")) {
      terminated <<- TRUE
      return(invisible(NULL))
    }
    keep_going <- on_chunk(list(event = event, delta = delta_from(data), data = data))
    if (identical(keep_going, FALSE)) {
      stop(structure(list(message = "stream cancelled", call = NULL),
                     class = c("nrouter_stream_cancel", "condition")))
    }
    invisible(NULL)
  }

  feed <- function(bytes) {
    if (terminated || !length(bytes)) return(invisible(NULL))
    buffer <<- c(buffer, bytes)
    repeat {
      split <- boundary(buffer)
      if (is.null(split)) break
      frame <- if (split$start > 1L) rawToChar(buffer[seq_len(split$start - 1L)]) else ""
      buffer <<- if (split$end < length(buffer)) buffer[(split$end + 1L):length(buffer)] else raw()
      dispatch(frame)
      if (terminated) break
    }
    invisible(NULL)
  }

  finish <- function() {
    if (!terminated && length(buffer)) {
      frame <- rawToChar(buffer)
      buffer <<- raw()
      dispatch(frame)
    }
    if (!terminated) {
      stop(nrouter_transport_condition(
        "The stream ended before its terminal event."
      ))
    }
    invisible(TRUE)
  }
  list(feed = feed, finish = finish)
}

#' Stream a JSON request from the nRouter gateway
#'
#' @param client An \code{nrouter_client}.
#' @param path Path under the gateway's \code{/v1} root.
#' @param body Named list forming the request body. \code{stream = TRUE} is set
#'   in a copy and the caller's list is not mutated.
#' @param on_chunk Function called incrementally with \code{event}, \code{delta},
#'   and provider-native \code{data}. Return \code{FALSE} to cancel early.
#' @return A list with final \code{meta}, \code{status_code}, and
#'   \code{cancelled}.
#' @export
nrouter_stream <- function(client, path, body, on_chunk) {
  url <- paste0(client$base_url, "/", sub("^/+", "", path))
  payload <- body
  payload$stream <- TRUE
  handle <- curl::new_handle()
  do.call(
    curl::handle_setheaders,
    c(list(handle), nrouter_request_headers(client, list(
      Accept = "text/event-stream",
      "Content-Type" = "application/json"
    )))
  )
  # Same deadlines as the httr paths, set on the raw handle because this one
  # bypasses httr. No `timeout`: an SSE stream that is producing tokens is a
  # WORKING stream however long it runs, and cutting it off discards tokens the
  # caller has already paid for. `low_speed_limit`/`low_speed_time` bound the
  # failure that matters -- a stream that has stopped producing bytes.
  curl::handle_setopt(
    handle,
    customrequest = "POST",
    connecttimeout = nrouter_connect_timeout_seconds(client),
    low_speed_limit = 1,
    low_speed_time = nrouter_stream_idle_seconds(client),
    postfields = charToRaw(jsonlite::toJSON(
      payload, auto_unbox = TRUE, null = "null"
    ))
  )
  parser <- nrouter_sse_parser(on_chunk)
  buffered <- raw()
  cancelled <- FALSE
  failure <- NULL

  info <- tryCatch(
    curl::curl_fetch_stream(url, function(bytes) {
      current <- curl::handle_data(handle)
      if (current$status_code >= 200L && current$status_code < 300L &&
          identical(current$type, "text/event-stream")) {
        parser$feed(bytes)
      } else {
        buffered <<- c(buffered, bytes)
      }
    }, handle = handle),
    nrouter_stream_cancel = function(e) {
      cancelled <<- TRUE
      curl::handle_data(handle)
    },
    nrouter_error = function(e) {
      failure <<- e
      curl::handle_data(handle)
    },
    error = function(e) {
      failure <<- nrouter_transport_condition(conditionMessage(e))
      curl::handle_data(handle)
    }
  )
  if (!is.null(failure)) stop(failure)

  headers <- curl::parse_headers_list(info$headers)
  meta <- nrouter_meta(headers)
  status <- info$status_code
  if (status < 200L || status >= 300L) {
    parsed <- tryCatch(
      jsonlite::fromJSON(rawToChar(buffered), simplifyVector = FALSE),
      error = function(e) list()
    )
    stop(nrouter_error_from_payload(status, parsed, meta))
  }
  if (!identical(info$type, "text/event-stream")) {
    stop(nrouter_transport_condition(paste0(
      "nRouter returned ", status, " with content-type '", info$type,
      "', which is not an SSE stream."
    )))
  }
  if (!cancelled) parser$finish()
  list(meta = meta, status_code = status, cancelled = cancelled)
}

#' Stream POST /chat/completions
#' @inheritParams nrouter_stream
#' @export
nrouter_chat_completions_stream <- function(client, body, on_chunk) {
  nrouter_stream(client, "/chat/completions", body, on_chunk)
}

#' Stream POST /completions
#' @inheritParams nrouter_stream
#' @export
nrouter_completions_stream <- function(client, body, on_chunk) {
  nrouter_stream(client, "/completions", body, on_chunk)
}

#' Stream POST /messages
#' @inheritParams nrouter_stream
#' @export
nrouter_messages_stream <- function(client, body, on_chunk) {
  body <- nrouter_normalize_anthropic_messages(body)
  nrouter_stream(client, "/messages", body, on_chunk)
}

#' Stream POST /responses
#' @inheritParams nrouter_stream
#' @export
nrouter_responses_stream <- function(client, body, on_chunk) {
  nrouter_stream(client, "/responses", body, on_chunk)
}
