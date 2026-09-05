# The gateway contract this SDK must keep, asserted against the values in
# spec/nrouter-sdk-spec.json.

test_that("constants match the spec", {
  expect_equal(nrouter_default_base_url(), "https://api.nrouter.ai/v1")
  expect_equal(nrouter_env_key(), "NROUTER_API_KEY")
  expect_equal(nrouter_key_prefix(), "sk-nrouter-")
})

test_that("nrouter_uses_messages_wire routes correctly", {
  expect_true(nrouter_uses_messages_wire("claude-3-5-sonnet-20241022"))
  expect_true(nrouter_uses_messages_wire("anthropic/claude-3-haiku"))
  expect_true(nrouter_uses_messages_wire("my-model", provider = "anthropic"))
  expect_false(nrouter_uses_messages_wire("gpt-4o"))
  expect_false(nrouter_uses_messages_wire("meta-llama/llama-3"))
})

test_that("every spec header is read", {
  expected <- c(
    "x-nr-request-id", "x-nr-request-cost", "x-nr-cost-status", "x-nr-model",
    "x-nr-input-tokens", "x-nr-output-tokens", "x-nr-total-tokens",
    "x-nr-cache-read-tokens", "x-nr-cache-write-tokens", "x-nr-limit-source",
    "x-nr-auth-reason", "x-nr-response-cache", "x-nr-response-cache-age",
    "x-nr-budget-warning", "x-nr-guardrails"
  )
  expect_length(nrouter_header_names(), 15)
  for (name in expected) {
    expect_true(name %in% nrouter_header_names(), info = name)
  }
})

test_that("each gateway code maps to its condition class", {
  expected <- list(
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
  for (code in names(expected)) {
    cond <- nrouter_condition("boom", code = code)
    expect_true(
      expected[[code]] %in% class(cond),
      info = paste(code, "->", paste(class(cond), collapse = ", "))
    )
    expect_true("nrouter_error" %in% class(cond))
  }
})

test_that("an unknown code is never reclassified", {
  cond <- nrouter_condition("boom", code = "some_future_code")
  expect_true("nrouter_other_error" %in% class(cond))
  expect_false("nrouter_request_error" %in% class(cond))
})

test_that("only transient failures are retryable", {
  for (code in c("rate_limit_exceeded", "service_unavailable", "credit_check_failed")) {
    expect_true(nrouter_is_retryable(nrouter_condition("x", code = code)), info = code)
  }
  for (code in c("invalid_request", "guardrail_blocked", "invalid_api_key",
                 "insufficient_credits", "model_not_found")) {
    expect_false(nrouter_is_retryable(nrouter_condition("x", code = code)), info = code)
  }
  expect_true(nrouter_is_retryable(nrouter_transport_condition("dns")))
  # A local configuration failure is PERMANENT. Marking it retryable makes a
  # caller's retry loop spin forever without ever sending.
  expect_false(nrouter_is_retryable(nrouter_configuration_condition("no key")))
})

test_that("an unpriced response reports no cost rather than zero", {
  meta <- nrouter_meta(list(
    "x-nr-cost-status" = "unpriced",
    "x-nr-request-id"  = "req_1"
  ))
  expect_null(meta$cost)
  expect_false(nrouter_is_priced(meta))
  expect_equal(meta$request_id, "req_1")
})

test_that("a priced response parses its numbers", {
  meta <- nrouter_meta(list(
    "x-nr-request-cost"      = "0.00042",
    "x-nr-cost-status"       = "exact",
    "x-nr-input-tokens"      = "11",
    "x-nr-response-cache"    = "hit",
    "x-nr-response-cache-age" = "7",
    "x-nr-budget-warning"     = "org soft_budget 80.00/100.00",
    "x-nr-guardrails"         = "pass"
  ))
  expect_equal(meta$cost, 0.00042)
  expect_true(nrouter_is_priced(meta))
  expect_equal(meta$input_tokens, 11)
  expect_equal(meta$response_cache, "hit")
  expect_equal(meta$response_cache_age, 7)
  expect_equal(meta$budget_warning, "org soft_budget 80.00/100.00")
  expect_equal(meta$guardrails, "pass")
})

test_that("header lookup is case-insensitive", {
  # httr returns headers lowercased, but a proxy may not.
  meta <- nrouter_meta(list("X-NR-Request-Id" = "req_2"))
  expect_equal(meta$request_id, "req_2")
})

test_that("a key without the prefix is refused before any request", {
  expect_error(nrouter_resolve_api_key("sk-openai-nope"),
               class = "nrouter_configuration_error")
  expect_equal(nrouter_resolve_api_key("sk-nrouter-abc"), "sk-nrouter-abc")
})

test_that("a trailing slash on the base URL is normalised", {
  client <- nrouter_client(api_key = "sk-nrouter-abc", base_url = "https://api.nrouter.ai/v1/")
  expect_equal(client$base_url, "https://api.nrouter.ai/v1")
})

test_that("the error envelope is read nested or bare", {
  meta <- nrouter_meta(list("x-nr-limit-source" = "tpm"))

  nested <- nrouter_error_from_payload(
    429, list(error = list(message = "slow down", code = "tpm_limit_exceeded")), meta
  )
  expect_true("nrouter_rate_limit_error" %in% class(nested))
  expect_equal(nested$code, "tpm_limit_exceeded")
  expect_equal(nested$limit_source, "tpm")

  # A proxy that unwraps `error` must not downgrade a typed error. Assert the
  # CODE, not only the class: the status fallback yields the same class for 429.
  bare <- nrouter_error_from_payload(
    429, list(message = "slow down", code = "tpm_limit_exceeded"), meta
  )
  expect_equal(bare$code, "tpm_limit_exceeded")
})

test_that("a caught nRouter error can be handled by family or by kind", {
  cond <- nrouter_condition("no credits", code = "insufficient_credits", status = 402)
  caught_family <- tryCatch(stop(cond), nrouter_error = function(e) "family")
  caught_kind <- tryCatch(stop(cond), nrouter_credit_error = function(e) "kind")
  expect_equal(caught_family, "family")
  expect_equal(caught_kind, "kind")
})

test_that("a codeless 400 is split on the message", {
  # The gateway's MAIN error path emits {"error":{"type","message"}} with no
  # code, so this is the ordinary shape. Calling every codeless 400 a request
  # error makes nrouter_guardrail_blocked_error unreachable.
  guardrail <- nrouter_condition("blocked by guardrail 'pii'", status = 400)
  expect_true("nrouter_guardrail_blocked_error" %in% class(guardrail))

  malformed <- nrouter_condition("invalid request: bad shape", status = 400)
  expect_true("nrouter_request_error" %in% class(malformed))
  expect_false("nrouter_guardrail_blocked_error" %in% class(malformed))
})

test_that("the real gateway envelope classifies without a code", {
  # Byte-for-byte what GatewayError::into_response emits.
  payload <- list(error = list(type = "gateway_error",
                               message = "blocked by guardrail 'pii'"))
  cond <- nrouter_error_from_payload(400, payload, nrouter_meta(list()))
  expect_null(cond$code)
  expect_true("nrouter_guardrail_blocked_error" %in% class(cond))
})

test_that("a codeless 402 separates a budget ceiling from a shortfall", {
  # Two of the three 402s are budget ceilings, whose fix is the OPPOSITE of a
  # shortfall's: raise the budget, not top up.
  budget <- nrouter_condition("budget exceeded: spend 5.00", status = 402)
  expect_true("nrouter_budget_exceeded_error" %in% class(budget))

  shortfall <- nrouter_condition("insufficient credits: 0.01 available", status = 402)
  expect_true("nrouter_credit_error" %in% class(shortfall))
})

test_that("a codeless 404 is only model_not_found when it names a model", {
  model <- nrouter_condition("model 'x' not found", status = 404)
  expect_true("nrouter_not_found_error" %in% class(model))

  # A missing video job or MCP server is also a 404.
  other <- nrouter_condition("unknown video job", status = 404)
  expect_true("nrouter_other_error" %in% class(other))
  expect_false("nrouter_not_found_error" %in% class(other))
})

test_that("printing a client never discloses its key", {
  # R's default list printer shows every element, so an interactive `client`
  # would display the full key — a credential that spends real credits, leaked
  # by an ordinary session transcript (Rule #5).
  client <- nrouter_client(api_key = "sk-nrouter-SECRET123")
  rendered <- paste(capture.output(print(client)), collapse = "\n")
  expect_false(grepl("SECRET123", rendered, fixed = TRUE))
  expect_true(grepl("sk-nrouter-...T123", rendered, fixed = TRUE))
})

test_that("named helpers cover every remaining gateway operation", {
  expect_equal(nrouter:::nrouter_endpoint_path("completions"), "/completions")
  expect_equal(nrouter:::nrouter_endpoint_path("images_generations"), "/images/generations")
  expect_equal(nrouter:::nrouter_endpoint_path("count_tokens"), "/messages/count_tokens")
  expect_equal(
    nrouter:::nrouter_endpoint_path("model", "provider/model one"),
    "/models/provider/model%20one"
  )
  expect_equal(nrouter:::nrouter_endpoint_path("create_video"), "/videos")
  expect_equal(nrouter:::nrouter_endpoint_path("retrieve_video", "video/one"), "/videos/video%2Fone")
  expect_equal(nrouter:::nrouter_endpoint_path("audio_speech"), "/audio/speech")
  expect_equal(
    nrouter:::nrouter_endpoint_path("download_video_content", "video/one"),
    "/videos/video%2Fone/content"
  )
})

test_that("the nrouter_chat default model is callable on the wire it posts to", {
  # `nrouter_chat()` calls `nrouter_chat_completions()`, which posts to
  # `/chat/completions` unconditionally — this package has no per-model wire
  # switch. The gateway resolves a provider endpoint PER WIRE, and a provider
  # declaring no endpoint for a wire answers 404 `model_unavailable_on_route`:
  # the model exists, just not on the route it was asked for. Anthropic declares
  # Messages only, so an Anthropic-family default here is a 404 for a brand-new
  # customer who called `nrouter_chat(messages)` with no model at all. Derive the
  # gateway side rather than trusting this comment:
  #
  #   cd nrouter-rust-gateway
  #   grep -n "fn endpoints" -A 12 src/sdk/providers/anthropic/transformation.rs
  #   # => messages: Some(...), responses: NULL, chat_completions: NULL
  default_model <- formals(nrouter_chat)$model
  expect_type(default_model, "character")
  expect_false(
    grepl("^(anthropic/|claude-)", default_model),
    info = paste0(
      default_model, " is an Anthropic-family id, served on /v1/messages ONLY, ",
      "but nrouter_chat() posts to /v1/chat/completions."
    )
  )
})
