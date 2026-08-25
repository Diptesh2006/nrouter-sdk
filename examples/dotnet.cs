// nRouter — C# / .NET
// OpenAI NuGet + guardrails (automatic) + cost tracking via headers.
//
// dotnet add package OpenAI
//
// Guardrails, prompt templates, and cost tracking are all server-side.
// Blocked requests throw with {"error": "...", "code": "guardrail_blocked"}.
// Cost is in the x-nr-request-cost response header when the model is priced.

using OpenAI;
using OpenAI.Chat;
using System.Net.Http;
using System.Text.Json;

var nrouterBase = "https://api.nrouter.ai";
var nrouterKey = Environment.GetEnvironmentVariable("NROUTER_API_KEY")!;

// ━━━ 1. Check guardrails + balance ━━━━━━━━━━━━━━━━━━━━━━━━━
var http = new HttpClient();
http.DefaultRequestHeaders.Add("Authorization", $"Bearer {nrouterKey}");

// Guardrails, prompt templates, rate limits and budgets are configured in the
// dashboard and enforced server-side on every request. There is deliberately no
// endpoint to list or override them: a request cannot opt out of its org policy.
// Balances and spend history live at https://app.nrouter.ai — org billing data,
// not inference. Per-request cost arrives on the x-nr-request-cost header.
// ━━━ 2. Chat (org defaults auto-apply) ━━━━━━━━━━━━━━━━━━━━━━
// Cache, guardrails, and rate limits auto-apply from org config.
var client = new ChatClient(
    model: "claude-sonnet-4-5",
    credential: new ApiKeyCredential(nrouterKey),
    options: new OpenAIClientOptions { Endpoint = new Uri($"{nrouterBase}/v1") }
);

ChatCompletion response = await client.CompleteChatAsync(
    new ChatMessage[] { new UserChatMessage("Hello!") }
);
Console.WriteLine(response.Content[0].Text);

// Per-request overrides (via raw HTTP POST):
// The .NET SDK does not support extra body fields natively — use raw HTTP POST
// with these fields in the JSON body:
//   "nrouter_prompt_template_id": "your-summarizer-id"
//   "nrouter_prompt_variables": {"language": "Spanish", "max_length": "100"}
//   "nrouter_guardrail_ids": ["uuid1","uuid2"]
//   "nrouter_cache": false   // disable cache for this request

// ━━━ 3. PII blocked by guardrail ━━━━━━━━━━━━━━━━━━━━━━━━━━
try {
    await client.CompleteChatAsync(
        new ChatMessage[] { new UserChatMessage("My SSN is 123-45-6789") }
    );
} catch (Exception e) {
    Console.WriteLine($"Guardrail blocked: {e.Message}");
}

