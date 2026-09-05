#' Claude Sampling and Parameter Policy for nRouter
#'
#' Helper functions for model detection and mutually exclusive sampling parameters.
#'
#' @name nrouter-sampling
NULL

NEUTRAL_TOP_P <- 1.0

#' Check whether a model or provider represents an Anthropic Claude model
#'
#' @param model Model identifier string.
#' @param provider Optional provider name.
#' @return Logical indicating if the model is a Claude model.
#' @export
nrouter_is_claude_model <- function(model, provider = NULL) {
  if (missing(model) || is.null(model) || !is.character(model) || length(model) == 0) {
    return(FALSE)
  }
  m <- tolower(model[1])
  p <- if (!is.null(provider) && is.character(provider) && length(provider) > 0) tolower(provider[1]) else ""

  grepl("claude|haiku|sonnet|opus", m) || grepl("anthropic", p)
}

#' Build sampling parameters with Claude mutual exclusion rules
#'
#' Claude models enforce strict mutual exclusion: setting top_p suppresses temperature.
#'
#' @param advanced Logical indicating if advanced sampling is enabled.
#' @param model Model identifier.
#' @param provider Optional provider identifier.
#' @param temperature Optional temperature parameter.
#' @param top_p Optional top_p parameter.
#' @return Named list of valid sampling parameters.
#' @export
nrouter_build_sampling_params <- function(advanced, model, provider = NULL,
                                          temperature = NULL, top_p = NULL) {
  if (!isTRUE(advanced)) {
    return(list())
  }

  if (!is.null(temperature)) {
    if (!is.numeric(temperature) || length(temperature) != 1 || !is.finite(temperature)) {
      stop(nrouter_configuration_condition("temperature must be a finite number"))
    }
    if (temperature < 0.0) {
      stop(nrouter_configuration_condition(paste0("temperature must be 0 or greater, got ", temperature)))
    }
  }

  if (!is.null(top_p)) {
    if (!is.numeric(top_p) || length(top_p) != 1 || !is.finite(top_p)) {
      stop(nrouter_configuration_condition("top_p must be a finite number"))
    }
    if (top_p < 0.0 || top_p > 1.0) {
      stop(nrouter_configuration_condition(paste0("top_p must be between 0 and 1.0, got ", top_p)))
    }
  }

  top_p_set <- !is.null(top_p) && !isTRUE(all.equal(top_p, NEUTRAL_TOP_P))
  suppress_temp <- top_p_set && nrouter_is_claude_model(model, provider)

  out <- list()
  if (!is.null(temperature) && !suppress_temp) {
    out$temperature <- temperature
  }
  if (!is.null(top_p) && top_p_set) {
    out$top_p <- top_p
  }

  out
}
