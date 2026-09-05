package ai.nrouter.sdk;

import com.openai.client.OpenAIClient;
import java.net.http.HttpHeaders;
import java.time.Duration;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertThrows;

class NRouterTest {

    @Test
    void vendorRequestDeadlineOutlivesTheGatewayStreamingSla() {
        assertEquals(Duration.ofSeconds(900), NRouterHttpClient.GATEWAY_STREAMING_DEADLINE);
        assertEquals(Duration.ofSeconds(410), NRouterHttpClient.GATEWAY_MAX_TIME_TO_FIRST_BYTE);
        assertTrue(
                NRouterHttpClient.DEFAULT_REQUEST_TIMEOUT.compareTo(
                        NRouterHttpClient.GATEWAY_MAX_TIME_TO_FIRST_BYTE.plus(
                                NRouterHttpClient.GATEWAY_STREAMING_DEADLINE)) > 0,
                "the SDK must not truncate a stream the gateway still considers healthy");
        assertEquals(NRouterHttpClient.DEFAULT_REQUEST_TIMEOUT, NRouter.timeoutProfile().request());
    }

    @Test
    void rejectsInvalidKeysBeforeBuildingClient() {
        assertThrows(IllegalArgumentException.class, () -> NRouter.create("bad-key"));
    }

    @Test
    void buildsClientWithValidLookingKeyAndDefaultBaseUrl() {
        OpenAIClient client = NRouter.create("sk-nrouter-test");
        assertNotNull(client);
    }

    @Test
    void nullBaseUrlFallsBackToDefaultBaseUrl() {
        OpenAIClient client = NRouter.create("sk-nrouter-test", null);
        assertNotNull(client);
    }

    @Test
    void promptSelectionMapsToGatewayFields() {
        NRouter.PromptSelection selection = NRouter.promptTemplate("  tpl_123  ", Map.of("name", "Ada"));
        assertEquals(
                Map.of(
                        "nrouter_prompt_template_id", "tpl_123",
                        "nrouter_prompt_variables", Map.of("name", "Ada")),
                NRouter.promptExtraBody(selection));
    }

    @Test
    void guardrailIdsAreRefusedAndCacheFalseIsMapped() {
        assertThrows(
                IllegalArgumentException.class,
                () -> NRouter.buildExtraBody(null, null, Arrays.asList("gr_1"), null));
        assertEquals(Collections.emptyMap(), NRouter.buildExtraBody(null, null, null, true));
        assertEquals(Map.of("nrouter_cache", false), NRouter.buildExtraBody(null, null, null, false));
    }

    @Test
    void extraBodyTenancyFieldsAreRefused() {
        assertThrows(IllegalArgumentException.class, () -> NRouter.vetExtra(Map.of("organization_id", "org")));
    }

    @Test
    void samplingPolicyMatchesClaudeRules() {
        assertEquals(
                Collections.emptyMap(),
                NRouter.buildSamplingParams(false, "anthropic/claude-sonnet", null, 0.7, 0.5));
        assertEquals(
                Map.of("top_p", 0.5),
                NRouter.buildSamplingParams(true, "anthropic/claude-sonnet", null, 0.7, 0.5));
        assertEquals(
                Map.of("temperature", 0.7, "top_p", 0.5),
                NRouter.buildSamplingParams(true, "openai/gpt-5", null, 0.7, 0.5));
        assertThrows(
                IllegalArgumentException.class,
                () -> NRouter.buildSamplingParams(true, "openai/gpt-5", null, 0.7, 2.0));
    }

    @Test
    void systemVariableConflictsAreReportedInGatewayOrder() {
        assertEquals(
                Arrays.asList("org_name", "model"),
                NRouter.systemVariableConflicts(Map.of("model", "fake", "org_name", "fake")));
        assertEquals(Collections.emptyList(), NRouter.systemVariableConflicts(null));
        assertEquals(Collections.emptyList(), NRouter.systemVariableConflicts(Collections.emptyMap()));
    }

    @Test
    void promptVariablesAndWithVariablesWorkAsExpected() {
        NRouter.PromptSelection vars = NRouter.promptVariables(Map.of("a", "1"));
        assertEquals(Map.of("nrouter_prompt_variables", Map.of("a", "1")), NRouter.promptExtraBody(vars));

        NRouter.PromptSelection merged = NRouter.withVariables(vars, Map.of("b", "2"));
        assertEquals(Map.of("a", "1", "b", "2"), merged.variables());

        assertThrows(IllegalArgumentException.class, () -> NRouter.promptTemplate(""));
        assertThrows(IllegalArgumentException.class, () -> NRouter.promptTemplate(null));
    }

    @Test
    void vetExtraRejectsProtoAndAllowsNull() {
        NRouter.vetExtra(null);
        NRouter.vetExtra(Collections.emptyMap());
        assertThrows(IllegalArgumentException.class, () -> NRouter.vetExtra(Map.of("__proto__", "pollute")));
    }

    @Test
    void samplingRejectsInvalidValues() {
        assertThrows(IllegalArgumentException.class, () -> NRouter.buildSamplingParams(true, "gpt-4", null, -0.5, 0.5));
        assertThrows(IllegalArgumentException.class, () -> NRouter.buildSamplingParams(true, "gpt-4", null, 0.7, -0.1));
        assertThrows(IllegalArgumentException.class, () -> NRouter.buildSamplingParams(true, "gpt-4", null, Double.NaN, 0.5));
    }

    @Test
    void isClaudeModelAndNormalizeAnthropicMessages() {
        assertTrue(NRouter.isClaudeModel("claude-sonnet-4-5", null));
        assertTrue(NRouter.isClaudeModel("sonnet-4-5", null));
        assertTrue(NRouter.isClaudeModel("haiku-3-5", null));
        assertTrue(NRouter.isClaudeModel("opus-4", null));
        assertTrue(NRouter.isClaudeModel("custom", "anthropic"));
        assertFalse(NRouter.isClaudeModel("gpt-4o", "openai"));

        Map<String, Object> input = new LinkedHashMap<>();
        input.put("model", "claude-sonnet-4-5");
        input.put("system", "Initial system");
        input.put("messages", List.of(
            Map.of("role", "system", "content", "Turn system"),
            Map.of("role", "user", "content", "Hello")
        ));
        input.put("max_completion_tokens", 1024);
        input.put("stop", "Human:");

        Map<String, Object> normalized = NRouterHttpClient.normalizeAnthropicMessages(input);
        assertEquals("Initial system\n\nTurn system", normalized.get("system"));
        assertEquals(1, ((List<?>) normalized.get("messages")).size());
        assertEquals(1024, normalized.get("max_tokens"));
        assertEquals(List.of("Human:"), normalized.get("stop_sequences"));
    }

    @Test
    void testUsesMessagesWire() {
        assertTrue(NRouter.usesMessagesWire("claude-3-5-sonnet-20241022"));
        assertTrue(NRouter.usesMessagesWire("anthropic/claude-3-haiku"));
        assertTrue(NRouter.usesMessagesWire("my-model", "anthropic"));
        assertFalse(NRouter.usesMessagesWire("gpt-4o"));
        assertFalse(NRouter.usesMessagesWire("meta-llama/llama-3"));
    }

    @Test
    void testRenderPrompt() {
        // 1. Whitespace tolerance & formatting
        String tpl = "Hello {{name}}! Age: {{  age  }}, active: {{ active }}.";
        Map<String, Object> vars = new HashMap<>();
        vars.put("name", "Alice");
        vars.put("age", 30);
        vars.put("active", true);
        String out = NRouterPrompts.renderPrompt(tpl, vars);
        assertEquals("Hello Alice! Age: 30, active: true.", out);

        // 2. Single pass non-recursive
        String tpl2 = "Value: {{a}}";
        String out2 = NRouterPrompts.renderPrompt(tpl2, Map.of("a", "{{b}}", "b", "final"));
        assertEquals("Value: {{b}}", out2);

        // 3. Metacharacter safety ($1, $&, escapes)
        String tpl3 = "Price: {{price}}, Path: {{path}}";
        String out3 = NRouterPrompts.renderPrompt(tpl3, Map.of("price", "$100", "path", "C:\\test\\1"));
        assertEquals("Price: $100, Path: C:\\test\\1", out3);

        // 4. Non-strict preserves missing tokens
        String tpl4 = "Greeting: {{hello}}, missing: {{world}}";
        String out4 = NRouterPrompts.renderPrompt(tpl4, Map.of("hello", "hi"));
        assertEquals("Greeting: hi, missing: {{world}}", out4);

        // 5. Strict throws error on missing tokens
        assertThrows(
            NRouterException.class,
            () -> NRouterPrompts.renderPrompt(tpl4, Map.of("hello", "hi"), new NRouterPrompts.RenderOptions(true))
        );

        // 6. System variables override
        String tpl5 = "Model: {{model}}, User: {{user}}";
        String out5 = NRouterPrompts.renderPrompt(
            tpl5,
            Map.of("model", "caller-model", "user", "alice"),
            new NRouterPrompts.RenderOptions(false, Map.of("model", "claude-3-7-sonnet"))
        );
        assertEquals("Model: claude-3-7-sonnet, User: alice", out5);
    }

    @Test
    void testSseEventInspectionPreservesIndentationAndSurfacesErrors() {
        NRouterHttpClient client = new NRouterHttpClient("sk-nrouter-test", "https://api.nrouter.ai/v1");
        HttpHeaders headers = HttpHeaders.of(Map.of("x-nr-request-id", List.of("req_sse_test")), (a, b) -> true);
        NRouterResponseMeta meta = NRouterResponseMeta.fromHeaders(headers);
        // Preserves code indentation and does not throw on normal data lines
        assertDoesNotThrow(() -> {
            client.inspectSseEvent(List.of("data:   def foo():", "data:       return 42"), 200, meta);
        });
        // Surfaces in-band error even if non-JSON text
        assertThrows(NRouterException.class, () -> {
            client.inspectSseEvent(List.of("event: error", "data: guardrail blocked response"), 200, meta);
        });
    }
}

