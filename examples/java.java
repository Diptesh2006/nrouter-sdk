// nRouter — Java
// OpenAI Java SDK + guardrails (automatic) + prompt templates + cost tracking.
//
// Maven: com.openai:openai-java:2.2.0
//
// Guardrails, prompt templates, and cost tracking are all server-side.
// Blocked requests return 400 with {"error": "...", "code": "guardrail_blocked"}.
// Cost is in the x-nr-request-cost response header when the model is priced.

import com.openai.client.OpenAIClient;
import com.openai.client.okhttp.OpenAIOkHttpClient;
import com.openai.models.*;
import java.net.URI;
import java.net.http.*;

public class nRouterExample {
    static final String NROUTER_BASE = "https://api.nrouter.ai";
    static final String NROUTER_KEY = System.getenv("NROUTER_API_KEY");

    public static void main(String[] args) throws Exception {

        // ━━━ 1. Check guardrails + balance ━━━━━━━━━━━━━━━━━━━
        HttpClient http = HttpClient.newHttpClient();

        String guardrails = http.send(
            HttpRequest.newBuilder()
                .uri(URI.create(NROUTER_BASE + "/nrouter/guardrail/list"))
                .header("Authorization", "Bearer " + NROUTER_KEY)
                .build(),
            HttpResponse.BodyHandlers.ofString()
        ).body();
        System.out.println("Guardrails: " + guardrails);

        String balance = http.send(
            HttpRequest.newBuilder()
                .uri(URI.create(NROUTER_BASE + "/api/credits/balance"))
                .header("Authorization", "Bearer " + NROUTER_KEY)
                .build(),
            HttpResponse.BodyHandlers.ofString()
        ).body();
        System.out.println("Balance: " + balance);

        // ━━━ 2. Chat (org defaults auto-apply) ━━━━━━━━━━━━━━━━
        // Cache, guardrails, and rate limits auto-apply from org config.
        OpenAIClient client = OpenAIOkHttpClient.builder()
                .apiKey(NROUTER_KEY)
                .baseUrl(NROUTER_BASE + "/v1")
                .build();

        ChatCompletion response = client.chat().completions().create(
                ChatCompletionCreateParams.builder()
                        .model("claude-sonnet-4-20250514")
                        .addMessage(ChatCompletionMessageParam.ofUser(
                                ChatCompletionUserMessageParam.builder()
                                        .content("Hello!")
                                        .build()
                        ))
                        .build()
        );
        System.out.println(response.choices().get(0).message().content());

        // Per-request overrides (via raw HTTP POST):
        // By default, ALL org-enabled guardrails apply automatically.
        // The Java SDK does not support extra body fields natively — use cURL or
        // a raw HTTP POST with these fields in the JSON body:
        //   "nrouter_guardrail_ids": ["uuid1","uuid2"]
        //   "nrouter_prompt_template_id": "your-summarizer-id"
        //   "nrouter_prompt_variables": {"language": "Spanish", "max_length": "100"}
        //   "nrouter_cache": false   // disable cache for this request

        // ━━━ 3. PII blocked by guardrail ━━━━━━━━━━━━━━━━━━━━━
        try {
            client.chat().completions().create(
                ChatCompletionCreateParams.builder()
                    .model("gpt-4o")
                    .addMessage(ChatCompletionMessageParam.ofUser(
                        ChatCompletionUserMessageParam.builder()
                            .content("My SSN is 123-45-6789")
                            .build()
                    ))
                    .build()
            );
        } catch (Exception e) {
            System.out.println("Guardrail blocked: " + e.getMessage());
        }
    }
}
