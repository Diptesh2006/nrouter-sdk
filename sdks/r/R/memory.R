#' Conversation Memory for nRouter
#'
#' Client-side conversation memory management with tenancy validation and sliding window pruning.
#'
#' @name nrouter-memory
NULL

TENANCY_KEYS <- c("organizationid", "orgid", "teamid", "userid", "nrouterorg")
VALID_ROLES <- c("system", "user", "assistant", "tool", "developer")

normalize_key <- function(key) {
  gsub("[-_]", "", tolower(key))
}

#' Validate a chat message
#'
#' @param message A named list representing a message.
#' @param context Context string for error reporting.
#' @return The validated message.
#' @export
nrouter_validate_message <- function(message, context = "nrouter_memory_add") {
  if (!is.list(message)) {
    stop(nrouter_configuration_condition(paste0(context, ": message must be a list")))
  }
  keys <- names(message)
  for (k in keys) {
    if (normalize_key(k) %in% TENANCY_KEYS) {
      stop(nrouter_configuration_condition(
        paste0(context, ": message contains forbidden tenancy key '", k, "'")
      ))
    }
  }
  role <- message$role
  if (is.null(role) || !is.character(role) || !(role %in% VALID_ROLES)) {
    stop(nrouter_configuration_condition(
      paste0(context, ": message must contain a valid role (system, user, assistant, tool, developer)")
    ))
  }
  content <- message$content
  tool_calls <- message$tool_calls
  has_tool_calls <- !is.null(tool_calls) && is.list(tool_calls) && length(tool_calls) > 0
  if (is.null(content)) {
    if (!has_tool_calls && role != "assistant") {
      stop(nrouter_configuration_condition(
        paste0(context, ": content must be a character string or list of content parts")
      ))
    }
  } else if (!is.character(content) && !is.list(content)) {
    stop(nrouter_configuration_condition(
      paste0(context, ": content must be a character string or list of content parts")
    ))
  }
  message
}

#' Sliding window pruning of message history
#'
#' @param messages List of messages.
#' @param max_messages Maximum messages to retain.
#' @param preserve_system Whether to preserve index 1 system/developer message.
#' @return Pruned list of messages.
#' @export
nrouter_sliding_window <- function(messages, max_messages = NULL, preserve_system = TRUE) {
  if (is.null(max_messages)) {
    return(messages)
  }
  if (!is.numeric(max_messages) || max_messages <= 0) {
    return(list())
  }
  limit <- as.integer(max_messages)
  n <- length(messages)
  if (n <= limit) {
    return(messages)
  }
  if (isTRUE(preserve_system) && n > 0) {
    first_role <- messages[[1]]$role
    if (!is.null(first_role) && (first_role == "system" || first_role == "developer")) {
      if (limit == 1L) {
        return(list(messages[[n]]))
      }
      tail_count <- limit - 1L
      start_idx <- n - tail_count + 1L
      return(c(list(messages[[1]]), messages[start_idx:n]))
    }
  }
  start_idx <- n - limit + 1L
  messages[start_idx:n]
}

#' In-memory array store for conversation messages
#'
#' @param seed Optional initial list of messages.
#' @return An environment with load and save functions.
#' @export
nrouter_create_array_store <- function(seed = list()) {
  store <- new.env(parent = emptyenv())
  store$messages <- seed

  load <- function() {
    store$messages
  }

  save <- function(messages) {
    store$messages <- messages
  }

  list(load = load, save = save)
}

#' Create conversation memory
#'
#' @param store Optional storage backend (defaults to in-memory array store).
#' @param max_messages Optional maximum messages limit for windowing.
#' @param preserve_system Whether to preserve system prompt during windowing.
#' @return An environment / list of memory methods (add, messages, clear).
#' @export
nrouter_create_memory <- function(store = NULL, max_messages = NULL, preserve_system = TRUE) {
  if (is.null(store)) {
    store <- nrouter_create_array_store()
  }

  add <- function(message) {
    clean <- nrouter_validate_message(message, context = "nrouter_memory$add")
    current <- store$load()
    current[[length(current) + 1L]] <- clean
    store$save(current)
    invisible(NULL)
  }

  messages <- function(max_msgs = max_messages, preserve_sys = preserve_system) {
    raw <- store$load()
    out <- lapply(seq_along(raw), function(i) {
      nrouter_validate_message(raw[[i]], context = paste0("MemoryStore$load()[[", i, "]]"))
    })
    if (!is.null(max_msgs) && max_msgs > 0) {
      nrouter_sliding_window(out, max_messages = max_msgs, preserve_system = preserve_sys)
    } else {
      out
    }
  }

  clear <- function() {
    store$save(list())
    invisible(NULL)
  }

  list(
    add = add,
    messages = messages,
    clear = clear
  )
}
