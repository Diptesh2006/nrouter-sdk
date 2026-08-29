package ai.nrouter.sdk;

import com.openai.client.OpenAIClient;
import java.util.Arrays;
import java.util.Collections;
import java.util.Map;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class NRouterTest {

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
    }
}
