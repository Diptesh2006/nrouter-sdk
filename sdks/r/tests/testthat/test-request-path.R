test_that("messages sends the real path, bearer key, JSON body, and reads metadata", {
  skip_if_not_installed("webfakes")
  skip_if_not(webfakes_available(), "webfakes background process not available")
  app <- webfakes::new_app()
  app$use(webfakes::mw_json())
  app$post("/v1/messages", function(req, res) {
    res$set_header("x-nr-request-id", "req_path")
    res$set_header("x-nr-request-cost", "0.00042")
    res$send_json(list(
      auth = req$get_header("Authorization"),
      model = req$json$model
    ))
  })
  process <- webfakes::new_app_process(app)
  on.exit(process$stop(), add = TRUE)
  client <- nrouter_client(
    api_key = "sk-nrouter-test",
    base_url = process$url("/v1")
  )

  result <- nrouter_messages(client, list(model = "claude-test", messages = list()))

  expect_equal(unname(unlist(result$body$auth)), "Bearer sk-nrouter-test")
  expect_equal(unname(unlist(result$body$model)), "claude-test")
  expect_equal(result$meta$request_id, "req_path")
  expect_equal(result$meta$cost, 0.00042)
})

test_that("multipart sends the named audio route, auth, and form content type", {
  skip_if_not_installed("webfakes")
  skip_if_not(webfakes_available(), "webfakes background process not available")
  app <- webfakes::new_app()
  app$post("/v1/audio/transcriptions", function(req, res) {
    res$set_header("x-nr-request-id", "req_audio")
    res$send_json(list(
      auth = req$get_header("Authorization"),
      content_type = req$get_header("Content-Type")
    ))
  })
  process <- webfakes::new_app_process(app)
  on.exit(process$stop(), add = TRUE)
  audio <- tempfile(fileext = ".mp3")
  on.exit(unlink(audio), add = TRUE)
  writeBin(charToRaw("fake-audio"), audio)
  client <- nrouter_client(
    api_key = "sk-nrouter-test",
    base_url = process$url("/v1")
  )

  result <- nrouter_audio_transcriptions(
    client,
    audio,
    fields = list(model = "whisper-test")
  )

  expect_equal(unname(unlist(result$body$auth)), "Bearer sk-nrouter-test")
  content_type <- unname(unlist(result$body$content_type))
  expect_true(startsWith(content_type, "multipart/form-data; boundary="))
  expect_equal(result$meta$request_id, "req_audio")
})

test_that("request sends client-language and trace routing headers", {
  skip_if_not_installed("webfakes")
  skip_if_not(webfakes_available(), "webfakes background process not available")
  app <- webfakes::new_app()
  app$use(webfakes::mw_json())
  app$post("/v1/chat/completions", function(req, res) {
    res$set_header("x-nr-request-id", "req_trace_test")
    res$send_json(list(
      lang = req$get_header("x-nr-client-language"),
      trace = req$get_header("x-nr-trace-id"),
      session = req$get_header("x-nr-session-id")
    ))
  })
  process <- webfakes::new_app_process(app)
  on.exit(process$stop(), add = TRUE)
  client <- nrouter_client(
    api_key = "sk-nrouter-test",
    base_url = process$url("/v1"),
    trace_id = "trace_wire_1",
    session_id = "session_wire_1"
  )

  result <- nrouter_chat_completions(client, list(model = "test-model"))

  expect_equal(unname(unlist(result$body$lang)), "r")
  expect_equal(unname(unlist(result$body$trace)), "trace_wire_1")
  expect_equal(unname(unlist(result$body$session)), "session_wire_1")
  expect_equal(result$meta$request_id, "req_trace_test")
})
