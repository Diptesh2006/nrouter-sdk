import ai.nrouter.sdk.NRouter;
import ai.nrouter.sdk.NRouterHttpClient;
import ai.nrouter.sdk.NRouterHttpResponse;
import java.util.List;
import java.util.Map;

/** A normal chat-completions request using the TypeSafe Jev System One model. */
class JevSystemOneExample {
    public static void main(String[] args) {
        NRouterHttpClient client = NRouter.httpClient(System.getenv("NROUTER_API_KEY"));
        NRouterHttpResponse response = client.chatCompletions(Map.of(
                "model", "typesafe/jev",
                "temperature", 0,
                "max_tokens", 128,
                "messages", List.of(
                        Map.of("role", "system", "content",
                                "Classify the incident. Return JSON only with priority, queue, and summary."),
                        Map.of("role", "user", "content",
                                "Production payment requests return HTTP 500 in two regions."))));

        System.out.println("Decision: " + response.body().at("/choices/0/message/content").asText());
        System.out.println("Request ID: " + response.meta().requestId());
        System.out.println("Served model: " + response.meta().model());
        System.out.println(response.meta().isPriced()
                ? "Exact cost: $" + response.meta().cost()
                : "Cost status: " + response.meta().costStatus());
    }
}
