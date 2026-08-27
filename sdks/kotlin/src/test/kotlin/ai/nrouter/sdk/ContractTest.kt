package ai.nrouter.sdk

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
        )
        assertEquals(13, NRouterResponseMeta.HEADER_NAMES.size)
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
    fun `a bare error envelope still yields a typed error`() = runBlocking {
        // A proxy that unwraps `error` must not downgrade this to a generic failure.
        server.enqueue(
            MockResponse()
                .setResponseCode(402)
                .setHeader("content-type", "application/json")
                .setBody("""{"message":"no credits","code":"insufficient_credits"}"""),
        )
        val error = assertFailsWith<NRouterError.Credit> {
            clientFor(server).chatCompletions(JSONObject())
        }
        // Assert the CODE was read, not merely that the type came out right:
        // the HTTP-status fallback also yields Credit for a 402, so a type-only
        // assertion passes even when the bare envelope is ignored entirely.
        assertEquals("insufficient_credits", error.body?.code)
        assertEquals("no credits", error.body?.message)
        assertFalse(error.isRetryable)
    }
}
