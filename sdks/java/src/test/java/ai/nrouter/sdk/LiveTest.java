package ai.nrouter.sdk;

import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

class LiveTest {
    @Test
    @EnabledIfEnvironmentVariable(named = "NROUTER_LIVE", matches = "1")
    void liveClaudeRequestReturnsBillingMetadata() {
        String apiKey = System.getenv("NROUTER_API_KEY");
        String baseUrl = System.getenv().getOrDefault("NROUTER_BASE_URL", "http://127.0.0.1:4000/v1");
        assertNotNull(apiKey, "NROUTER_API_KEY is required for live tests");

        NRouterHttpResponse response = NRouter.httpClient(apiKey, baseUrl).messages(Map.of(
                "model", "claude-haiku-4-5-20251001",
                "max_tokens", 2,
                "messages", List.of(Map.of("role", "user", "content", "Reply OK"))));

        assertEquals(200, response.statusCode());
        assertNotNull(response.meta().requestId());
        assertTrue(response.meta().isPriced());
        assertNotNull(response.meta().cost());
        assertTrue(response.meta().cost() > 0.0);
    }
}
