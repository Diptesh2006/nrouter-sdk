# nRouter SDK (Java)

SDK for the [nRouter](https://nrouter.ai) LLM gateway — one API key for models across six provider clouds (Alibaba US, OpenAI, AWS Bedrock, Azure Foundry, Google Vertex AI, Anthropic). A thin factory
around the official `openai-java` client — same API surface, pre-configured for nRouter.

## Install

```xml
<dependency>
    <groupId>ai.nrouter</groupId>
    <artifactId>nrouter-sdk</artifactId>
    <version>2.2.1</version>
</dependency>
```

## Authentication & Setup

The SDK automatically reads your API key from the `NROUTER_API_KEY` environment variable:

```bash
export NROUTER_API_KEY="sk-nrouter-your-api-key-here"
```

## Usage

```java
import ai.nrouter.sdk.NRouter;
import com.openai.client.OpenAIClient;
import com.openai.models.chat.completions.ChatCompletion;
import com.openai.models.chat.completions.ChatCompletionCreateParams;
import com.openai.models.ChatCompletionMessageParam;
import com.openai.models.ChatCompletionUserMessageParam;

OpenAIClient client = NRouter.create(); // reads NROUTER_API_KEY from env

ChatCompletion response = client.chat().completions().create(
        ChatCompletionCreateParams.builder()
                .model("gpt-5.4-mini")
                .addMessage(ChatCompletionMessageParam.ofUser(
                        ChatCompletionUserMessageParam.builder()
                                .content("Hello!")
                                .build()
                ))
                .build()
);
System.out.println(response.choices().get(0).message().content());
```

`NRouter.create()` returns a real `OpenAIClient`, so the resources nRouter
serves are called exactly as you would call them against OpenAI.

> ⚠️ **`OpenAIClient` compiles against a larger API than nRouter serves, and the
> model is what decides whether a compiling call reaches anything.**
> `openai-java` posts `client.chat().completions()` to `/v1/chat/completions`,
> and neither Anthropic nor AWS Bedrock declares a chat-completions path — they
> serve `/v1/messages` — so the call is a **404 from the gateway**, not a
> translation. That is why the snippet above names an OpenAI-wire model rather
> than a Claude alias. The 404 body is
> `{"error":{"type":"gateway_error","message":"<model> is not available on <route>"}}`;
> there is no `code` field to branch on, so match on the status and the route.
>
> **Use the native `NRouterHttpClient.messages(...)`, below, for any Anthropic
> or AWS Bedrock model.** `client.chat().completions()` is right for a model whose
> provider serves that route — OpenAI, Azure OpenAI, Azure AI Foundry, Vertex
> AI, Alibaba DashScope. `/v1/responses` is narrower still: OpenAI and Azure
> only. `client.completions()` (legacy `/v1/completions`) is narrower again:
> OpenAI only. And `embeddings()`, `images()` and `audio()` are mounted but
> served on the **OpenAI cloud only** — a Vertex or DashScope alias 404s there
> even though the chat call with the same alias works.
>
> Resolve it per model rather than by name — an alias does not have to spell its
> provider. Every entry `GET /v1/models` returns carries an
> `nrouter_endpoints` array naming the routes that alias answers on (for a
> Claude alias, `["/v1/messages", "/v1/messages/count_tokens"]`). Read it from
> `client.models().list()` and pick the call that matches, rather than inferring
> a wire from the id. An **empty** array is a real answer, not a gap: a Bedrock
> alias outside the Anthropic family serves no text wire at all, so no
> `openai-java` resource — and no `messages(...)` call either — will reach it.
>
> Resources nRouter mounts no route for at all — `files()`, `fineTuning()`,
> `batches()`, `beta()`, `vectorStores()`, `uploads()`, `containers()`,
> `conversations()`, `webhooks()`, `moderations()`, image edits — type-check and
> 404. `spec/nrouter-sdk-spec.json` is the served list.

### Native response metadata and typed errors

Use the additive Java 11 client when you need nRouter response headers or
gateway-specific error classification:

```java
import ai.nrouter.sdk.NRouterHttpClient;
import ai.nrouter.sdk.NRouterHttpResponse;
import java.util.Map;

NRouterHttpClient client = NRouter.httpClient(System.getenv("NROUTER_API_KEY"));
NRouterHttpResponse response = client.messages(Map.of(
        "model", "claude-haiku-4-5-20251001",
        "max_tokens", 64,
        "messages", java.util.List.of(Map.of("role", "user", "content", "Hello!"))
));

System.out.println(response.meta().requestId());
if (response.meta().isPriced()) {
    System.out.println(response.meta().cost());
}
```

`NRouterException` classifies the canonical gateway errors and preserves the
HTTP status plus the same response metadata. A missing cost header remains
unknown—it is never converted to zero.

The native client covers every operation in the canonical gateway spec:

| Capability | Named Java helpers |
|---|---|
| Text | `chatCompletions`, `completions`, `messages`, `responses`, `countTokens` |
| Discovery | `models`, `model` |
| Image and embeddings | `imagesGenerations`, `embeddings` |
| Audio | `audioSpeech`, `audioTranscriptions`, `audioTranslations` |
| Video | `createVideo`, `retrieveVideo`, `downloadVideoContent` |
| Incremental SSE | `chatCompletionsStream`, `completionsStream`, `messagesStream`, `responsesStream` |

Audio uploads use multipart bodies and reject CR/LF header injection in field
names and filenames. Speech and video downloads return `NRouterBinaryResponse`
so bytes are never coerced through JSON or text. A malformed JSON success keeps
its status and `x-nr-*` metadata and warns that the request may have been billed.

## Features & Capabilities

- **Key Validation & Base URL**: Auto-reads `NROUTER_API_KEY`, enforces `sk-nrouter-` prefix, defaults to `https://api.nrouter.ai/v1`.
- **Client-Side Memory**: `NRouterMemory` provides in-memory turn management that ensures safe conversation history formatting and prevents tenancy header leaks.
- **Prompt Templates & Variables**: `NRouter.promptTemplate(templateId, variables)` and `NRouter.promptVariables(variables)` build canonical wire payloads for nRouter prompt templates.
- **Sampling Controls**: `NRouter.buildSamplingParams(...)` enforces gateway sampling policies (such as Claude temperature/top_p mutual exclusivity).

### Conversation Memory Example

```java
import ai.nrouter.sdk.NRouterMemory;
import java.util.Map;

NRouterMemory memory = NRouterMemory.createMemory();
memory.add(Map.of("role", "user", "content", "Hello!"));
memory.add(Map.of("role", "assistant", "content", "Hi! How can I help you today?"));

System.out.println("Stored messages: " + memory.messages().size());
```

## How guardrails, budgets and routing work

They are configured in the dashboard and enforced at the **gateway**, not in
this package. The useful guarantee is not that they are always on — it is that
**whatever you have enabled cannot be bypassed by a client**, this one
included, and behaves identically from every nRouter SDK and from raw `curl`.

- [Guardrails](https://nrouter.ai/docs/guides/guardrails) — PII redaction,
  injection protection, secret and keyword scanning, pre-call and post-call.
  Which ones run is resolved per request: the organization's guardrail switch
  first, then the narrowest applicable assignment wins across
  key > team > org > default, and a winner disabled at that scope does not run.
- [Budget controls](https://nrouter.ai/docs/guides/budget-controls) — spend
  limits per key, team and organization.
- [Observability](https://nrouter.ai/docs/guides/observability) — cost and usage
  on billable calls. Free routes are genuinely free and carry no
  `x-nr-request-cost`: `/v1/messages/count_tokens`, and video polling and
  content retrieval.

[Smart Router aliases and fallback chains](https://nrouter.ai/docs/guides/router-settings)
carry two conditions worth knowing before you rely on failover you have not
enabled:

- **Opt-in by what you put in `model`.** An alias gets the strategy and its
  chain; a concrete model is never re-routed and inherits no hidden fallback.
- **Text wires only** — chat completions, responses, messages and legacy
  completions. Audio, image and video calls take a single-provider route and
  are not cross-provider Smart Router wires.
- [Java quickstart](https://nrouter.ai/docs/sdks/java) and the
  [API reference](https://nrouter.ai/docs/api-reference).
