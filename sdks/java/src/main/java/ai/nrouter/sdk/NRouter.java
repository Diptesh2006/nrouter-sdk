package ai.nrouter.sdk;

import com.openai.client.OpenAIClient;
import com.openai.client.okhttp.OpenAIOkHttpClient;

/**
 * Factory for an OpenAI-compatible client pre-configured for nRouter.
 *
 * openai-java builds clients through a builder that returns the {@link OpenAIClient}
 * interface directly, so there's no class to subclass the way the Python/JS SDKs do —
 * this factory validates the key and returns the real client instead.
 */
public final class NRouter {

    private static final String DEFAULT_BASE_URL = "https://api.nrouter.ai/v1";
    private static final String ENV_KEY = "NROUTER_API_KEY";
    private static final String KEY_PREFIX = "sk-nrouter-";

    private NRouter() {
    }

    /** Reads the API key from the {@code NROUTER_API_KEY} environment variable. */
    public static OpenAIClient create() {
        return create(System.getenv(ENV_KEY));
    }

    public static OpenAIClient create(String apiKey) {
        return create(apiKey, DEFAULT_BASE_URL);
    }

    public static OpenAIClient create(String apiKey, String baseUrl) {
        String resolved = resolveApiKey(apiKey);
        return OpenAIOkHttpClient.builder()
                .apiKey(resolved)
                .baseUrl(baseUrl != null ? baseUrl : DEFAULT_BASE_URL)
                .build();
    }

    private static String resolveApiKey(String apiKey) {
        if (apiKey == null || !apiKey.startsWith(KEY_PREFIX)) {
            throw new IllegalArgumentException(
                    "nRouter API keys must start with '" + KEY_PREFIX
                            + "'; pass apiKey or set " + ENV_KEY + ".");
        }
        return apiKey;
    }
}
