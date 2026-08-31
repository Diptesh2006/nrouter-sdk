# nRouter — Every Language Guide

nRouter serves models from six provider clouds behind one API key, and **speaks the OpenAI wire format**. Any language with an OpenAI SDK works by changing two things:

```
base_url  →  https://api.nrouter.ai/v1
api_key   →  your NROUTER_API_KEY
```

That's it. Guardrails, prompt templates, credit tracking, and cost headers all work automatically regardless of language.

---

## Cost Transparency

Priced responses expose the exact USD cost in `x-nr-request-cost`. Unpriced responses
omit the amount and identify the result with `x-nr-cost-status: unpriced`.

```
HTTP/1.1 200 OK
x-nr-request-id: nrouter-a1b2c3d4e5f67890
x-nr-request-cost: 0.00347
x-nr-cost-status: exact
x-nr-model: gpt-5.5
x-nr-input-tokens: 42
x-nr-output-tokens: 18
x-nr-total-tokens: 60
```

| Header | What It Tells You |
|--------|------------------|
| `x-nr-request-id` | Unique ID for debugging / support tickets (always present) |
| `x-nr-request-cost` | Exact cost in USD; absent when the model is unpriced |
| `x-nr-cost-status` | `exact` or `unpriced` |
| `x-nr-model` | Model that served the request |
| `x-nr-input-tokens` | Input token count |
| `x-nr-output-tokens` | Output token count |
| `x-nr-total-tokens` | Total tokens, including cache tokens |
| `x-nr-cache-read-tokens` | Cache-read tokens; emitted only when nonzero |
| `x-nr-cache-write-tokens` | Cache-write tokens; emitted only when nonzero |
| `x-nr-limit-source` | Rate-limit source (`key`, `plan`, `team`, `user`, or `budget`) on 429 |

### Platform Fee (Already Deducted)

The cost in the header is the **model cost only**. Your platform fee (0-4%) was already applied when you purchased credits — not per-request. What you see is what you pay.

| Plan | Platform Fee | $100 Purchase → Credits |
|------|-------------|------------------------|
| Pay As You Go | 4% | $96.00 |
| Tier 2 ($100/mo) | 2% | $98.00 |
| Tier 3 ($1,200/yr) | 0% | $100.00 |
| Enterprise | 0% | $100.00 |

---

## cURL

> **Model availability.** `/v1/embeddings` and `/v1/images/generations` are
> mounted, but the model has to be enabled for your organization. Measured on
> 2026-08-25 the served catalogue carried no embedding and no image model, so
> the names in these snippets are illustrative. List what your key can actually
> reach with `GET /v1/models` before copying one.

```bash
# Chat completion
curl https://api.nrouter.ai/v1/chat/completions \
  -H "Authorization: Bearer $NROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'

# With prompt template override
curl https://api.nrouter.ai/v1/chat/completions \
  -H "Authorization: Bearer $NROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5.5",
    "messages": [{"role": "user", "content": "Summarize this report..."}],
    "nrouter_prompt_template_id": "your-template-id",
    "nrouter_prompt_variables": {"language": "Spanish", "max_length": "100"}
  }'

# Check cost from response headers
curl -i https://api.nrouter.ai/v1/chat/completions \
  -H "Authorization: Bearer $NROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5.4-mini",
    "messages": [{"role": "user", "content": "Hi"}]
  }' 2>&1 | grep -i "x-nr-request-cost"
# x-nr-request-cost: 0.000015

# Embeddings
curl https://api.nrouter.ai/v1/embeddings \
  -H "Authorization: Bearer $NROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "text-embedding-3-small",
    "input": "The quick brown fox"
  }'

# Image generation
curl https://api.nrouter.ai/v1/images/generations \
  -H "Authorization: Bearer $NROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "dall-e-3",
    "prompt": "A cat astronaut on Mars",
    "size": "1024x1024"
  }'

# List models
curl https://api.nrouter.ai/v1/models \
  -H "Authorization: Bearer $NROUTER_API_KEY"

# Streaming
curl https://api.nrouter.ai/v1/chat/completions \
  -H "Authorization: Bearer $NROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -N \
  -d '{
    "model": "claude-sonnet-4-5",
    "messages": [{"role": "user", "content": "Count to 10"}],
    "stream": true
  }'
```

---

## Python (Branded SDK)

```bash
pip install nrouter-sdk
```

```python
from nroutersdk import nRouter, nRouterGuardrailBlockedError, nRouterCreditError
import os

client = nRouter()  # reads NROUTER_API_KEY from env

# Chat
response = client.chat.completions.create(
    model="claude-sonnet-4-5",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)

# With prompt template
response = client.nrouter.chat(
    model="gpt-5.5",
    messages=[{"role": "user", "content": "Summarize this..."}],
    prompt_template_id="your-template-id",
    prompt_variables={"language": "Spanish"},
)

# Check what that call cost — reported per request, not polled from a balance.
meta = client.last_response
if meta.cost_status == "exact":
    print(f"cost ${meta.cost:.6f} | request {meta.request_id}")
else:
    print(f"cost unpriced ({meta.cost_status})")

# Error handling
try:
    response = client.chat.completions.create(
        model="gpt-5.5",
        messages=[{"role": "user", "content": "My SSN is 123-45-6789"}],
    )
except nRouterGuardrailBlockedError as e:
    print(f"Blocked: {e}")
except nRouterCreditError:
    print("Out of credits!")
```

---

## Python (Plain OpenAI SDK)

```bash
pip install openai
```

```python
from openai import OpenAI
import os

client = OpenAI(
    api_key=os.environ["NROUTER_API_KEY"],
    base_url="https://api.nrouter.ai/v1",
)

response = client.chat.completions.create(
    model="claude-sonnet-4-5",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)

# With prompt template (via extra_body)
response = client.chat.completions.create(
    model="gpt-5.5",
    messages=[{"role": "user", "content": "Summarize this..."}],
    extra_body={
        "nrouter_prompt_template_id": "your-template-id",
        "nrouter_prompt_variables": {"language": "Spanish"},
    },
)

# Read cost from raw response
response = client.chat.completions.with_raw_response.create(
    model="gpt-5.4-mini",
    messages=[{"role": "user", "content": "Hi"}],
)
cost = response.headers.get("x-nr-request-cost")
cost_status = response.headers.get("x-nr-cost-status")
print(f"Cost: ${float(cost):.6f}" if cost is not None else f"Cost status: {cost_status}")
parsed = response.parse()
print(parsed.choices[0].message.content)
```

---

## Node.js / TypeScript

```bash
npm install openai
```

```typescript
import OpenAI from "openai";

const client = new OpenAI({
  apiKey: process.env.NROUTER_API_KEY,
  baseURL: "https://api.nrouter.ai/v1",
});

// Chat
const response = await client.chat.completions.create({
  model: "claude-sonnet-4-5",
  messages: [{ role: "user", content: "Hello!" }],
});
console.log(response.choices[0].message.content);

// Streaming
const stream = await client.chat.completions.create({
  model: "gpt-5.5",
  messages: [{ role: "user", content: "Write a poem" }],
  stream: true,
});
for await (const chunk of stream) {
  process.stdout.write(chunk.choices[0]?.delta?.content || "");
}

// With prompt template
const withPrompt = await client.chat.completions.create({
  model: "gpt-5.5",
  messages: [{ role: "user", content: "Summarize this..." }],
  // @ts-ignore — nRouter-specific fields
  nrouter_prompt_template_id: "your-template-id",
  nrouter_prompt_variables: { language: "Spanish" },
});

// Read cost from raw response
const raw = await client.chat.completions
  .create({
    model: "gpt-5.4-mini",
    messages: [{ role: "user", content: "Hi" }],
  })
  .asResponse();
const cost = raw.headers.get("x-nr-request-cost");
const costStatus = raw.headers.get("x-nr-cost-status");
console.log(cost === null ? `Cost status: ${costStatus}` : `Cost: $${cost}`);

// Tool calling
const tools = await client.chat.completions.create({
  model: "gpt-5.5",
  messages: [{ role: "user", content: "What's the weather in Tokyo?" }],
  tools: [
    {
      type: "function",
      function: {
        name: "get_weather",
        description: "Get weather for a city",
        parameters: {
          type: "object",
          properties: { city: { type: "string" } },
          required: ["city"],
        },
      },
    },
  ],
});
```

---

## Go

A branded SDK lives in [`sdks/go/`](sdks/go/). It hands back all thirteen
`x-nr-*` headers and types the gateway's nine error codes, which the vendor
client cannot do without `.WithRawResponse()` plumbing at every call site:

```go
client, _ := nrouter.NewFromEnv() // reads NROUTER_API_KEY
res, err := client.ChatCompletions(ctx, map[string]any{
    "model":    "claude-sonnet-4-5",
    "messages": []any{map[string]any{"role": "user", "content": "Hello!"}},
})
// res.Meta.Cost is nil when unpriced. Nil is not zero.
```

The plain OpenAI client works too, and stays supported:

```bash
go get github.com/openai/openai-go
```

```go
package main

import (
    "context"
    "fmt"
    "os"

    "github.com/openai/openai-go"
    "github.com/openai/openai-go/option"
)

func main() {
    client := openai.NewClient(
        option.WithAPIKey(os.Getenv("NROUTER_API_KEY")),
        option.WithBaseURL("https://api.nrouter.ai/v1"),
    )

    // Chat
    response, err := client.Chat.Completions.New(context.Background(),
        openai.ChatCompletionNewParams{
            Model: "claude-sonnet-4-5",
            Messages: []openai.ChatCompletionMessageParamUnion{
                openai.UserMessage("Hello!"),
            },
        },
    )
    if err != nil {
        panic(err)
    }
    fmt.Println(response.Choices[0].Message.Content)

    // Read cost from response header
    // Use .WithRawResponse() to access headers
}
```

---

## Java

```xml
<!-- Maven -->
<dependency>
    <groupId>com.openai</groupId>
    <artifactId>openai-java</artifactId>
    <version>2.2.1</version>
</dependency>
```

```java
import com.openai.client.OpenAIClient;
import com.openai.client.okhttp.OpenAIOkHttpClient;
import com.openai.models.*;

public class nRouterExample {
    public static void main(String[] args) {
        OpenAIClient client = OpenAIOkHttpClient.builder()
            .apiKey(System.getenv("NROUTER_API_KEY"))
            .baseUrl("https://api.nrouter.ai/v1")
            .build();

        // Chat
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
    }
}
```

---

## Ruby

```bash
gem install ruby-openai
```

```ruby
require "openai"

client = OpenAI::Client.new(
  access_token: ENV["NROUTER_API_KEY"],
  uri_base: "https://api.nrouter.ai/v1",
)

# Chat
response = client.chat(
  parameters: {
    model: "claude-sonnet-4-5",
    messages: [{ role: "user", content: "Hello!" }],
  }
)
puts response.dig("choices", 0, "message", "content")

# Streaming
client.chat(
  parameters: {
    model: "gpt-5.5",
    messages: [{ role: "user", content: "Write a haiku" }],
    stream: proc do |chunk, _bytesize|
      content = chunk.dig("choices", 0, "delta", "content")
      print content if content
    end,
  }
)

# With prompt template
response = client.chat(
  parameters: {
    model: "gpt-5.5",
    messages: [{ role: "user", content: "Summarize this..." }],
    nrouter_prompt_template_id: "your-template-id",
    nrouter_prompt_variables: { language: "Spanish" },
  }
)

# Embeddings
response = client.embeddings(
  parameters: {
    model: "text-embedding-3-small",
    input: "The quick brown fox",
  }
)
puts response.dig("data", 0, "embedding").length  # 1536
```

---

## PHP

```bash
composer require openai-php/client
```

```php
<?php
require 'vendor/autoload.php';

$client = OpenAI::factory()
    ->withApiKey(getenv('NROUTER_API_KEY'))
    ->withBaseUri('https://api.nrouter.ai/v1')
    ->make();

// Chat
$response = $client->chat()->create([
    'model' => 'claude-sonnet-4-5',
    'messages' => [
        ['role' => 'user', 'content' => 'Hello!'],
    ],
]);
echo $response->choices[0]->message->content;

// Streaming
$stream = $client->chat()->createStreamed([
    'model' => 'gpt-5.5',
    'messages' => [
        ['role' => 'user', 'content' => 'Write a poem'],
    ],
]);
foreach ($stream as $response) {
    echo $response->choices[0]->delta->content;
}

// Embeddings
$response = $client->embeddings()->create([
    'model' => 'text-embedding-3-small',
    'input' => 'The quick brown fox',
]);
echo count($response->embeddings[0]->embedding); // 1536
```

---

## C# / .NET

```bash
dotnet add package OpenAI
```

```csharp
using OpenAI;
using OpenAI.Chat;

// Configure client
var client = new ChatClient(
    model: "claude-sonnet-4-5",
    credential: new ApiKeyCredential(Environment.GetEnvironmentVariable("NROUTER_API_KEY")!),
    options: new OpenAIClientOptions
    {
        Endpoint = new Uri("https://api.nrouter.ai/v1")
    }
);

// Chat
ChatCompletion response = await client.CompleteChatAsync(
    new ChatMessage[]
    {
        new UserChatMessage("Hello!"),
    }
);
Console.WriteLine(response.Content[0].Text);
```

---

## Rust (Branded SDK)

```toml
[dependencies]
nrouter = { path = "sdks/rust" } # from a checkout of this repository
```

```rust
use serde_json::json;

let client = nrouter::http::Client::from_env()?;      // reads NROUTER_API_KEY
let out = client.chat_completions(&json!({
    "model": "claude-sonnet-4-5",
    "messages": [{"role": "user", "content": "Hello!"}]
})).await?;

// Unpriced is unknown, not free — never render a None cost as 0.0.
match out.meta.cost {
    Some(usd) => println!("cost ${usd}"),
    None => println!("unpriced ({:?})", out.meta.cost_status),
}
```

`nrouter::client()` also returns an `async-openai` client pointed at the gateway,
for the OpenAI-shaped surface. See [`sdks/rust/`](sdks/rust/).

### Rust (Plain OpenAI SDK)

```toml
# Cargo.toml
[dependencies]
async-openai = "0.25"
tokio = { version = "1", features = ["full"] }
```

```rust
use async_openai::{
    config::OpenAIConfig,
    types::{CreateChatCompletionRequestArgs, ChatCompletionRequestUserMessageArgs},
    Client,
};

#[tokio::main]
async fn main() {
    let config = OpenAIConfig::new()
        .with_api_key(std::env::var("NROUTER_API_KEY").unwrap())
        .with_api_base("https://api.nrouter.ai/v1");

    let client = Client::with_config(config);

    let request = CreateChatCompletionRequestArgs::default()
        .model("claude-sonnet-4-5")
        .messages(vec![
            ChatCompletionRequestUserMessageArgs::default()
                .content("Hello!")
                .build().unwrap()
                .into(),
        ])
        .build().unwrap();

    let response = client.chat().create(request).await.unwrap();
    println!("{}", response.choices[0].message.content.as_ref().unwrap());
}
```

---

## Kotlin (Branded SDK)

```kotlin
// build.gradle.kts
repositories { mavenLocal() }
implementation("ai.nrouter:nrouter-sdk-kotlin:2.2.1")
```

```kotlin
import ai.nrouter.sdk.NRouter
import org.json.JSONObject

val client = NRouter()                        // reads NROUTER_API_KEY

val result = client.chatCompletions(
    JSONObject()
        .put("model", "claude-sonnet-4-5")
        .put("messages", listOf(mapOf("role" to "user", "content" to "Hello!")))
)

// Typed errors from the gateway's nine codes, and all 13 x-nr-* headers.
// Unpriced is unknown, not free — never render a null cost as 0.
println(if (result.meta.isPriced) "cost $${result.meta.cost}" else "unpriced")
```

**Android:** use `ai.nrouter:nrouter-sdk-android` instead — `System.getenv` returns
null on Android, so the env fallback silently resolves to nothing there. See
[`sdks/android/`](sdks/android/).

### Kotlin (Plain OpenAI SDK)

```kotlin
// Using OpenAI Kotlin SDK
val client = OpenAI(
    OpenAIConfig(
        token = System.getenv("NROUTER_API_KEY"),
        host = OpenAIHost(baseUrl = "https://api.nrouter.ai/v1"),
    )
)

val response = client.chatCompletion(
    ChatCompletionRequest(
        model = ModelId("claude-sonnet-4-5"),
        messages = listOf(
            ChatMessage(role = ChatRole.User, content = "Hello!")
        ),
    )
)
println(response.choices[0].message.content)
```

---

## Swift (Branded SDK)

```swift
// Package.swift
.package(url: "https://github.com/nRouterAI/nrouter-sdk.git", from: "2.2.1")
```

```swift
import NRouter

let client = try NRouter(apiKey: myKey)        // no env on iOS — pass the key

let result = try await client.chatCompletions([
    "model": "claude-sonnet-4-5",
    "messages": [["role": "user", "content": "Hello!"]],
])

// Unpriced is unknown, not free — never render a nil cost as 0.
print(result.meta.isPriced ? "cost $\(result.meta.cost!)" : "unpriced")
```

Zero external dependencies; URLSession and async/await only. See
[`sdks/swift/`](sdks/swift/).

### Swift (Plain OpenAI SDK)

```swift
import OpenAI

let configuration = OpenAI.Configuration(
    token: ProcessInfo.processInfo.environment["NROUTER_API_KEY"]!,
    host: "api.nrouter.ai"
)
let openAI = OpenAI(configuration: configuration)

let query = ChatQuery(
    messages: [.init(role: .user, content: "Hello!")],
    model: .init("claude-sonnet-4-5")
)

let result = try await openAI.chats(query: query)
print(result.choices[0].message.content ?? "")
```

---

## Dart / Flutter (Branded SDK)

```yaml
dependencies:
  nrouter:
    path: sdks/dart # from a checkout of this repository
```

```dart
import 'package:nrouter/nrouter.dart';

final client = NRouter(apiKey: myKey);

final result = await client.chatCompletions({
  'model': 'claude-sonnet-4-5',
  'messages': [{'role': 'user', 'content': 'Hello!'}],
});

// Unpriced is unknown, not free — never render a null cost as 0.
print(result.meta.isPriced ? 'cost \$${result.meta.cost}' : 'unpriced');
client.close();
```

One dependency (`http`), so the same code runs on Flutter mobile, desktop, **web**
and the plain Dart VM. There is deliberately no `NROUTER_API_KEY` fallback:
`Platform.environment` needs `dart:io`, which does not exist in a web build. See
[`sdks/dart/`](sdks/dart/).

### Dart / Flutter (Plain OpenAI SDK)

```yaml
# pubspec.yaml
dependencies:
  dart_openai: ^5.0.0
```

```dart
import 'package:dart_openai/dart_openai.dart';

void main() async {
  OpenAI.apiKey = Platform.environment['NROUTER_API_KEY']!;
  OpenAI.baseUrl = 'https://api.nrouter.ai';

  final response = await OpenAI.instance.chat.create(
    model: 'claude-sonnet-4-5',
    messages: [
      OpenAIChatCompletionChoiceMessageModel(
        role: OpenAIChatMessageRole.user,
        content: [OpenAIChatCompletionChoiceMessageContentItemModel.text('Hello!')],
      ),
    ],
  );
  print(response.choices[0].message.content?[0].text);
}
```

---

## Elixir

```elixir
# config/config.exs
config :openai,
  api_key: System.get_env("NROUTER_API_KEY"),
  api_url: "https://api.nrouter.ai/v1"

# Usage
{:ok, response} = OpenAI.chat_completion(
  model: "claude-sonnet-4-5",
  messages: [%{role: "user", content: "Hello!"}]
)
IO.puts(hd(response.choices)["message"]["content"])
```

---

## HTTPie (CLI)

```bash
# Quick one-liner
http POST https://api.nrouter.ai/v1/chat/completions \
  Authorization:"Bearer $NROUTER_API_KEY" \
  model=claude-sonnet-4-5 \
  messages:='[{"role":"user","content":"Hello!"}]'
```

---

## Cost Tracking in Every Language

Every language can read the cost header from the raw HTTP response:

| Language | How to Read `x-nr-request-cost` |
|----------|--------------------------------------|
| **cURL** | `curl -i ... \| grep x-nr-request-cost` |
| **Python (nroutersdk)** | `client.last_response.cost` |
| **Python (openai)** | `client.chat.completions.with_raw_response.create(...)` then `response.headers["x-nr-request-cost"]` |
| **Node.js** | `client.chat.completions.create(...).asResponse()` then `response.headers.get("x-nr-request-cost")` |
| **Go** | Access `resp.Header.Get("x-nr-request-cost")` from raw response |
| **Java** | Intercept via OkHttp interceptor |
| **Ruby** | Response hash includes headers |
| **PHP** | `$response->meta()['x-nr-request-cost']` |
| **C#** | Custom `DelegatingHandler` to capture headers |
| **Rust** | `response.headers.get("x-nr-request-cost")` |

### Cost Estimation Before You Call

```bash
# Check model pricing
curl https://api.nrouter.ai/v1/models \
  -H "Authorization: Bearer $NROUTER_API_KEY"
```

```python
# Python — the models this key can reach
for model in client.models.list().data:
    print(model.id)
```

Per-request cost is reported on the response itself, on the `x-nr-request-cost`
header, paired with `x-nr-cost-status`. The header is **absent** when the model
is unpriced — nRouter never reports a confident `0`.

### Per-Request Cost

```python
# Python — every call populates last_response from the x-nr-* headers
client.chat.completions.create(
    model="gpt-5.5",
    messages=[{"role": "user", "content": "Hello!"}],
    max_tokens=512,
)

meta = client.last_response
print(f"request {meta.request_id} | model {meta.model}")
print(f"tokens  {meta.input_tokens} in / {meta.output_tokens} out")

# Branch on cost_status, never on `cost` being falsy: an unpriced model reports
# cost=None, and treating that as $0 is how a margin leak looks like revenue.
if meta.cost_status == "exact":
    print(f"cost    ${meta.cost:.6f}")
else:
    print(f"cost    unpriced")
```

Balances, spend history and guardrail logs are org-scoped billing data and live
in the dashboard at <https://app.nrouter.ai>, not on the inference API.
