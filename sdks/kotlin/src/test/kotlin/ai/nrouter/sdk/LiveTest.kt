package ai.nrouter.sdk

import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.json.JSONObject
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable
import kotlin.test.assertTrue

/**
 * BILLED acceptance probes. Every test here reaches a real gateway, a real
 * provider and a real credit balance.
 *
 * # Why the gate is an annotation and not an early `return`
 *
 * This class opened with `if (System.getenv("NROUTER_LIVE") != "1")
 * return@runBlocking`. An early return is a PASS to JUnit, so Gradle printed
 * the live probe as a passing test on a machine with no key, no gateway and no
 * credits — release evidence that could not distinguish a probe that ran from
 * one that never executed a line. [EnabledIfEnvironmentVariable] is decided
 * BEFORE the body runs, so the same machine now reports the probe as
 * `disabled`, with its reason, in the JUnit XML the release reads.
 *
 * ```text
 * ./gradlew test                       # every probe reports disabled/skipped
 * NROUTER_LIVE=1 ./gradlew test        # runs them; needs the env below
 * ```
 *
 * # And why a missing variable is a THROW, not a skip
 *
 * Once `NROUTER_LIVE=1` is set the caller has asked for the billed probes. A
 * missing variable at that point is a misconfigured live run, not a reason to
 * report success — so [require] throws and names the variable. Non-execution
 * can be disabled or a failure; it can never be a pass.
 *
 * # The route-family matrix
 *
 * Claude-through-`/v1/messages` was the only live acceptance here, so the wires
 * customers actually reported broken — OpenAI chat completions, `/v1/responses`
 * and an opaque alias whose provider is not inferable from its name — were
 * outside live evidence entirely. They are separate tests with separate model
 * variables because a model is servable on the wires ITS provider declares and
 * no others: one model cannot certify the matrix, and a single test that tried
 * would fail for a reason that is not a defect.
 */
@EnabledIfEnvironmentVariable(
    named = "NROUTER_LIVE",
    matches = "1",
    disabledReason = "billed: set NROUTER_LIVE=1, NROUTER_API_KEY and the per-wire model variables",
)
class LiveTest {
    /**
     * The value of [name], or a failure naming it.
     *
     * Reached only when `NROUTER_LIVE=1`, where the caller has already asked
     * for a billed run — see the class header.
     */
    private fun require(name: String): String =
        System.getenv(name) ?: error(
            "$name is required for a live probe. Set NROUTER_LIVE=1, " +
                "NROUTER_API_KEY, and the per-wire model variables, then run " +
                "`NROUTER_LIVE=1 ./gradlew test`.",
        )

    /** A client pointed at the gateway under test. */
    private fun liveClient(): NRouter =
        NRouter(baseURL = System.getenv("NROUTER_BASE_URL") ?: NRouter.DEFAULT_BASE_URL)

    /**
     * Every response must carry `x-nr-request-id`: it is the only handle a
     * customer has at support, and the join key for the spend row this call
     * just wrote.
     */
    private fun assertCorrelatable(meta: NRouterResponseMeta, wire: String) =
        assertTrue(!meta.requestId.isNullOrEmpty(), "$wire answered without x-nr-request-id")

    /**
     * The `/v1` paths `GET /v1/models` says this alias can be called on.
     *
     * (Written without a wildcard on purpose: Kotlin block comments NEST, so a
     * literal slash-star inside this KDoc opens a comment that never closes and
     * the file stops compiling several declarations later.)
     *
     * The gateway renders `nrouter_endpoints` from the provider's own endpoint
     * declaration, so this is the discovery answer an SDK is supposed to use
     * instead of guessing a wire from the model name.
     */
    private fun advertisedEndpoints(catalogue: JSONObject, model: String): List<String> {
        val data = catalogue.optJSONArray("data")
            ?: error("GET /v1/models returned no data array")
        val entry = (0 until data.length())
            .map { data.getJSONObject(it) }
            .firstOrNull { it.optString("id") == model }
            ?: error("$model is not in this key's catalogue")
        val endpoints = entry.optJSONArray("nrouter_endpoints")
            ?: error("$model carries no nrouter_endpoints")
        return (0 until endpoints.length()).map { endpoints.getString(it) }
    }

    @Test
    fun `live Claude stream reaches the configured gateway`() = runBlocking {
        val client = liveClient()
        val model = System.getenv("NROUTER_LIVE_MESSAGES_MODEL") ?: "claude-haiku-4-5-20251001"
        val chunks = withTimeout(60_000) {
            client.messagesStream(
                JSONObject()
                    .put("model", model)
                    .put("max_tokens", 2)
                    .put(
                        "messages",
                        listOf(mapOf("role" to "user", "content" to "Reply OK")),
                    )
            ).toList()
        }
        assertTrue(chunks.any { it.delta.isNotEmpty() }, "/v1/messages streamed no text")
        assertCorrelatable(chunks.first().meta, "/v1/messages")
    }

    @Test
    fun `live OpenAI chat completions wire answers`() = runBlocking {
        val client = liveClient()
        val model = require("NROUTER_LIVE_CHAT_MODEL")
        val response = withTimeout(60_000) {
            client.chatCompletions(
                JSONObject()
                    .put("model", model)
                    .put("max_tokens", 2)
                    .put(
                        "messages",
                        listOf(mapOf("role" to "user", "content" to "Reply OK")),
                    )
            )
        }
        assertTrue(
            response.body.optJSONArray("choices") != null,
            "/v1/chat/completions returned no choices array",
        )
        assertCorrelatable(response.meta, "/v1/chat/completions")
    }

    @Test
    fun `live Responses wire answers`() = runBlocking {
        val client = liveClient()
        val model = require("NROUTER_LIVE_RESPONSES_MODEL")
        val response = withTimeout(60_000) {
            client.responses(
                JSONObject()
                    .put("model", model)
                    .put("input", "Reply OK")
                    .put("max_output_tokens", 16)
            )
        }
        assertTrue(response.body.length() > 0, "/v1/responses returned an empty document")
        assertCorrelatable(response.meta, "/v1/responses")
    }

    /**
     * An alias whose provider a client cannot infer from the name — a Bedrock
     * GLM or a Gemma alias — must still be callable, and the wire must come
     * from discovery rather than from a guess.
     *
     * This is the one probe that proves the matrix is DERIVABLE: it reads the
     * endpoints out of `GET /v1/models` and then calls the wire it was told
     * about. An alias listed with an endpoint it cannot serve fails here.
     */
    @Test
    fun `live opaque alias is callable on the wire discovery advertises`() = runBlocking {
        val client = liveClient()
        val model = require("NROUTER_LIVE_OPAQUE_MODEL")
        val catalogue = withTimeout(60_000) { client.models() }
        assertCorrelatable(catalogue.meta, "/v1/models")
        val endpoints = advertisedEndpoints(catalogue.body, model)
        assertTrue(
            endpoints.isNotEmpty(),
            "$model is listed with an empty nrouter_endpoints — the catalogue " +
                "advertises a name no wire serves",
        )

        val body = JSONObject()
            .put("model", model)
            .put("max_tokens", 2)
            .put("messages", listOf(mapOf("role" to "user", "content" to "Reply OK")))
        val response = withTimeout(60_000) {
            when {
                endpoints.contains("/v1/chat/completions") -> client.chatCompletions(body)
                endpoints.contains("/v1/messages") -> client.messages(body)
                else -> error("$model advertises no text wire: $endpoints")
            }
        }
        assertCorrelatable(response.meta, "the discovered text wire")
    }
}
