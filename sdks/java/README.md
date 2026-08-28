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

They are enforced at the **gateway**, not in this package, so they behave the
same from every nRouter SDK. Three of them are ALWAYS ON for every request on
the key, and this client cannot switch them off:

- [Guardrails](https://nrouter.ai/docs/guides/guardrails) — PII redaction and
  injection protection, pre-call and post-call.
- [Budget controls](https://nrouter.ai/docs/guides/budget-controls) — spend
  limits per key, team and organization.
- [Observability](https://nrouter.ai/docs/guides/observability) — per-request
  cost and usage.

[Routing and fallbacks](https://nrouter.ai/docs/guides/router-settings) are
different: **opt-in, by what you put in `model`.** Name a Smart Router alias and
you get the strategy and its fallback chain; name a concrete model and it is
never re-routed and inherits no hidden platform fallback. Worth knowing before
you rely on failover you have not actually enabled.
- [Java quickstart](https://nrouter.ai/docs/sdks/java) and the
  [API reference](https://nrouter.ai/docs/api-reference).
