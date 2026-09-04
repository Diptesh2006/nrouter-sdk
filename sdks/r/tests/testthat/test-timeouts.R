# Transport deadlines.
#
# httr passes no timeout to libcurl unless one is given, and libcurl's own
# CURLOPT_TIMEOUT defaults to ZERO — "wait forever". These tests pin the
# numbers AND prove they reach the wire: a constant nobody passes to httr is
# decoration, and this package shipped exactly that for as long as nothing
# asserted otherwise.

test_that("the declared defaults are the ones a client gets", {
  expect_equal(nrouter_default_timeout_seconds(), 600)
  expect_equal(nrouter_default_connect_timeout_seconds(), 10)
  expect_equal(nrouter_default_stream_idle_seconds(), 180)

  client <- nrouter_client(api_key = "sk-nrouter-test")
  expect_equal(client$timeout_seconds, 600)
  expect_equal(client$connect_timeout_seconds, 10)
  expect_equal(client$stream_idle_seconds, 180)
})

test_that("buffered calls carry a whole-request ceiling and a connect ceiling", {
  client <- nrouter_client(api_key = "sk-nrouter-test")
  options <- nrouter_request_config(client)$options
  # httr stores the request timeout in MILLISECONDS.
  expect_equal(options$timeout_ms, 600 * 1000)
  expect_equal(options$connecttimeout, 10)
})

test_that("streaming and binary transfers carry a stall ceiling and NO whole-request one", {
  # The property that keeps a paid response intact: a whole-request ceiling
  # severs an SSE stream mid-generation and truncates a long video download,
  # both of them already billed.
  client <- nrouter_client(api_key = "sk-nrouter-test")
  options <- nrouter_transfer_config(client)$options
  expect_null(options$timeout_ms)
  expect_equal(options$connecttimeout, 10)
  expect_equal(options$low_speed_limit, 1)
  expect_equal(options$low_speed_time, 180)
})

test_that("a caller's own deadlines override the defaults", {
  client <- nrouter_client(
    api_key = "sk-nrouter-test",
    timeout_seconds = 3,
    connect_timeout_seconds = 2,
    stream_idle_seconds = 4
  )
  expect_equal(nrouter_request_config(client)$options$timeout_ms, 3000)
  expect_equal(nrouter_request_config(client)$options$connecttimeout, 2)
  expect_equal(nrouter_transfer_config(client)$options$low_speed_time, 4)
})

test_that("a client list built before these fields existed still gets the defaults", {
  # Falling back to NULL here means falling back to libcurl's "wait forever",
  # which is the exact failure this change removes.
  legacy <- structure(
    class = "nrouter_client",
    list(api_key = "sk-nrouter-test", base_url = "https://api.nrouter.ai/v1")
  )
  expect_equal(nrouter_request_config(legacy)$options$timeout_ms, 600 * 1000)
  expect_equal(nrouter_transfer_config(legacy)$options$low_speed_time, 180)
})

test_that("a gateway that goes silent fails the buffered call but not a download", {
  skip_if_not_installed("webfakes")
  app <- webfakes::new_app()
  app$get("/v1/models", function(req, res) {
    Sys.sleep(3)
    res$send_json(list(data = list()))
  })
  app$get("/v1/videos/vid_1/content", function(req, res) {
    Sys.sleep(3)
    res$set_header("content-type", "video/mp4")
    res$send(charToRaw("mp4"))
  })
  process <- webfakes::new_app_process(app)
  on.exit(process$stop(), add = TRUE)

  client <- nrouter_client(
    api_key = "sk-nrouter-test",
    base_url = process$url("/v1"),
    timeout_seconds = 1,
    stream_idle_seconds = 30
  )

  # The buffered path is bounded, so a silent gateway is reported rather than
  # waited on forever.
  expect_error(nrouter_models(client), class = "nrouter_transport_error")

  # The binary path is NOT bounded by that ceiling: the same one-second
  # timeout_seconds must not truncate a download that is already billed.
  result <- nrouter_download_video_content(client, "vid_1")
  expect_equal(rawToChar(result$bytes), "mp4")
})
