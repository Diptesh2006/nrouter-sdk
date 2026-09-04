package ai.nrouter.sdk

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.json.JSONObject
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertSame
import kotlin.test.assertTrue

/**
 * The gateway contract this SDK must keep, asserted against the values in
 * `spec/nrouter-sdk-spec.json`.
 */
class ContractTest {
    private lateinit var server: MockWebServer

    @BeforeTest fun start() { server = MockWebServer().also { it.start() } }
    @AfterTest fun stop() { server.shutdown() }

    private fun clientFor(server: MockWebServer) =
        NRouter(apiKey = "sk-nrouter-test", baseURL = server.url("/v1").toString())

    @Test
    fun `constants match the spec`() {
        assertEquals("https://api.nrouter.ai/v1", NRouter.DEFAULT_BASE_URL)
        assertEquals("NROUTER_API_KEY", NRouter.ENV_KEY)
        assertEquals("sk-nrouter-", NRouter.KEY_PREFIX)
    }

    @Test
    fun `every spec header is read`() {
        val expected = listOf(
            "x-nr-request-id", "x-nr-request-cost", "x-nr-cost-status", "x-nr-model",
            "x-nr-input-tokens", "x-nr-output-tokens", "x-nr-total-tokens",
            "x-nr-cache-read-tokens", "x-nr-cache-write-tokens", "x-nr-limit-source",
            "x-nr-auth-reason", "x-nr-response-cache", "x-nr-response-cache-age",
            "x-nr-budget-warning", "x-nr-guardrails",
        )
        assertEquals(15, NRouterResponseMeta.HEADER_NAMES.size)
        expected.forEach {
            assertTrue(it in NRouterResponseMeta.HEADER_NAMES, "$it is not read by this SDK")
        }
    }

    @Test
    fun `each gateway code maps to its type`() {
        val expected = mapOf(
            "invalid_request" to NRouterError.Request::class,
            "guardrail_blocked" to NRouterError.GuardrailBlocked::class,
            "invalid_api_key" to NRouterError.Authentication::class,
            "insufficient_credits" to NRouterError.Credit::class,
            "model_not_found" to NRouterError.NotFound::class,
            "rate_limit_exceeded" to NRouterError.RateLimit::class,
            "tpm_limit_exceeded" to NRouterError.RateLimit::class,
            "credit_check_failed" to NRouterError.Service::class,
            "service_unavailable" to NRouterError.Service::class,
        )
        expected.forEach { (code, type) ->
            val error = NRouterError.fromCode(NRouterErrorBody("boom", code = code))
            assertEquals(type, error::class, "code $code mapped to ${error::class.simpleName}")
        }
    }

    @Test
    fun `a codeless 402 separates a budget ceiling from a shortfall`() {
        // Two of the three 402s are budget ceilings, whose fix is the OPPOSITE
        // of a shortfall's. Telling a customer whose budget is exhausted to top
        // up is a wrong answer delivered confidently.
        val budget = NRouterError.fromCode(
            NRouterErrorBody("budget exceeded: spend 5.00 of max_budget 5.00", status = 402),
        )
        assertTrue(budget is NRouterError.BudgetExceeded, "got ${budget::class.simpleName}")

        val shortfall = NRouterError.fromCode(
            NRouterErrorBody("insufficient credits: 0.01 available", status = 402),
        )
        assertTrue(shortfall is NRouterError.Credit, "got ${shortfall::class.simpleName}")
    }

    @Test
    fun `a codeless 404 is only model_not_found when it names a model`() {
        val model = NRouterError.fromCode(NRouterErrorBody("model 'x' not found", status = 404))
        assertTrue(model is NRouterError.NotFound)

        // A missing video job or MCP server is also a 404.
        val other = NRouterError.fromCode(NRouterErrorBody("unknown video job", status = 404))
        assertTrue(other is NRouterError.Other, "got ${other::class.simpleName}")
    }

    @Test
    fun `an unknown code is never reclassified`() {
        val error = NRouterError.fromCode(NRouterErrorBody("boom", code = "some_future_code"))
        assertTrue(error is NRouterError.Other)
    }

    @Test
    fun `only transient failures are retryable`() {
        listOf("rate_limit_exceeded", "service_unavailable", "credit_check_failed").forEach {
            assertTrue(NRouterError.fromCode(NRouterErrorBody("x", code = it)).isRetryable, it)
        }
        listOf(
            "invalid_request", "guardrail_blocked", "invalid_api_key",
            "insufficient_credits", "model_not_found",
        ).forEach {
            assertFalse(
                NRouterError.fromCode(NRouterErrorBody("x", code = it)).isRetryable,
                "$it must not be advertised as retryable",
            )
        }
        assertTrue(NRouterError.Transport("dns").isRetryable)
        // A local configuration failure is PERMANENT. Marking it retryable
        // makes a caller's retry loop spin forever without ever sending.
        assertFalse(NRouterError.Configuration("no key").isRetryable)
    }

    @Test
    fun `an unpriced response reports no cost rather than zero`() {
        val meta = NRouterResponseMeta.fromLookup {
            when (it) {
                "x-nr-cost-status" -> "unpriced"
                "x-nr-request-id" -> "req_1"
                else -> null
            }
        }
        assertNull(meta.cost, "unpriced must not become a number")
        assertFalse(meta.isPriced)
        assertEquals("req_1", meta.requestId)
    }

    @Test
    fun `a key without the prefix is refused before any request`() {
        assertFailsWith<NRouterError.Configuration> { NRouter.resolveApiKey("sk-openai-nope") }
        assertEquals("sk-nrouter-abc", NRouter.resolveApiKey("sk-nrouter-abc"))
        assertFailsWith<NRouterError.Configuration> { NRouter(apiKey = "bad-key") }
    }

    @Test
    fun `a live call carries the key and returns the gateway metadata`() = runBlocking {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("content-type", "application/json")
                .setHeader("x-nr-request-id", "req_42")
                .setHeader("x-nr-request-cost", "0.00042")
                .setHeader("x-nr-cost-status", "exact")
                .setHeader("x-nr-input-tokens", "11")
                .setHeader("x-nr-response-cache", "hit")
                .setBody("""{"choices":[{"message":{"content":"hi"}}]}"""),
        )

        val result = clientFor(server).chatCompletions(
            JSONObject().put("model", "claude-sonnet-4-5"),
        )

        val sent = server.takeRequest()
        assertEquals("Bearer sk-nrouter-test", sent.getHeader("Authorization"))
        assertEquals("/v1/chat/completions", sent.path)
        assertEquals("req_42", result.meta.requestId)
        assertEquals(0.00042, result.meta.cost)
        assertEquals(11L, result.meta.inputTokens)
        assertEquals("hit", result.meta.responseCache)
        assertTrue(result.meta.isPriced)
    }

    @Test
    fun `a gateway error becomes its typed exception with metadata attached`() = runBlocking {
        server.enqueue(
            MockResponse()
                .setResponseCode(429)
                .setHeader("content-type", "application/json")
                .setHeader("x-nr-request-id", "req_9")
                .setHeader("x-nr-limit-source", "tpm")
                .setBody("""{"error":{"message":"slow down","code":"tpm_limit_exceeded"}}"""),
        )

        val error = assertFailsWith<NRouterError.RateLimit> {
            clientFor(server).chatCompletions(JSONObject())
        }
        assertEquals("tpm_limit_exceeded", error.body?.code)
        assertEquals("tpm", error.body?.limitSource)
        assertEquals("req_9", error.body?.requestId)
        assertTrue(error.isRetryable)
    }

    @Test
    fun `a codeless 400 is split on the message`() {
        // The gateway's MAIN error path emits {"error":{"type","message"}} with
        // no code, so this is the ordinary shape. Calling every codeless 400 a
        // request error makes GuardrailBlocked unreachable.
        val guardrail = NRouterError.fromCode(
            NRouterErrorBody("blocked by guardrail 'pii'", status = 400),
        )
        assertTrue(guardrail is NRouterError.GuardrailBlocked, "got ${guardrail::class.simpleName}")

        val malformed = NRouterError.fromCode(
            NRouterErrorBody("invalid request: messages must be an array", status = 400),
        )
        assertTrue(malformed is NRouterError.Request, "got ${malformed::class.simpleName}")
    }

    @Test
    fun `a real codeless guardrail 400 from the gateway raises GuardrailBlocked`() = runBlocking {
        // Byte-for-byte the gateway's envelope: type + message, no code.
        server.enqueue(
            MockResponse()
                .setResponseCode(400)
                .setHeader("content-type", "application/json")
                .setBody(
                    """{"error":{"type":"gateway_error","message":"blocked by guardrail 'pii'"}}""",
                ),
        )
        assertFailsWith<NRouterError.GuardrailBlocked> {
            clientFor(server).chatCompletions(JSONObject())
        }
        Unit
    }

    @Test
    fun `a non-JSON 2xx refuses instead of reporting an empty success`() = runBlocking {
        // /v1/audio/speech returns audio. Parsed as JSON it becomes {} — the
        // caller is billed and receives nothing, while the call reports 200.
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("content-type", "audio/mpeg")
                .setHeader("x-nr-request-cost", "0.004")
                .setBody("ID3\u0000\u0000binary-audio"),
        )
        val error = assertFailsWith<NRouterError.Transport> {
            clientFor(server).post("/audio/speech", JSONObject())
        }
        assertTrue(error.message.orEmpty().contains("bytes()"), error.message.orEmpty())
    }

    @Test
    fun `bytes returns the raw body a non-JSON endpoint sent`() = runBlocking {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("content-type", "audio/mpeg")
                .setHeader("x-nr-request-cost", "0.004")
                .setBody("binary-audio"),
        )
        val raw = clientFor(server).bytes("/audio/speech", JSONObject())
        assertEquals("binary-audio", String(raw.bytes))
        assertEquals(0.004, raw.meta.cost)
    }

    @Test
    fun `messages stream yields native Anthropic deltas and forces stream true`() = runBlocking {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("content-type", "text/event-stream")
                .setHeader("x-nr-request-id", "req_stream")
                .setBody(
                    "event: content_block_delta\n" +
                        "data: {\"type\":\"content_block_delta\",\"delta\":{\"type\":\"text_delta\",\"text\":\"Claude\"}}\n\n" +
                        "event: message_stop\n" +
                        "data: {\"type\":\"message_stop\"}\n\n",
                ),
        )

        val original = JSONObject().put("model", "claude")
        val chunks = clientFor(server).messagesStream(original).toList()
        assertEquals(1, chunks.size)
        assertEquals("Claude", chunks.single().delta)
        assertEquals("req_stream", chunks.single().meta.requestId)
        assertFalse(original.has("stream"), "the helper must not mutate the caller's body")
        assertTrue(JSONObject(server.takeRequest().body.readUtf8()).getBoolean("stream"))
    }

    @Test
    fun `nested Kotlin collections are encoded as JSON arrays and objects`() = runBlocking {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("content-type", "application/json")
                .setBody("{}"),
        )
        clientFor(server).messages(
            JSONObject()
                .put("model", "claude")
                .put(
                    "messages",
                    listOf(mapOf("role" to "user", "content" to "hello")),
                ),
        )

        val sent = JSONObject(server.takeRequest().body.readUtf8())
        val message = sent.getJSONArray("messages").getJSONObject(0)
        assertEquals("user", message.getString("role"))
        assertEquals("hello", message.getString("content"))
    }

    @Test
    fun `stream error frame raises the typed guardrail failure`() = runBlocking {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("content-type", "text/event-stream")
                .setHeader("x-nr-request-id", "req_blocked")
                .setBody(
                    "event: error\n" +
                        "data: {\"error\":{\"type\":\"guardrail_blocked\",\"message\":\"the response was withheld by an output guardrail\"}}\n\n",
                ),
        )

        val error = assertFailsWith<NRouterError.GuardrailBlocked> {
            clientFor(server).messagesStream(JSONObject()).toList()
        }
        assertEquals("req_blocked", error.body?.requestId)
        assertEquals("guardrail_blocked", error.body?.code)
    }

    @Test
    fun `a 2xx with unparseable JSON is a failure, not an empty success`() = runBlocking {
        // Truncated mid-stream. The request was BILLED; returning {} reports
        // success with nothing in it.
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("content-type", "application/json")
                .setHeader("x-nr-request-cost", "0.004")
                .setBody("""{"choices":[{"message":"""),
        )
        val error = assertFailsWith<NRouterError.Transport> {
            clientFor(server).chatCompletions(JSONObject())
        }
        assertTrue(error.message.orEmpty().contains("billed"), error.message.orEmpty())
    }

    @Test
    fun `audio transcriptions sends multipart with a named file part`() = runBlocking {
        // The gateway requires multipart/form-data with a binary `file` here.
        // Sent as JSON the endpoint is unreachable, which is what the generic
        // post() helper would have done.
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("content-type", "application/json")
                .setBody("""{"text":"hello"}"""),
        )

        val result = clientFor(server).audioTranscriptions(
            file = "fake-audio".toByteArray(),
            fileName = "speech.mp3",
            fields = mapOf("model" to "whisper-1"),
        )

        val sent = server.takeRequest()
        val contentType = sent.getHeader("Content-Type").orEmpty()
        val body = sent.body.readUtf8()
        assertTrue(contentType.startsWith("multipart/form-data"), contentType)
        assertTrue(body.contains("""name="file""""), "no file part: $body")
        // The extension is load-bearing: providers pick their decoder from it.
        assertTrue(body.contains("speech.mp3"), "file name not sent: $body")
        assertTrue(body.contains("""name="model""""), "no model field: $body")
        assertEquals("hello", result.body.getString("text"))
    }

    @Test
    fun `toString never prints the api key`() {
        // Making this a data class later would silently start printing apiKey
        // into every log — a credential that spends real credits (Rule #5).
        val rendered = NRouter(apiKey = "sk-nrouter-SECRET123").toString()
        assertFalse(rendered.contains("SECRET123"), "the api key leaked: $rendered")
        assertTrue(rendered.contains("sk-nrouter-...T123"), rendered)
    }

    @Test
    fun `cancelling the caller aborts the in-flight request`() = runBlocking {
        // A cancelled coroutine does not interrupt a blocking OkHttp read, so
        // on Android a ViewModel that goes away mid-inference would leave the
        // request running — and a running inference is a BILLED one.
        //
        // Ask OKHTTP whether the call was cancelled. Two weaker observables
        // were tried and both were vacuous: `job.isCancelled` is true after
        // `job.cancel()` no matter what the SDK did, and timing `job.join()`
        // measures coroutine cancellation, which returns immediately without
        // waiting for the socket. Only the client's own event says the request
        // actually stopped.
        val cancelled = java.util.concurrent.CountDownLatch(1)
        val listener = object : okhttp3.EventListener() {
            override fun canceled(call: okhttp3.Call) = cancelled.countDown()
        }
        val client = NRouter(
            apiKey = "sk-nrouter-test",
            baseURL = server.url("/v1").toString(),
            http = okhttp3.OkHttpClient.Builder().eventListener(listener).build(),
        )

        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("content-type", "application/json")
                .setBody("{}")
                // Headers arrive at once and the body streams after, which is
                // the real shape: by cancel time the wait is over and the READ
                // is what is still running.
                .setBodyDelay(4, java.util.concurrent.TimeUnit.SECONDS),
        )

        // Dispatchers.Default: runBlocking's single thread would otherwise be
        // held by the call, and the cancel could not be delivered.
        val job = launch(Dispatchers.Default) {
            runCatching { client.chatCompletions(JSONObject()) }
        }
        delay(500)                     // headers in, body streaming
        job.cancel()
        job.join()

        assertTrue(
            cancelled.await(5, java.util.concurrent.TimeUnit.SECONDS),
            "OkHttp never cancelled the call — the request is still running and billing",
        )
    }

    @Test
    fun `all remaining endpoints build expected requests`() = runBlocking {
        val client = clientFor(server)

        suspend fun json(path: String, call: suspend () -> Unit) {
            server.enqueue(MockResponse().setResponseCode(200).setHeader("content-type", "application/json").setBody("{}"))
            call()
            assertEquals(path, server.takeRequest().path)
        }

        json("/v1/completions") { client.completions(JSONObject()) }
        json("/v1/images/generations") { client.imagesGenerations(JSONObject()) }
        json("/v1/messages/count_tokens") { client.countTokens(JSONObject()) }
        json("/v1/models/provider/model%20one") { client.model("provider/model one") }
        json("/v1/videos") { client.createVideo(JSONObject()) }
        json("/v1/videos/video%2Fone") { client.retrieveVideo("video/one") }

        server.enqueue(MockResponse().setResponseCode(200).setHeader("content-type", "audio/mpeg").setBody("audio"))
        client.audioSpeech(JSONObject())
        assertEquals("/v1/audio/speech", server.takeRequest().path)

        server.enqueue(MockResponse().setResponseCode(200).setHeader("content-type", "video/mp4").setBody("video"))
        client.downloadVideoContent("video/one")
        assertEquals("/v1/videos/video%2Fone/content", server.takeRequest().path)

        server.enqueue(MockResponse().setResponseCode(200).setHeader("content-type", "application/json").setBody("{}"))
        client.embeddings(JSONObject().put("model", "text-embedding-3"))
        assertEquals("/v1/embeddings", server.takeRequest().path)

        server.enqueue(MockResponse().setResponseCode(200).setHeader("content-type", "application/json").setBody("{}"))
        client.messages(JSONObject().put("model", "claude-sonnet"))
        assertEquals("/v1/messages", server.takeRequest().path)

        server.enqueue(MockResponse().setResponseCode(200).setHeader("content-type", "application/json").setBody("{}"))
        client.responses(JSONObject().put("model", "gpt-4o"))
        assertEquals("/v1/responses", server.takeRequest().path)

        server.enqueue(MockResponse().setResponseCode(200).setHeader("content-type", "application/json").setBody("{}"))
        client.models()
        assertEquals("/v1/models", server.takeRequest().path)

        server.enqueue(MockResponse().setResponseCode(200).setHeader("content-type", "application/json").setBody("{}"))
        client.get("/custom-path")
        assertEquals("/v1/custom-path", server.takeRequest().path)

        server.enqueue(MockResponse().setResponseCode(200).setHeader("content-type", "application/json").setBody("{}"))
        client.audioTranslations(
            file = "audio".toByteArray(),
            fileName = "audio.mp3",
            fields = mapOf("model" to "whisper-1"),
        )
        val audioReq = server.takeRequest()
        assertEquals("/v1/audio/translations", audioReq.path)
        assertTrue(audioReq.getHeader("Content-Type").orEmpty().startsWith("multipart/form-data"))

        // GET bytes without body
        server.enqueue(MockResponse().setResponseCode(200).setBody("video-data"))
        val vidBytes = client.bytes("/videos/123/content")
        assertEquals("video-data", String(vidBytes.bytes))
    }

    @Test
    fun `bytes error path throws typed error`() = runBlocking {
        server.enqueue(
            MockResponse()
                .setResponseCode(402)
                .setHeader("content-type", "application/json")
                .setBody("""{"error":{"code":"insufficient_credits","message":"out of credits"}}"""),
        )
        val error = assertFailsWith<NRouterError.Credit> {
            clientFor(server).bytes("/audio/speech", JSONObject())
        }
        assertEquals("insufficient_credits", error.body?.code)
    }

    @Test
    fun `response meta extracts all properties correctly`() {
        val headers = okhttp3.Headers.Builder()
            .add("x-nr-request-id", "req-kt-123")
            .add("x-nr-request-cost", "0.0025")
            .add("x-nr-cost-status", "exact")
            .add("x-nr-model", "gpt-4o")
            .add("x-nr-input-tokens", "15")
            .add("x-nr-output-tokens", "35")
            .add("x-nr-total-tokens", "50")
            .add("x-nr-cache-read-tokens", "10")
            .add("x-nr-cache-write-tokens", "5")
            .add("x-nr-limit-source", "key")
            .add("x-nr-auth-reason", "active")
            .add("x-nr-response-cache", "hit")
            .add("x-nr-response-cache-age", "120")
            .add("x-nr-budget-warning", "org soft_budget 80.00/100.00")
            .add("x-nr-guardrails", "pass")
            .build()

        val meta = NRouterResponseMeta.fromLookup { headers[it] }
        assertEquals("req-kt-123", meta.requestId)
        assertEquals(0.0025, meta.cost)
        assertEquals("exact", meta.costStatus)
        assertEquals("gpt-4o", meta.model)
        assertEquals(15L, meta.inputTokens)
        assertEquals(35L, meta.outputTokens)
        assertEquals(50L, meta.totalTokens)
        assertEquals(10L, meta.cacheReadTokens)
        assertEquals(5L, meta.cacheWriteTokens)
        assertEquals("key", meta.limitSource)
        assertEquals("active", meta.authReason)
        assertEquals("hit", meta.responseCache)
        assertEquals(120L, meta.responseCacheAge)
        assertEquals("org soft_budget 80.00/100.00", meta.budgetWarning)
        assertEquals("pass", meta.guardrails)
        assertTrue(meta.isPriced)
    }

    // ---- timeouts -----------------------------------------------------------

    private fun tuned(
        readTimeoutMillis: Long = NRouter.READ_TIMEOUT_MILLIS,
        callTimeoutMillis: Long = 0,
    ) = NRouter.defaultHttpClient().newBuilder()
        .readTimeout(readTimeoutMillis, java.util.concurrent.TimeUnit.MILLISECONDS)
        .callTimeout(callTimeoutMillis, java.util.concurrent.TimeUnit.MILLISECONDS)
        .build()

    @Test
    fun `the default transport bounds connect, read and write time`() {
        // OkHttpClient() ships a 10s READ timeout — far below a normal
        // completion, and far below an image, video or TTS response. The client
        // was aborting requests the gateway completes, settles and BILLS.
        val client = NRouter(apiKey = "sk-nrouter-test")

        assertEquals(15_000, client.httpClient.connectTimeoutMillis)
        assertEquals(120_000, client.httpClient.readTimeoutMillis)
        assertEquals(60_000, client.httpClient.writeTimeoutMillis)
        assertTrue(
            client.httpClient.readTimeoutMillis >= 60_000,
            "a read timeout under a minute cuts ordinary completions",
        )

        // Streaming and binary paths: no whole-call ceiling at all.
        assertEquals(0, client.httpClient.callTimeoutMillis)
        // Buffered JSON: a ceiling above the gateway's worst honest case
        // (3 provider attempts, 20s cumulative backoff, 120s between bytes).
        assertEquals(600_000, client.bufferedHttpClient.callTimeoutMillis)
    }

    @Test
    fun `the SDK adds no retry loop of its own`() = runBlocking {
        // The gateway reserves credit ONCE per customer request and owns retry
        // and failover. A client retry of a billed POST is a second call and a
        // second bill with nothing to deduplicate on.
        assertFalse(
            NRouter.defaultHttpClient().retryOnConnectionFailure,
            "OkHttp would re-send a request that failed after it was written",
        )

        // A RETRYABLE failure is the interesting case: the SDK must still not
        // retry it. Retrying is the gateway's job, above one credit reservation.
        server.enqueue(
            MockResponse()
                .setResponseCode(503)
                .setHeader("content-type", "application/json")
                .setBody("""{"error":{"code":"service_unavailable","message":"upstream is down"}}"""),
        )
        val error = assertFailsWith<NRouterError.Service> { clientFor(server).chatCompletions(JSONObject()) }
        assertTrue(error.isRetryable)
        assertEquals(1, server.requestCount, "a 503 was retried; that is a second call and a second bill")
    }

    @Test
    fun `a stalled server cuts a buffered call rather than hanging forever`() = runBlocking {
        val client = NRouter(
            apiKey = "sk-nrouter-test",
            baseURL = server.url("/v1").toString(),
            http = tuned(readTimeoutMillis = 300),
        )
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("content-type", "application/json")
                .setBody("{}")
                .setHeadersDelay(5, java.util.concurrent.TimeUnit.SECONDS),
        )
        val started = System.nanoTime()
        assertFailsWith<NRouterError.Transport> { client.chatCompletions(JSONObject()) }
        val elapsedMillis = (System.nanoTime() - started) / 1_000_000
        assertTrue(elapsedMillis < 4_000, "the call was not cut: ${elapsedMillis}ms")
    }

    @Test
    fun `the buffered ceiling cuts a call whose body never finishes`() = runBlocking {
        // The read timeout catches silence between bytes; this catches a peer
        // that keeps dribbling forever, which is the other way to hang.
        val client = NRouter(
            apiKey = "sk-nrouter-test",
            baseURL = server.url("/v1").toString(),
            bufferedCallTimeoutMillis = 400,
        )
        assertEquals(400, client.bufferedHttpClient.callTimeoutMillis)
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("content-type", "application/json")
                .setBody("{}")
                .setBodyDelay(5, java.util.concurrent.TimeUnit.SECONDS),
        )
        val started = System.nanoTime()
        assertFailsWith<NRouterError.Transport> { client.chatCompletions(JSONObject()) }
        val elapsedMillis = (System.nanoTime() - started) / 1_000_000
        // Not merely "it failed": it failed at the CEILING, not five seconds later.
        assertTrue(elapsedMillis < 4_000, "the ceiling never fired: ${elapsedMillis}ms")
    }

    @Test
    fun `a slow stream body is never cut by the buffered ceiling`() = runBlocking {
        // SSE is long BY DESIGN. A ceiling here kills a completion the gateway
        // has already settled and billed.
        val client = NRouter(
            apiKey = "sk-nrouter-test",
            baseURL = server.url("/v1").toString(),
            bufferedCallTimeoutMillis = 400,
        )
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("content-type", "text/event-stream")
                .setHeader("x-nr-request-id", "req_slow_stream")
                .setBody("data: {\"delta\":\"one\"}\n\ndata: {\"delta\":\"two\"}\n\ndata: [DONE]\n\n")
                .setBodyDelay(1_500, java.util.concurrent.TimeUnit.MILLISECONDS),
        )
        val chunks = client.chatCompletionsStream(JSONObject()).toList()
        assertEquals(listOf("one", "two"), chunks.map { it.delta })
        assertEquals("req_slow_stream", chunks.first().meta.requestId)
    }

    @Test
    fun `a slow binary download is never cut by the buffered ceiling`() = runBlocking {
        // Generated audio and a rendered video are large and slow by nature,
        // and the customer has already paid for them.
        val client = NRouter(
            apiKey = "sk-nrouter-test",
            baseURL = server.url("/v1").toString(),
            bufferedCallTimeoutMillis = 400,
        )
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("content-type", "audio/mpeg")
                .setBody("audio-bytes")
                .setBodyDelay(1_500, java.util.concurrent.TimeUnit.MILLISECONDS),
        )
        assertEquals("audio-bytes", String(client.audioSpeech(JSONObject()).bytes))
    }

    @Test
    fun `an injected client fully overrides the defaults`() = runBlocking {
        val injected = okhttp3.OkHttpClient.Builder()
            .connectTimeout(3, java.util.concurrent.TimeUnit.SECONDS)
            .readTimeout(7, java.util.concurrent.TimeUnit.SECONDS)
            .writeTimeout(9, java.util.concurrent.TimeUnit.SECONDS)
            .callTimeout(11, java.util.concurrent.TimeUnit.SECONDS)
            .build()
        val client = NRouter(
            apiKey = "sk-nrouter-test",
            baseURL = server.url("/v1").toString(),
            http = injected,
        )

        assertSame(injected, client.httpClient)
        assertEquals(3_000, client.httpClient.connectTimeoutMillis)
        assertEquals(7_000, client.httpClient.readTimeoutMillis)
        assertEquals(9_000, client.httpClient.writeTimeoutMillis)
        // The caller stated a ceiling; the SDK does not widen or narrow it, and
        // does not layer its own on top.
        assertSame(injected, client.bufferedHttpClient)
        assertEquals(11_000, client.bufferedHttpClient.callTimeoutMillis)

        // And it is the transport actually used, not merely stored.
        server.enqueue(MockResponse().setResponseCode(200).setHeader("content-type", "application/json").setBody("{}"))
        client.chatCompletions(JSONObject())
        assertEquals("/v1/chat/completions", server.takeRequest().path)
    }
}
