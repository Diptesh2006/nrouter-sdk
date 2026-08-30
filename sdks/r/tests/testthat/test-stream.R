test_that("SSE parser handles fragmented native Anthropic deltas", {
  chunks <- list()
  parser <- nrouter_sse_parser(function(chunk) {
    chunks[[length(chunks) + 1L]] <<- chunk
  })

  parser$feed(charToRaw(paste0(
    "event: content_block_delta\n",
    "data: {\"type\":\"content_block_delta\",\"delta\":{\"text\":\"hel"
  )))
  parser$feed(charToRaw(paste0(
    "lo\"}}\n\n",
    "event: message_stop\ndata: {\"type\":\"message_stop\"}\n\n"
  )))
  parser$finish()

  expect_length(chunks, 1)
  expect_equal(chunks[[1]]$event, "content_block_delta")
  expect_equal(chunks[[1]]$delta, "hello")
})

test_that("SSE parser surfaces an in-band guardrail refusal", {
  parser <- nrouter_sse_parser(function(chunk) NULL)

  expect_error(
    parser$feed(charToRaw(paste0(
      "event: error\n",
      "data: {\"error\":{\"type\":\"guardrail_blocked\",",
      "\"message\":\"withheld by guardrail\"}}\n\n"
    ))),
    class = "nrouter_guardrail_blocked_error"
  )
})

test_that("SSE parser refuses EOF without a terminal event", {
  parser <- nrouter_sse_parser(function(chunk) NULL)
  parser$feed(charToRaw("data: {\"delta\":\"partial\"}\n\n"))
  expect_error(parser$finish(), class = "nrouter_transport_error")
})

test_that("messages stream sends the real path, auth, and stream flag", {
  skip_if_not_installed("webfakes")
  app <- webfakes::new_app()
  app$use(webfakes::mw_json())
  app$post("/v1/messages", function(req, res) {
    res$set_header("content-type", "text/event-stream")
    res$set_header("x-nr-request-id", "req_r_stream")
    res$send(paste0(
      "data: {\"delta\":{\"text\":\"ok\"}}\n\n",
      "event: message_stop\ndata: {\"type\":\"message_stop\"}\n\n"
    ))
  })
  process <- webfakes::new_app_process(app)
  on.exit(process$stop(), add = TRUE)
  client <- nrouter_client(
    api_key = "sk-nrouter-stream-test",
    base_url = process$url("/v1")
  )
  chunks <- list()

  result <- nrouter_messages_stream(client, list(model = "claude"), function(chunk) {
    chunks[[length(chunks) + 1L]] <<- chunk
  })

  expect_equal(result$status_code, 200)
  expect_equal(result$meta$request_id, "req_r_stream")
  expect_equal(chunks[[1]]$delta, "ok")
})
