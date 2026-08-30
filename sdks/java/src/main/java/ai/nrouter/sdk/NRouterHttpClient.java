package ai.nrouter.sdk;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.Map;
import java.util.Set;

/** Native Java 11 client for callers who need x-nr metadata and typed errors. */
public final class NRouterHttpClient {
    private static final Set<String> ERROR_CODES = Set.of(
            "invalid_request", "guardrail_blocked", "invalid_api_key", "insufficient_credits",
            "model_not_found", "rate_limit_exceeded", "tpm_limit_exceeded",
            "credit_check_failed", "service_unavailable");
    private final String apiKey;
    private final String baseUrl;
    private final HttpClient http;
    private final ObjectMapper json = new ObjectMapper();

    NRouterHttpClient(String apiKey, String baseUrl) {
        this.apiKey = apiKey;
        this.baseUrl = baseUrl.replaceAll("/+$", "");
        this.http = HttpClient.newHttpClient();
    }

    public NRouterHttpResponse chatCompletions(Map<String, ?> body) { return post("/chat/completions", body); }
    public NRouterHttpResponse completions(Map<String, ?> body) { return post("/completions", body); }
    public NRouterHttpResponse messages(Map<String, ?> body) { return post("/messages", body); }
    public NRouterHttpResponse responses(Map<String, ?> body) { return post("/responses", body); }

    public NRouterHttpResponse post(String path, Object body) {
        try {
            String encoded = json.writeValueAsString(body);
            HttpRequest request = HttpRequest.newBuilder(URI.create(baseUrl + "/" + path.replaceFirst("^/+", "")))
                    .header("Authorization", "Bearer " + apiKey)
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(encoded))
                    .build();
            HttpResponse<String> response = http.send(request, HttpResponse.BodyHandlers.ofString());
            NRouterResponseMeta meta = NRouterResponseMeta.fromHeaders(response.headers());
            JsonNode parsed = json.readTree(response.body());
            if (response.statusCode() >= 200 && response.statusCode() < 300) {
                return new NRouterHttpResponse(parsed, meta, response.statusCode());
            }
            JsonNode node = parsed.has("error") ? parsed.get("error") : parsed;
            String message = node.hasNonNull("message") ? node.get("message").asText() : "nRouter request failed";
            String code = node.hasNonNull("code") ? node.get("code").asText() : null;
            if (code == null && node.hasNonNull("type") && ERROR_CODES.contains(node.get("type").asText())) {
                code = node.get("type").asText();
            }
            throw NRouterException.gateway(message, code, response.statusCode(), meta);
        } catch (NRouterException error) {
            throw error;
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw NRouterException.transport("nRouter request interrupted");
        } catch (Exception error) {
            throw NRouterException.transport(error.getMessage());
        }
    }
}
