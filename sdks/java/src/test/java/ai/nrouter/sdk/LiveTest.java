package ai.nrouter.sdk;

import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

/**
 * BILLED acceptance probes. Every test here reaches a real gateway, a real
 * provider and a real credit balance.
 *
 * <p>The gate is {@link EnabledIfEnvironmentVariable}, decided BEFORE the body
 * runs, so an unconfigured machine reports these as <em>disabled</em> in the
 * surefire XML a release reads. An early {@code return} would have reported the
 * same machine as passing — evidence that cannot distinguish a probe that ran
 * from one that never executed a line. Non-execution can be disabled or a
 * failure; it can never be a pass.
 *
 * <p>Once {@code NROUTER_LIVE=1} is set the caller has asked for the billed
 * probes, so a missing per-wire variable is a misconfigured live run rather
 * than a reason to report success: {@link #require} FAILS and names it.
 *
 * <h2>The route-family matrix</h2>
 *
 * <p>Claude-through-{@code /v1/messages} was the only live acceptance here, so
 * the wires customers actually reported broken — OpenAI chat completions,
 * {@code /v1/responses}, and an opaque alias whose provider is not inferable
 * from its name — were outside live evidence entirely. They are separate tests
 * with separate model variables because a model is servable on the wires ITS
 * provider declares and no others.
 *
 * <p>The opaque-alias probe names its wire in {@code NROUTER_LIVE_OPAQUE_WIRE}
 * rather than reading {@code nrouter_endpoints} out of {@code GET /v1/models},
 * as the Rust, Kotlin and JS probes do. {@link NRouterHttpClient} exposes no
 * GET, and adding one to the shipping surface is a wider change than a test may
 * make. This probe therefore proves the alias is CALLABLE; it does not prove
 * discovery advertises the wire it was called on.
 */
@EnabledIfEnvironmentVariable(
        named = "NROUTER_LIVE",
        matches = "1",
        disabledReason = "billed: set NROUTER_LIVE=1, NROUTER_API_KEY and the per-wire model variables")
class LiveTest {
    /** The value of {@code name}, or a failure naming it. */
    private static String require(String name) {
        String value = System.getenv(name);
        assertNotNull(
                value,
                name + " is required for a live probe. Set NROUTER_LIVE=1, NROUTER_API_KEY, and the"
                        + " per-wire model variables, then run `NROUTER_LIVE=1 mvn test`.");
        return value;
    }

    /** A client pointed at the gateway under test. */
    private static NRouterHttpClient liveClient() {
        String apiKey = require("NROUTER_API_KEY");
        String baseUrl = System.getenv().getOrDefault("NROUTER_BASE_URL", "http://127.0.0.1:4000/v1");
        return NRouter.httpClient(apiKey, baseUrl);
    }

    /**
     * Every response must carry {@code x-nr-request-id}: it is the only handle a
     * customer has at support, and the join key for the spend row this call just
     * wrote.
     */
    private static void assertCorrelatable(NRouterHttpResponse response, String wire) {
        assertEquals(200, response.statusCode(), wire + " did not answer 200");
        assertNotNull(response.meta().requestId(), wire + " answered without x-nr-request-id");
        assertFalse(response.meta().requestId().isEmpty(), wire + " answered with an empty x-nr-request-id");
    }

    /**
     * Unpriced is not free (Rule #28). {@code x-nr-request-cost} is ABSENT when
     * the model is unpriced — never a zero — so the honest states are exactly
     * two, and a reported cost of 0 is a defect on either.
     */
    private static void assertHonestCost(NRouterHttpResponse response, String wire) {
        String status = response.meta().costStatus();
        if (status == null) {
            return;
        }
        assertTrue(
                "exact".equals(status) || "unpriced".equals(status),
                wire + " reported x-nr-cost-status " + status);
        if ("exact".equals(status)) {
            assertNotNull(response.meta().cost(), wire + " claimed an exact cost and sent none");
            assertTrue(response.meta().cost() > 0.0, wire + " claimed an exact cost that was not above zero");
        } else {
            assertNull(response.meta().cost(), wire + " priced an unpriced response");
        }
    }

    private static Map<String, Object> textBody(String model) {
        return Map.of(
                "model", model,
                "max_tokens", 2,
                "messages", List.of(Map.of("role", "user", "content", "Reply OK")));
    }

    @Test
    void liveClaudeRequestReturnsBillingMetadata() {
        String model = System.getenv().getOrDefault("NROUTER_LIVE_MESSAGES_MODEL", "claude-haiku-4-5-20251001");
        NRouterHttpResponse response = liveClient().messages(textBody(model));

        assertCorrelatable(response, "/v1/messages");
        assertTrue(response.meta().isPriced(), "/v1/messages did not price a priced model");
        assertTrue(response.meta().cost() > 0.0);
    }

    @Test
    void liveOpenAiChatCompletionsWireAnswers() {
        NRouterHttpResponse response = liveClient().chatCompletions(textBody(require("NROUTER_LIVE_CHAT_MODEL")));

        assertTrue(
                response.body().path("choices").isArray(),
                "/v1/chat/completions returned no choices array");
        assertCorrelatable(response, "/v1/chat/completions");
        assertHonestCost(response, "/v1/chat/completions");
    }

    @Test
    void liveResponsesWireAnswers() {
        NRouterHttpResponse response = liveClient()
                .responses(Map.of(
                        "model", require("NROUTER_LIVE_RESPONSES_MODEL"),
                        "input", "Reply OK",
                        "max_output_tokens", 16));

        assertFalse(response.body().isMissingNode(), "/v1/responses returned an empty document");
        assertCorrelatable(response, "/v1/responses");
        assertHonestCost(response, "/v1/responses");
    }

    /**
     * An alias whose provider a client cannot infer from the name — a Bedrock
     * GLM or a Gemma alias — must still be callable. See the class header for
     * why this probe is told its wire instead of discovering it.
     */
    @Test
    void liveOpaqueAliasIsCallable() {
        String model = require("NROUTER_LIVE_OPAQUE_MODEL");
        String wire = System.getenv().getOrDefault("NROUTER_LIVE_OPAQUE_WIRE", "/v1/chat/completions");
        NRouterHttpClient client = liveClient();
        // if/else, not a switch expression: this module targets Java 11.
        NRouterHttpResponse response;
        if ("/v1/chat/completions".equals(wire)) {
            response = client.chatCompletions(textBody(model));
        } else if ("/v1/messages".equals(wire)) {
            response = client.messages(textBody(model));
        } else {
            throw new IllegalStateException(
                    "NROUTER_LIVE_OPAQUE_WIRE must be /v1/chat/completions or /v1/messages, not " + wire);
        }

        assertCorrelatable(response, wire);
        assertHonestCost(response, wire);
    }
}
