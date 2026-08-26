# The gateway contract this SDK must keep, asserted against the values in
# spec/nrouter-sdk-spec.json.

test_that("constants match the spec", {
  expect_equal(nrouter_default_base_url(), "https://api.nrouter.ai/v1")
  expect_equal(nrouter_env_key(), "NROUTER_API_KEY")
  expect_equal(nrouter_key_prefix(), "sk-nrouter-")
})

test_that("every spec header is read", {
  expected <- c(
    "x-nr-request-id", "x-nr-request-cost", "x-nr-cost-status", "x-nr-model",
    "x-nr-input-tokens", "x-nr-output-tokens", "x-nr-total-tokens",
    "x-nr-cache-read-tokens", "x-nr-cache-write-tokens", "x-nr-limit-source",
    "x-nr-auth-reason", "x-nr-response-cache", "x-nr-response-cache-age"
  )
  expect_length(nrouter_header_names(), 13)
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
    "x-nr-response-cache-age" = "7"
  ))
  expect_equal(meta$cost, 0.00042)
  expect_true(nrouter_is_priced(meta))
  expect_equal(meta$input_tokens, 11)
  expect_equal(meta$response_cache, "hit")
  expect_equal(meta$response_cache_age, 7)
})

test_that("header lookup is case-insensitive", {
  # httr returns headers lowercased, but a proxy may not.
  meta <- nrouter_meta(list("X-NR-Request-Id" = "req_2"))
  expect_equal(meta$request_id, "req_2")
})

test_that("a key without the prefix is refused before any request", {
  expect_error(nrouter_resolve_api_key("sk-openai-nope"), class = "nrouter_transport_error")
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
