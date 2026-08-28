# nRouter SDK (Java)

SDK for the [nRouter](https://nrouter.ai) LLM gateway — one API key for models across six provider clouds (Alibaba US, OpenAI, AWS Bedrock, Azure Foundry, Google Vertex AI, Anthropic). A thin factory
around the official `openai-java` client — same API surface, pre-configured for nRouter.

## Install

```xml
<dependency>
    <groupId>ai.nrouter</groupId>
    <artifactId>nrouter-sdk</artifactId>
    <version>1.0.0</version>
</dependency>
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

## Basic only, for now

This is a minimal wrapper: API key resolution/validation (`sk-nrouter-...`) and a
default base URL of `https://api.nrouter.ai/v1`. It doesn't yet have the typed errors,
automatic cost-header capture, or `credits`/`guardrails`/`prompts` namespaces that
[`sdks/python/`](../python/) has — see that package for the fuller pattern this one will
grow into.

## How guardrails, budgets and routing work

They are enforced at the **gateway**, not in this package — so they apply to
every request on the key, they behave the same from every nRouter SDK, and this
client cannot turn them off:

- [Guardrails](https://nrouter.ai/docs/guides/guardrails) — PII redaction and
  injection protection, pre-call and post-call.
- [Budget controls](https://nrouter.ai/docs/guides/budget-controls) — spend
  limits per key, team and organization.
- [Routing and fallbacks](https://nrouter.ai/docs/guides/router-settings) —
  failover chains across providers.
- [Observability](https://nrouter.ai/docs/guides/observability) — per-request
  cost and usage.
- [Java quickstart](https://nrouter.ai/docs/sdks/java) and the
  [API reference](https://nrouter.ai/docs/api-reference).
