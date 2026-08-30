test_that("live Claude request reaches the configured gateway", {
  skip_if(Sys.getenv("NROUTER_LIVE") != "1")
  base_url <- Sys.getenv("NROUTER_BASE_URL", unset = nrouter_default_base_url())
  client <- nrouter_client(base_url = base_url)
  result <- nrouter_messages(client, list(
    model = "claude-haiku-4-5-20251001",
    max_tokens = 2,
    messages = list(list(role = "user", content = "Reply OK"))
  ))
  expect_false(is.null(result$meta$request_id))
  expect_true(nrouter_is_priced(result$meta))
  expect_gt(result$meta$cost, 0)
  expect_true(length(result$body$content) > 0)
})

test_that("live Claude messages stream reaches its terminal event", {
  skip_if(Sys.getenv("NROUTER_LIVE") != "1")
  base_url <- Sys.getenv("NROUTER_BASE_URL", unset = nrouter_default_base_url())
  client <- nrouter_client(base_url = base_url)
  chunks <- list()
  result <- nrouter_messages_stream(client, list(
    model = "claude-haiku-4-5-20251001",
    max_tokens = 2,
    messages = list(list(role = "user", content = "Reply OK"))
  ), function(chunk) {
    chunks[[length(chunks) + 1L]] <<- chunk
  })

  expect_true(length(chunks) > 0)
  expect_false(is.null(result$meta$request_id))
  # Opening SSE headers precede final usage. Unknown is NULL, never zero.
  expect_false(nrouter_is_priced(result$meta))
  expect_null(result$meta$cost)
  expect_false(result$cancelled)
})
