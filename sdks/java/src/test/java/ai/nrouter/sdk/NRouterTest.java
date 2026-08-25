package ai.nrouter.sdk;

import com.openai.client.OpenAIClient;
import org.junit.jupiter.api.Test;

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
}
