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

public class nRouterExample {
    static final String NROUTER_BASE = "https://api.nrouter.ai";
    static final String NROUTER_KEY = System.getenv("NROUTER_API_KEY");

    public static void main(String[] args) throws Exception {

        // Guardrails, prompt templates, rate limits and budgets are configured in
        // the dashboard and enforced server-side on every request. There is
        // deliberately no endpoint to list or override them: a request cannot opt
        // out of its own org policy. Balances and spend history live at
        // https://app.nrouter.ai — org billing data, not inference. Per-request
        // cost arrives on the x-nr-request-cost response header.

        // ━━━ 1. Chat (org defaults auto-apply) ━━━━━━━━━━━━━━━━
        // Cache, guardrails, and rate limits auto-apply from org config.
        OpenAIClient client = OpenAIOkHttpClient.builder()
                .apiKey(NROUTER_KEY)
                .baseUrl(NROUTER_BASE + "/v1")
                .build();

        ChatCompletion response = client.chat().completions().create(
                ChatCompletionCreateParams.builder()
                        .model("anthropic/claude-sonnet-4-5-20250929")
                        .addMessage(ChatCompletionMessageParam.ofUser(
                                ChatCompletionUserMessageParam.builder()
                                        .content("Hello!")
                                        .build()
                        ))
                        .build()
        );
        System.out.println(response.choices().get(0).message().content());

        // Guardrails are assigned per key, team or org in the dashboard and
        // apply automatically — the narrowest assignment wins. There is no
        // per-request override to send in the body.
        //
        // Per-request overrides (via raw HTTP POST):
        // The Java SDK does not support extra body fields natively — use cURL or
        // a raw HTTP POST with these fields in the JSON body:
        //   "nrouter_prompt_template_id": "your-summarizer-id"
        //   "nrouter_prompt_variables": {"language": "Spanish", "max_length": "100"}
        //   "nrouter_cache": false   // disable cache for this request

        // ━━━ 2. PII blocked by guardrail ━━━━━━━━━━━━━━━━━━━━━
        try {
            client.chat().completions().create(
                ChatCompletionCreateParams.builder()
                    .model("anthropic/claude-sonnet-4-5-20250929")
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
