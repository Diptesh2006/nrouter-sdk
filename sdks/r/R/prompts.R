#' Managed Prompts for nRouter
#'
#' Helper functions for prompt template selection and safe variable interpolation.
#'
#' @name nrouter-prompts
NULL

PROMPT_TEMPLATE_ID_FIELD <- "nrouter_prompt_template_id"
PROMPT_VARIABLES_FIELD <- "nrouter_prompt_variables"
PROMPT_WIRE_FIELDS <- c(PROMPT_TEMPLATE_ID_FIELD, PROMPT_VARIABLES_FIELD)
SYSTEM_VARIABLE_NAMES <- c("org_name", "model", "timestamp", "user_id")

#' Select a prompt template
#'
#' @param template_id The template identifier.
#' @param variables Optional named list of variable values.
#' @return A prompt selection object.
#' @export
nrouter_prompt_template <- function(template_id, variables = list()) {
  if (missing(template_id) || is.null(template_id) || !is.character(template_id) || nchar(trimws(template_id)) == 0) {
    stop(nrouter_configuration_condition("prompt_template requires a non-empty template id"))
  }
  list(
    template_id = trimws(template_id),
    variables = as.list(variables)
  )
}

#' Select prompt variables for the assigned template
#'
#' @param variables Named list of variable values.
#' @return A prompt selection object.
#' @export
nrouter_prompt_variables <- function(variables = list()) {
  list(
    template_id = NULL,
    variables = as.list(variables)
  )
}

#' Merge additional variables into a prompt selection
#'
#' @param selection Existing prompt selection.
#' @param variables Named list of new variables.
#' @return A new prompt selection with merged variables.
#' @export
nrouter_with_variables <- function(selection, variables = list()) {
  merged <- selection$variables
  new_vars <- as.list(variables)
  for (k in names(new_vars)) {
    merged[[k]] <- new_vars[[k]]
  }
  list(
    template_id = selection$template_id,
    variables = merged
  )
}

#' Check for collisions with gateway system variables
#'
#' @param variables Named list of variable values.
#' @return Character vector of conflicting variable names in deterministic order.
#' @export
nrouter_system_variable_conflicts <- function(variables = list()) {
  if (is.null(variables) || length(variables) == 0) {
    return(character(0))
  }
  vars_names <- names(variables)
  conflicts <- character(0)
  for (sys_var in SYSTEM_VARIABLE_NAMES) {
    if (sys_var %in% vars_names) {
      conflicts <- c(conflicts, sys_var)
    }
  }
  conflicts
}

#' Safely render a prompt template by interpolating variables
#'
#' @param template Prompt template string containing `{{variable}}` or `{{ variable }}` tokens.
#' @param variables Named list of variables to substitute.
#' @param strict Logical; if TRUE, error when any variable is missing.
#' @param system_variables Optional named list of system variables that override caller variables.
#' @return The interpolated string.
#' @export
nrouter_render_prompt <- function(template, variables = list(), strict = FALSE, system_variables = list()) {
  if (missing(template) || is.null(template) || length(template) == 0 || nchar(template) == 0) {
    return("")
  }

  pattern <- "\\{\\{\\s*([a-zA-Z0-9_-]+)\\s*\\}\\}"
  m <- gregexpr(pattern, template, perl = TRUE)[[1]]

  if (m[1] == -1) {
    return(template)
  }

  match_lens <- attr(m, "match.length")
  capture_starts <- attr(m, "capture.start")
  capture_lens <- attr(m, "capture.length")

  n_matches <- length(m)
  missing_keys <- character(0)
  out_parts <- character(0)
  last_pos <- 1

  for (i in seq_len(n_matches)) {
    start_pos <- m[i]
    match_len <- match_lens[i]
    cap_start <- capture_starts[i, 1]
    cap_len <- capture_lens[i, 1]

    if (start_pos > last_pos) {
      out_parts <- c(out_parts, substr(template, last_pos, start_pos - 1))
    }

    key <- substr(template, cap_start, cap_start + cap_len - 1)

    if (!is.null(names(system_variables)) && key %in% names(system_variables)) {
      val <- system_variables[[key]]
      out_parts <- c(out_parts, if (is.null(val)) "" else as.character(val))
    } else if (!is.null(names(variables)) && key %in% names(variables)) {
      val <- variables[[key]]
      out_parts <- c(out_parts, if (is.null(val)) "" else as.character(val))
    } else {
      if (isTRUE(strict)) {
        missing_keys <- c(missing_keys, key)
      }
      out_parts <- c(out_parts, substr(template, start_pos, start_pos + match_len - 1))
    }

    last_pos <- start_pos + match_len
  }

  if (last_pos <= nchar(template)) {
    out_parts <- c(out_parts, substr(template, last_pos, nchar(template)))
  }

  if (isTRUE(strict) && length(missing_keys) > 0) {
    stop(nrouter_configuration_condition(
      paste0("Missing required prompt template variables: ", paste(missing_keys, collapse = ", "))
    ))
  }

  paste(out_parts, collapse = "")
}
