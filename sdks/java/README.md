# nRouter SDK (Java)

SDK for the [nRouter](https://nrouter.ai) LLM gateway — one API key for models across six provider clouds (Alibaba US, OpenAI, AWS Bedrock, Azure Foundry, Google Vertex AI, Anthropic). A thin factory
around the official `openai-java` client — same API surface, pre-configured for nRouter.

## Install

```xml
<dependency>
    <groupId>ai.nrouter</groupId>
    <artifactId>nrouter-sdk</artifactId>
    <version>2.2.0</version>
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
                .model("claude-sonnet-4-5")
                .addMessage(ChatCompletionMessageParam.ofUser(
                        ChatCompletionUserMessageParam.builder()
                                .content("Hello!")
                                .build()
                ))
                .build()
);
System.out.println(response.choices().get(0).message().content());
```

`NRouter.create()` returns a real `OpenAIClient`, so every resource `openai-java`
supports works unmodified.

### Native response metadata and typed errors

Use the additive Java 11 client when you need nRouter response headers or
gateway-specific error classification:

```java
import ai.nrouter.sdk.NRouterHttpClient;
import ai.nrouter.sdk.NRouterHttpResponse;
import java.util.Map;

NRouterHttpClient client = NRouter.httpClient();
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
