package ai.nrouter.sdk.android

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import ai.nrouter.sdk.NRouter
import ai.nrouter.sdk.NRouterError
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.json.JSONObject
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertSame
import kotlin.test.assertTrue

/**
 * Android-specific behaviour only. The wire contract is proven once, in the
 * shared `sdks/kotlin` module; repeating it here would be two copies of one
 * promise.
 */
@RunWith(RobolectricTestRunner::class)
class NRouterAndroidTest {

    private val context: Context get() = ApplicationProvider.getApplicationContext()

    @Test
    fun `an explicit key builds a client`() {
        val client = NRouterAndroid.create(context, apiKey = "sk-nrouter-test")
        assertEquals(NRouter.DEFAULT_BASE_URL, client.baseURL)
    }

    @Test
    fun `a local setup failure is Configuration, never retryable Transport`() {
        // Nothing left the process, so it is permanent. Raised as Transport it
        // reports isRetryable == true and a caller's retry loop spins forever.
        val error = assertFailsWith<NRouterError.Configuration> { NRouterAndroid.create(context) }
        assertFalse(error.isRetryable)
    }

    @Test
    fun `a missing key names the Android situation, not the env var`() {
        val error = assertFailsWith<NRouterError.Configuration> { NRouterAndroid.create(context) }
        val message = error.message.orEmpty()
        // The core's advice ("set NROUTER_API_KEY") is unactionable on a
        // handset. If this message ever degrades into that, a developer is sent
        // to do something that cannot work.
        assertTrue(
            message.contains("System.getenv() is not available"),
            "the Android error must explain why the env var cannot help: $message",
        )
        assertTrue(message.contains(NRouterAndroid.MANIFEST_KEY))
    }

    @Test
    fun `an absent manifest entry is null rather than an exception`() {
        assertNull(NRouterAndroid.manifestKey(context))
    }

    @Test
    fun `key validation still applies on Android`() {
        assertFailsWith<NRouterError.Configuration> {
            NRouterAndroid.create(context, apiKey = "sk-openai-nope")
        }
    }

    @Test
    fun `a custom base URL reaches the client`() {
        val client = NRouterAndroid.create(
            context,
            apiKey = "sk-nrouter-test",
            baseURL = "https://api-stage.nrouter.ai/v1/",
        )
        assertEquals("https://api-stage.nrouter.ai/v1", client.baseURL)
    }

    @Test
    fun `a non-string Kotlin map key is a typed configuration failure`() = runBlocking {
        val server = MockWebServer().also { it.start() }
        try {
            val client = NRouterAndroid.create(
                context,
                apiKey = "sk-nrouter-test",
                baseURL = server.url("/v1").toString(),
            )
            val error = assertFailsWith<NRouterError.Configuration> {
                client.messages(
                    JSONObject().put("messages", listOf(mapOf(1 to "invalid"))),
                )
            }
            assertTrue(error.message.orEmpty().contains("keys must be strings"))
        } finally {
            server.shutdown()
        }
    }

    // ---- timeouts -----------------------------------------------------------

    @Test
    fun `the default transport bounds connect, read and write time`() {
        // A bare OkHttpClient() reads for 10s and then gives up — far below a
        // normal completion, and far below an image, video or TTS response. On
        // a handset that aborts requests the gateway completes, settles and
        // BILLS: the user pays and sees a failure.
        val client = NRouterAndroid.create(context, apiKey = "sk-nrouter-test")

        assertEquals(15_000, client.httpClient.connectTimeoutMillis)
        assertEquals(120_000, client.httpClient.readTimeoutMillis)
        assertEquals(60_000, client.httpClient.writeTimeoutMillis)
        assertTrue(
            client.httpClient.readTimeoutMillis >= 60_000,
            "a read timeout under a minute cuts ordinary completions",
        )
        // Streaming and binary downloads carry no whole-call ceiling at all.
        assertEquals(0, client.httpClient.callTimeoutMillis)
    }

    @Test
    fun `the Android default is the shared core transport, not a second set of numbers`() {
        // Two clients disagreeing about how long an inference may take is how
        // one platform starts cutting what the other tolerates.
        val android = NRouterAndroid.defaultHttpClient()
        val core = NRouter.defaultHttpClient()
        assertEquals(core.connectTimeoutMillis, android.connectTimeoutMillis)
        assertEquals(core.readTimeoutMillis, android.readTimeoutMillis)
        assertEquals(core.writeTimeoutMillis, android.writeTimeoutMillis)
        assertEquals(core.callTimeoutMillis, android.callTimeoutMillis)
        // And no retry loop: the gateway reserves credit once per request and
        // owns retry. A client retry of a billed POST is a second bill.
        assertFalse(android.retryOnConnectionFailure)
    }

    @Test
    fun `a stalled server is cut rather than hanging forever`() = runBlocking {
        val server = MockWebServer().also { it.start() }
        try {
            val client = NRouterAndroid.create(
                context,
                apiKey = "sk-nrouter-test",
                baseURL = server.url("/v1").toString(),
                http = NRouterAndroid.defaultHttpClient().newBuilder()
                    .readTimeout(300, java.util.concurrent.TimeUnit.MILLISECONDS)
                    .build(),
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
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun `a slow binary download is never cut`() = runBlocking {
        // /v1/audio/speech and /v1/videos/{id}/content are large and slow by
        // nature, and already paid for. Nothing bounds their TOTAL.
        val server = MockWebServer().also { it.start() }
        try {
            val client = NRouterAndroid.create(
                context,
                apiKey = "sk-nrouter-test",
                baseURL = server.url("/v1").toString(),
            )
            server.enqueue(
                MockResponse()
                    .setResponseCode(200)
                    .setHeader("content-type", "audio/mpeg")
                    .setBody("audio-bytes")
                    .setBodyDelay(1_500, java.util.concurrent.TimeUnit.MILLISECONDS),
            )
            assertEquals("audio-bytes", String(client.audioSpeech(JSONObject()).bytes))
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun `an injected client fully overrides the defaults`() = runBlocking {
        val injected = OkHttpClient.Builder()
            .connectTimeout(3, java.util.concurrent.TimeUnit.SECONDS)
            .readTimeout(7, java.util.concurrent.TimeUnit.SECONDS)
            .writeTimeout(9, java.util.concurrent.TimeUnit.SECONDS)
            .build()
        val server = MockWebServer().also { it.start() }
        try {
            val client = NRouterAndroid.create(
                context,
                apiKey = "sk-nrouter-test",
                baseURL = server.url("/v1").toString(),
                http = injected,
            )
            assertSame(injected, client.httpClient)
            assertEquals(3_000, client.httpClient.connectTimeoutMillis)
            assertEquals(7_000, client.httpClient.readTimeoutMillis)
            assertEquals(9_000, client.httpClient.writeTimeoutMillis)

            // And it is the transport actually used, not merely stored.
            server.enqueue(
                MockResponse().setResponseCode(200).setHeader("content-type", "application/json").setBody("{}"),
            )
            client.chatCompletions(JSONObject())
            assertEquals("/v1/chat/completions", server.takeRequest().path)
        } finally {
            server.shutdown()
        }
    }

    // ---- Retry-After & Jittered Backoff -------------------------------------

    @Test
    fun `Android retry after parsing delegates to core and respects ceilings`() {
        assertEquals(120L, NRouterAndroid.parseRetryAfter("120"))
        assertEquals(86400L, NRouterAndroid.MAX_RETRY_AFTER_SECONDS)
        assertEquals(86400L, NRouterAndroid.parseRetryAfter("99999999"))
        assertNull(NRouterAndroid.parseRetryAfter(null))
        assertNull(NRouterAndroid.parseRetryAfter("invalid-value"))
    }

    @Test
    fun `Android jittered backoff computes within bounded windows`() {
        val delay0 = NRouterAndroid.computeJitteredBackoff(0, baseDelayMs = 1000L, maxDelayMs = 5000L, jitterFactor = 0.0)
        assertEquals(1000L, delay0)

        val delayWithRetryAfter = NRouterAndroid.computeJitteredBackoff(0, retryAfterSeconds = 5L, jitterFactor = 0.0)
        assertEquals(5000L, delayWithRetryAfter)

        val jittered = NRouterAndroid.computeJitteredBackoff(2, baseDelayMs = 1000L, maxDelayMs = 10000L, jitterFactor = 0.5)
        assertTrue(jittered in 2000L..4000L, "Backoff should be within jitter factor range: $jittered")
    }

    @Test
    fun `Android error formatting and redaction helpers`() {
        val msg = "Key sk-nrouter-live-12345 or sk-ant-api03-abcdef"
        val redacted = NRouterAndroid.redactKeys(msg)
        assertTrue(redacted.contains("sk-nrouter-***"))
        assertTrue(redacted.contains("sk-***"))

        val json = """{"error":{"message":"Failed with sk-nrouter-test-abcdef","code":"invalid_request_error","param":"model","type":"invalid_request_error"}}"""
        val envelope = NRouterAndroid.parseGatewayErrorEnvelope(json)
        assertEquals("invalid_request_error", envelope.code)
        assertEquals("model", envelope.param)
        assertEquals("invalid_request_error", envelope.type)
        assertTrue(envelope.message?.contains("sk-nrouter-***") == true)

        val authError = NRouterError.Authentication(ai.nrouter.sdk.NRouterErrorBody("Invalid key sk-nrouter-live-999"))
        assertEquals("Authentication failed. Please verify your API key.", NRouterAndroid.formatUserMessage(authError))

        val rateLimitError = NRouterError.RateLimit(ai.nrouter.sdk.NRouterErrorBody("Too many requests", code = "rate_limit_exceeded", status = 429))
        assertEquals("Rate limit reached. Please wait and try again.", NRouterAndroid.formatUserMessage(rateLimitError))

        val diagnostic = NRouterAndroid.formatDiagnosticMessage(authError)
        assertTrue(diagnostic.contains("[authentication]"))
        assertTrue(diagnostic.contains("sk-nrouter-***"))
    }

    @Test
    fun `Android client propagates trace context and platform header`() {
        runBlocking {
            val server = MockWebServer().also { it.start() }
            try {
                server.enqueue(
                    MockResponse()
                        .setResponseCode(200)
                        .setHeader("content-type", "application/json")
                        .setHeader("x-nr-request-id", "req_android_999")
                        .setBody("{}"),
                )
                val client = NRouterAndroid.create(
                    context,
                    apiKey = "sk-nrouter-test",
                    baseURL = server.url("/v1").toString(),
                    traceId = "tr_android_1",
                    sessionId = "sess_android_1",
                )
                assertEquals("tr_android_1", client.traceId)
                assertEquals("sess_android_1", client.sessionId)
                assertEquals("android", client.clientPlatform)

                val resp = client.chatCompletions(JSONObject())
                val recorded = server.takeRequest()
                assertEquals("android", recorded.getHeader("x-nr-client-platform"))
                assertEquals("kotlin", recorded.getHeader("x-nr-client-language"))
                assertEquals("tr_android_1", recorded.getHeader("x-nr-trace-id"))
                assertEquals("sess_android_1", recorded.getHeader("x-nr-session-id"))

                // Trace headers extraction
                val extracted = NRouterAndroid.extractTraceHeaders(resp.meta)
                assertEquals("req_android_999", extracted["x-nr-request-id"])

                val headerMap = mapOf(
                    "x-nr-request-id" to "req_2",
                    "x-nr-trace-id" to "tr_2",
                    "x-nr-session-id" to "sess_2",
                    "foo" to "bar"
                )
                val extractedMap = NRouterAndroid.extractTraceHeaders(headerMap)
                assertEquals(3, extractedMap.size)
                assertEquals("req_2", extractedMap["x-nr-request-id"])
                assertEquals("tr_2", extractedMap["x-nr-trace-id"])
                assertEquals("sess_2", extractedMap["x-nr-session-id"])

                // Trace context injection
                val injected = NRouterAndroid.withTraceContext(mapOf("orig" to "1"), "tr_3", "sess_3")
                assertEquals("1", injected["orig"])
                assertEquals("tr_3", injected["x-nr-trace-id"])
                assertEquals("sess_3", injected["x-nr-session-id"])

                assertFailsWith<IllegalArgumentException> {
                    NRouterAndroid.withTraceContext(emptyMap(), "bad\r\ntrace", "sess")
                }
            } finally {
                server.shutdown()
            }
        }
    }
}
