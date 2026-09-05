package ai.nrouter.sdk;

import com.openai.client.OpenAIClient;
import com.openai.client.okhttp.OpenAIOkHttpClient;
import com.openai.core.Timeout;
import java.net.http.HttpClient;
import java.time.Duration;
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

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
    public static final String PROMPT_TEMPLATE_ID_FIELD = "nrouter_prompt_template_id";
    public static final String PROMPT_VARIABLES_FIELD = "nrouter_prompt_variables";
    public static final String CACHE_FIELD = "nrouter_cache";
    public static final java.util.List<String> PROMPT_WIRE_FIELDS =
            Collections.unmodifiableList(Arrays.asList(PROMPT_TEMPLATE_ID_FIELD, PROMPT_VARIABLES_FIELD));
    public static final java.util.List<String> SYSTEM_VARIABLE_NAMES =
            Collections.unmodifiableList(Arrays.asList("org_name", "model", "timestamp", "user_id"));

    private static final Set<String> TENANCY_KEYS =
            Set.of("organizationid", "orgid", "teamid", "userid", "nrouterorg");

    private NRouter() {
    }

    /** True when a model family is served on /v1/messages rather than /v1/chat/completions. */
    public static boolean usesMessagesWire(String model) {
        return usesMessagesWire(model, null);
    }

    /** True when a model family is served on /v1/messages rather than /v1/chat/completions. */
    public static boolean usesMessagesWire(String model, String provider) {
        if (model != null) {
            String m = model.toLowerCase();
            if (m.contains("claude") || m.contains("anthropic") || m.contains("haiku") || m.contains("sonnet") || m.contains("opus")) {
                return true;
            }
        }
        if (provider != null && provider.toLowerCase().contains("anthropic")) {
            return true;
        }
        return false;
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
                // Both Java surfaces share one timeout profile, including the
                // margin beyond the gateway's longest healthy stream.
                .timeout(OPENAI_TIMEOUT)
                // NOT the library default of 2. The gateway reserves credit once
                // per customer request and owns retry and failover; a client-side
                // retry of a billed POST is a second call and a second bill, with
                // no idempotency key to deduplicate on.
                .maxRetries(0)
                .build();
    }

    /**
     * The timeout profile for the vendor OpenAI-compatible surface.
     *
     * <p>{@code request} is a whole-exchange ceiling and {@code read} is the gap
     * between bytes; the OkHttp-backed client can express both, so it does. The
     * native {@link NRouterHttpClient} can only express the connect and
     * whole-exchange halves and therefore handles long-lived response bodies
     * separately.
     */
    private static final Timeout OPENAI_TIMEOUT = Timeout.builder()
            .connect(NRouterHttpClient.DEFAULT_CONNECT_TIMEOUT)
            .read(NRouterHttpClient.DEFAULT_READ_TIMEOUT)
            .write(NRouterHttpClient.DEFAULT_WRITE_TIMEOUT)
            .request(NRouterHttpClient.DEFAULT_REQUEST_TIMEOUT)
            .build();

    static Timeout timeoutProfile() {
        return OPENAI_TIMEOUT;
    }

    /** Native Java 11 surface with raw nRouter metadata and typed errors. */
    public static NRouterHttpClient httpClient(String apiKey) {
        return httpClient(apiKey, DEFAULT_BASE_URL);
    }

    /** Native Java 11 surface pointed at a custom gateway. */
    public static NRouterHttpClient httpClient(String apiKey, String baseUrl) {
        return new NRouterHttpClient(
                resolveApiKey(apiKey),
                baseUrl != null ? baseUrl : DEFAULT_BASE_URL);
    }

    /**
     * Native Java 11 surface over a transport you built — proxy, connection
     * pool, executor, TLS. The SDK's own defaults are what you are replacing;
     * nothing here is layered back on top of yours.
     */
    public static NRouterHttpClient httpClient(String apiKey, String baseUrl, HttpClient http) {
        return httpClient(apiKey, baseUrl, http, NRouterHttpClient.DEFAULT_REQUEST_TIMEOUT);
    }

    /**
     * Native Java 11 surface over your transport and your whole-exchange
     * ceiling. The ceiling still applies only to buffered requests: SSE and
     * binary downloads are never bounded by a total.
     */
    public static NRouterHttpClient httpClient(
            String apiKey, String baseUrl, HttpClient http, Duration requestTimeout) {
        return new NRouterHttpClient(
                resolveApiKey(apiKey),
                baseUrl != null ? baseUrl : DEFAULT_BASE_URL,
                http,
                requestTimeout);
    }

    public static Map<String, Object> buildExtraBody(
            String promptTemplateId,
            Map<String, String> promptVariables,
            java.util.List<String> guardrailIds,
            Boolean cache) {
        if (guardrailIds != null && !guardrailIds.isEmpty()) {
            throw new IllegalArgumentException(
                    "guardrailIds is not supported: guardrails are assigned per key, team, or organization "
                            + "in the nRouter dashboard and already apply automatically to every call.");
        }
        Map<String, Object> out = new LinkedHashMap<>();
        if (promptTemplateId != null && !promptTemplateId.isBlank()) {
            out.put(PROMPT_TEMPLATE_ID_FIELD, promptTemplateId);
        }
        if (promptVariables != null && !promptVariables.isEmpty()) {
            out.put(PROMPT_VARIABLES_FIELD, new LinkedHashMap<>(promptVariables));
        }
        if (Boolean.FALSE.equals(cache)) {
            out.put(CACHE_FIELD, false);
        }
        return out;
    }

    public static void vetExtra(Map<String, ?> extra) {
        if (extra == null) {
            return;
        }
        for (String key : extra.keySet()) {
            if (TENANCY_KEYS.contains(normalizeKey(key))) {
                throw new IllegalArgumentException(
                        "extraBody must not carry the tenancy field \"" + key
                                + "\". The gateway resolves organization, team, and user from the API key.");
            }
            if ("__proto__".equals(key)) {
                throw new IllegalArgumentException("extraBody must not carry a \"__proto__\" key.");
            }
        }
    }

    public static PromptSelection promptTemplate(String templateId) {
        return promptTemplate(templateId, null);
    }

    public static PromptSelection promptTemplate(String templateId, Map<String, String> variables) {
        if (templateId == null || templateId.trim().isEmpty()) {
            throw new IllegalArgumentException(
                    "promptTemplate requires a template id. Use promptVariables() to render the assigned prompt.");
        }
        return new PromptSelection(templateId.trim(), variables);
    }

    public static PromptSelection promptVariables(Map<String, String> variables) {
        return new PromptSelection(null, variables);
    }

    public static PromptSelection withVariables(PromptSelection selection, Map<String, String> more) {
        Map<String, String> merged = new LinkedHashMap<>();
        if (selection.variables() != null) {
            merged.putAll(selection.variables());
        }
        if (more != null) {
            merged.putAll(more);
        }
        return new PromptSelection(selection.templateId(), merged);
    }

    public static Map<String, Object> promptExtraBody(PromptSelection selection) {
        return buildExtraBody(selection.templateId(), selection.variables(), null, null);
    }

    public static java.util.List<String> systemVariableConflicts(Map<String, String> variables) {
        if (variables == null || variables.isEmpty()) {
            return Collections.emptyList();
        }
        java.util.List<String> conflicts = new java.util.ArrayList<>();
        for (String name : SYSTEM_VARIABLE_NAMES) {
            if (variables.containsKey(name)) {
                conflicts.add(name);
            }
        }
        return conflicts;
    }

    public static boolean isClaudeModel(String model, String provider) {
        return containsIgnoreCase(model, "claude") || containsIgnoreCase(provider, "anthropic");
    }

    public static Map<String, Double> buildSamplingParams(
            boolean advanced,
            String model,
            String provider,
            Double temperature,
            Double topP) {
        if (!advanced) {
            return Collections.emptyMap();
        }
        if (temperature != null) {
            requireUsable("temperature", temperature, null);
        }
        if (topP != null) {
            requireUsable("top_p", topP, 1.0);
        }
        boolean topPSet = topP != null && topP.doubleValue() != 1.0;
        boolean suppressTemperature = topPSet && isClaudeModel(model, provider);
        Map<String, Double> out = new LinkedHashMap<>();
        if (temperature != null && !suppressTemperature) {
            out.put("temperature", temperature);
        }
        if (topPSet) {
            out.put("top_p", topP);
        }
        return out;
    }

    public static final class PromptSelection {
        private final String templateId;
        private final Map<String, String> variables;

        private PromptSelection(String templateId, Map<String, String> variables) {
            this.templateId = templateId;
            this.variables = variables == null ? null : Collections.unmodifiableMap(new LinkedHashMap<>(variables));
        }

        public String templateId() {
            return templateId;
        }

        public Map<String, String> variables() {
            return variables;
        }
    }

    private static String resolveApiKey(String apiKey) {
        if (apiKey == null || !apiKey.startsWith(KEY_PREFIX)) {
            throw new IllegalArgumentException(
                    "nRouter API keys must start with '" + KEY_PREFIX
                            + "'; pass apiKey or set " + ENV_KEY + ".");
        }
        return apiKey;
    }

    private static String normalizeKey(String key) {
        return key.toLowerCase(Locale.ROOT).replace("_", "");
    }

    private static boolean containsIgnoreCase(String value, String needle) {
        return value != null && value.toLowerCase(Locale.ROOT).contains(needle);
    }

    private static void requireUsable(String name, double value, Double max) {
        if (!Double.isFinite(value)) {
            throw new IllegalArgumentException(name + " must be a finite number.");
        }
        if (value < 0 || (max != null && value > max)) {
            String range = max == null ? "0 or greater" : "between 0 and " + max;
            throw new IllegalArgumentException(name + " must be " + range + ", got " + value + ".");
        }
    }
}
