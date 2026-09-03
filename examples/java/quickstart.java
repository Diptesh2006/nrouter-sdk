// nRouter Java SDK — Claude Messages, metadata, managed prompts and SSE.
// Maven: ai.nrouter:nrouter-sdk:2.2.1

import ai.nrouter.sdk.NRouter;
import ai.nrouter.sdk.NRouterHttpClient;
import ai.nrouter.sdk.NRouterHttpResponse;
import ai.nrouter.sdk.NRouterStreamResponse;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

class nRouterExample {
    public static void main(String[] args) {
        NRouterHttpClient client = NRouter.httpClient(System.getenv("NROUTER_API_KEY"));

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("model", "claude-haiku-4-5-20251001");
        body.put("max_tokens", 256);
        body.put("messages", List.of(Map.of("role", "user", "content", "Summarize this release.")));
        body.putAll(NRouter.buildExtraBody(
                "your-summarizer-id",
                Map.of("audience", "SDK users"),
                null,
                false));

        NRouterHttpResponse response = client.messages(body);
        System.out.println(response.body().at("/content/0/text").asText());
        System.out.println("request=" + response.meta().requestId());
        System.out.println(response.meta().isPriced()
                ? "cost=$" + response.meta().cost()
                : "cost=unpriced");

        // Streaming is incremental. Closing the response closes the HTTP body stream.
        try (NRouterStreamResponse stream = client.messagesStream(body)) {
            stream.lines().forEach(System.out::println);
        }

        // Guardrails, budgets and routing are assigned in the dashboard and
        // enforced by the gateway; a request cannot override its own tenancy.
    }
}
