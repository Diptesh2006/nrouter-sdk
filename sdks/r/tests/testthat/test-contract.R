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

test_that("nrouter_create_memory stores messages and validates tenancy/roles", {
  mem <- nrouter_create_memory()
  mem$add(list(role = "user", content = "Hello"))
  mem$add(list(role = "assistant", content = "Hi!"))
  msgs <- mem$messages()
  expect_equal(length(msgs), 2L)

  # Rejects tenancy field
  expect_error(
    mem$add(list(role = "user", content = "evil", organization_id = "org_1")),
    class = "nrouter_configuration_error"
  )

  # Rejects unknown role
  expect_error(
    mem$add(list(role = "unknown_role", content = "text")),
    class = "nrouter_configuration_error"
  )

  # Accepts developer and tool roles
  mem$add(list(role = "developer", content = "system instructions"))
  mem$add(list(role = "tool", content = "tool result"))

  # Accepts assistant with tool_calls and null content
  mem$add(list(role = "assistant", content = NULL, tool_calls = list(list(id = "c1"))))

  all_msgs <- mem$messages()
  expect_equal(length(all_msgs), 5L)
  expect_equal(all_msgs[[3]]$role, "developer")
  expect_equal(all_msgs[[4]]$role, "tool")
  expect_equal(all_msgs[[5]]$role, "assistant")

  # Clear
  mem$clear()
  expect_equal(length(mem$messages()), 0L)
})

test_that("nrouter_sliding_window prunes and preserves system prompt", {
  msgs <- list(
    list(role = "system", content = "sys"),
    list(role = "user", content = "1"),
    list(role = "assistant", content = "2"),
    list(role = "user", content = "3"),
    list(role = "assistant", content = "4")
  )

  pruned <- nrouter_sliding_window(msgs, max_messages = 3, preserve_system = TRUE)
  expect_equal(length(pruned), 3L)
  expect_equal(pruned[[1]]$role, "system")
  expect_equal(pruned[[2]]$content, "3")
  expect_equal(pruned[[3]]$content, "4")

  no_preserve <- nrouter_sliding_window(msgs, max_messages = 2, preserve_system = FALSE)
  expect_equal(length(no_preserve), 2L)
  expect_equal(no_preserve[[1]]$content, "3")
  expect_equal(no_preserve[[2]]$content, "4")
})

test_that("nrouter prompt helpers and system variable conflicts", {
  sel <- nrouter_prompt_template("tpl_123", list(customer = "Acme"))
  expect_equal(sel$template_id, "tpl_123")
  expect_equal(sel$variables$customer, "Acme")

  expect_error(nrouter_prompt_template("   "))

  merged <- nrouter_with_variables(sel, list(customer = "Beta", user = "Alice"))
  expect_equal(merged$variables$customer, "Beta")
  expect_equal(merged$variables$user, "Alice")

  conflicts <- nrouter_system_variable_conflicts(list(
    user_id = "u1",
    custom = "val",
    org_name = "orgX",
    timestamp = 123
  ))
  expect_equal(conflicts, c("org_name", "timestamp", "user_id"))
})

test_that("nrouter_render_prompt safely interpolates variables", {
  # 1. Whitespace tolerance & type formatting
  tpl <- "Hello {{name}}! Age: {{  age  }}, active: {{ active }}."
  out <- nrouter_render_prompt(tpl, list(name = "Alice", age = 30, active = TRUE))
  expect_equal(out, "Hello Alice! Age: 30, active: TRUE.")

  # 2. Single pass non-recursive
  tpl2 <- "Value: {{a}}"
  out2 <- nrouter_render_prompt(tpl2, list(a = "{{b}}", b = "final"))
  expect_equal(out2, "Value: {{b}}")

  # 3. Metacharacter safety ($1, escapes)
  tpl3 <- "Price: {{price}}, Path: {{path}}"
  out3 <- nrouter_render_prompt(tpl3, list(price = "$100", path = "C:\\test\\1"))
  expect_equal(out3, "Price: $100, Path: C:\\test\\1")

  # 4. Non-strict preserves missing tokens
  tpl4 <- "Greeting: {{hello}}, missing: {{world}}"
  out4 <- nrouter_render_prompt(tpl4, list(hello = "hi"))
  expect_equal(out4, "Greeting: hi, missing: {{world}}")

  # 5. Strict throws error on missing tokens
  expect_error(nrouter_render_prompt(tpl4, list(hello = "hi"), strict = TRUE))

  # 6. System variables override
  tpl5 <- "Model: {{model}}, User: {{user}}"
  out5 <- nrouter_render_prompt(
    tpl5,
    list(model = "caller-model", user = "alice"),
    system_variables = list(model = "claude-3-7-sonnet")
  )
  expect_equal(out5, "Model: claude-3-7-sonnet, User: alice")
})

test_that("Claude model detection and sampling parameter policy match spec", {
  expect_true(nrouter_is_claude_model("claude-3-5-sonnet"))
  expect_true(nrouter_is_claude_model("anthropic/claude-3-haiku"))
  expect_true(nrouter_is_claude_model("haiku-20240307"))
  expect_true(nrouter_is_claude_model("sonnet-3.7"))
  expect_true(nrouter_is_claude_model("opus-4"))
  expect_true(nrouter_is_claude_model("my-model", "anthropic"))
  expect_false(nrouter_is_claude_model("gpt-4o"))
  expect_false(nrouter_is_claude_model("meta-llama/llama-3"))

  # Non-advanced returns empty
  expect_equal(nrouter_build_sampling_params(FALSE, "claude-3-5-sonnet", temperature = 0.7), list())

  # Claude suppresses temperature when top_p is set and non-neutral
  params <- nrouter_build_sampling_params(TRUE, "claude-3-5-sonnet", temperature = 0.7, top_p = 0.9)
  expect_null(params$temperature)
  expect_equal(params$top_p, 0.9)

  # Claude keeps temperature when top_p is neutral (1.0)
  params_neutral <- nrouter_build_sampling_params(TRUE, "claude-3-5-sonnet", temperature = 0.7, top_p = 1.0)
  expect_equal(params_neutral$temperature, 0.7)
  expect_null(params_neutral$top_p)

  # Non-Claude keeps both
  params_gpt <- nrouter_build_sampling_params(TRUE, "gpt-4o", temperature = 0.7, top_p = 0.9)
  expect_equal(params_gpt$temperature, 0.7)
  expect_equal(params_gpt$top_p, 0.9)
})

test_that("nrouter_normalize_anthropic_messages normalizes payload correctly", {
  body <- list(
    model = "claude-3-5-sonnet",
    system = "Base prompt.",
    max_completion_tokens = 1000L,
    stop = "STOP_HERE",
    messages = list(
      list(role = "system", content = "Extra system instructions."),
      list(role = "user", content = "Hello Claude")
    )
  )

  norm <- nrouter_normalize_anthropic_messages(body)

  expect_equal(norm$system, "Base prompt.\n\nExtra system instructions.")
  expect_equal(norm$max_tokens, 1000L)
  expect_false("max_completion_tokens" %in% names(norm))
  expect_equal(norm$stop_sequences, list("STOP_HERE"))
  expect_false("stop" %in% names(norm))
  expect_null(norm[["stop"]])
  expect_equal(length(norm$messages), 1L)
  expect_equal(norm$messages[[1]]$role, "user")
  expect_equal(norm$messages[[1]]$content, "Hello Claude")
})

test_that("media audio validation and video polling match spec", {
  for (fmt in VALID_AUDIO_FORMATS) {
    expect_equal(nrouter_validate_audio_format(fmt), fmt)
    expect_equal(nrouter_validate_audio_format(paste0("  ", toupper(fmt), "  ")), fmt)
  }
  expect_error(nrouter_validate_audio_format("unsupported_fmt"), class = "nrouter_configuration_error")
  expect_error(nrouter_validate_audio_format(""), class = "nrouter_configuration_error")
  expect_error(nrouter_validate_audio_format(123), class = "nrouter_configuration_error")

  expect_error(nrouter_wait_for_video(list(), ""), class = "nrouter_configuration_error")
})

test_that("cleartext is limited to loopback development gateways and rejects credentials", {
  for (allowed in c(
    "http://127.0.0.1:4000/v1",
    "http://[::1]:4000/v1",
    "http://localhost:4000/v1",
    "https://api.nrouter.ai/v1"
  )) {
    client <- nrouter_client(api_key = "sk-nrouter-abc", base_url = allowed)
    expect_equal(client$base_url, sub("/+$", "", allowed))
  }

  for (refused in c(
    "http://api.nrouter.ai/v1",
    "http://192.0.2.10:4000/v1",
    "ftp://127.0.0.1/v1",
    "https://user:pass@api.nrouter.ai/v1",
    "not-a-url"
  )) {
    expect_error(
      nrouter_client(api_key = "sk-nrouter-abc", base_url = refused),
      class = "nrouter_configuration_error"
    )
  }
})

test_that("retry-after parsing and jittered backoff match contract", {
  expect_equal(NROUTER_MAX_RETRY_AFTER_SECONDS, 86400L)
  expect_equal(nrouter_parse_retry_after("120"), 120L)
  expect_equal(nrouter_parse_retry_after("  60  "), 60L)
  expect_equal(nrouter_parse_retry_after("99999999"), 86400L)
  expect_null(nrouter_parse_retry_after(NULL))
  expect_null(nrouter_parse_retry_after(""))
  expect_null(nrouter_parse_retry_after("invalid-value"))

  # HTTP-date parsing
  now <- as.POSIXct("2026-09-05 12:00:00 GMT", tz = "GMT")
  future_date <- "Sat, 05 Sep 2026 12:02:00 GMT"
  past_date <- "Sat, 05 Sep 2026 11:59:00 GMT"
  expect_equal(nrouter_parse_retry_after(future_date, now = now), 120L)
  expect_equal(nrouter_parse_retry_after(past_date, now = now), 0L)

  # Condition receives retry_after
  cond <- nrouter_condition("rate limited", status = 429, retry_after = 120L)
  expect_equal(cond$retry_after, 120L)

  # Jittered backoff computation
  b0 <- nrouter_compute_jittered_backoff(0, base_delay_seconds = 1.0, jitter_factor = 0.0)
  expect_equal(b0, 1.0)

  b_retry <- nrouter_compute_jittered_backoff(0, retry_after_seconds = 5.0, jitter_factor = 0.0)
  expect_equal(b_retry, 5.0)

  b_jitter <- nrouter_compute_jittered_backoff(2, base_delay_seconds = 1.0, max_delay_seconds = 10.0, jitter_factor = 0.5)
  expect_true(b_jitter >= 2.0 && b_jitter <= 4.0)
})

test_that("redacts keys and formats gateway error envelopes", {
  msg <- "Invalid key sk-nrouter-live-12345678 or sk-ant-api03-abcdef123"
  redacted <- nrouter_redact_keys(msg)
  expect_true(grepl("sk-nrouter-\\*\\*\\*", redacted))
  expect_true(grepl("sk-\\*\\*\\*", redacted))
  expect_equal(redacted, nrouter_redact_keys(redacted)) # idempotent

  json <- '{"error":{"message":"Failed with sk-nrouter-test-abcdef","code":"invalid_request_error","param":"model","type":"invalid_request_error"}}'
  envelope <- nrouter_parse_gateway_error_envelope(json)
  expect_equal(envelope$code, "invalid_request_error")
  expect_equal(envelope$param, "model")
  expect_equal(envelope$type, "invalid_request_error")
  expect_true(grepl("sk-nrouter-\\*\\*\\*", envelope$message))

  cond <- nrouter_condition(
    message    = "model secret-key sk-nrouter-live-999 not found",
    code       = "model_not_found",
    param      = "model",
    type       = "invalid_request_error",
    status     = 404,
    request_id = "req_123"
  )
  expect_equal(cond$param, "model")
  expect_equal(cond$type, "invalid_request_error")
  formatted <- nrouter_format_error(cond)
  expect_true(grepl("\\[not_found\\]", formatted))
  expect_true(grepl("HTTP 404", formatted))
  expect_true(grepl("code=model_not_found", formatted))
  expect_true(grepl("param=model", formatted))
  expect_true(grepl("req_id=req_123", formatted))
  expect_true(grepl("sk-nrouter-\\*\\*\\*", formatted))
  expect_true(grepl("sk-nrouter-\\*\\*\\*", cond$message))
})

test_that("propagates trace context and rejects crlf", {
  # Client fields and CRLF rejection
  client <- nrouter_client(
    api_key = "sk-nrouter-test",
    trace_id = "tr_abc",
    session_id = "sess_xyz"
  )
  expect_equal(client$trace_id, "tr_abc")
  expect_equal(client$session_id, "sess_xyz")

  expect_error(
    nrouter_client(api_key = "sk-nrouter-test", trace_id = "bad\r\ntrace"),
    class = "nrouter_configuration_error"
  )
  expect_error(
    nrouter_client(api_key = "sk-nrouter-test", session_id = "bad\nsession"),
    class = "nrouter_configuration_error"
  )

  # Header generation
  hdrs <- nrouter:::nrouter_request_headers(client)
  expect_equal(hdrs[["x-nr-client-language"]], "r")
  expect_equal(hdrs[["x-nr-trace-id"]], "tr_abc")
  expect_equal(hdrs[["x-nr-session-id"]], "sess_xyz")

  # Trace headers extraction
  meta <- nrouter_meta(list("x-nr-request-id" = "req_trace_999"))
  ext_meta <- nrouter_extract_trace_headers(meta)
  expect_equal(ext_meta[["x-nr-request-id"]], "req_trace_999")

  header_map <- list(
    "x-nr-request-id" = "req_1",
    "x-nr-trace-id" = "tr_1",
    "x-nr-session-id" = "sess_1",
    "other" = "val"
  )
  ext_map <- nrouter_extract_trace_headers(header_map)
  expect_equal(length(ext_map), 3L)
  expect_equal(ext_map[["x-nr-request-id"]], "req_1")
  expect_equal(ext_map[["x-nr-trace-id"]], "tr_1")
  expect_equal(ext_map[["x-nr-session-id"]], "sess_1")

  # Trace context injection
  injected <- nrouter_with_trace_context(list(keep = "yes"), trace_id = "tr_2", session_id = "sess_2")
  expect_equal(injected$keep, "yes")
  expect_equal(injected[["x-nr-trace-id"]], "tr_2")
  expect_equal(injected[["x-nr-session-id"]], "sess_2")

  expect_error(
    nrouter_with_trace_context(list(), trace_id = "injected\r\ntrace"),
    class = "nrouter_configuration_error"
  )
})


