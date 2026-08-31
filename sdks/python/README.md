# nRouter Python SDK

[![PyPI](https://img.shields.io/pypi/v/nrouter-sdk?logo=pypi&logoColor=white&label=nrouter-sdk)](https://pypi.org/project/nrouter-sdk/)
[![Python Versions](https://img.shields.io/pypi/pyversions/nrouter-sdk.svg)](https://pypi.org/project/nrouter-sdk/)
[![PyPI publish](https://github.com/nRouterAI/nrouter-sdk/actions/workflows/publish-pypi.yml/badge.svg)](https://github.com/nRouterAI/nrouter-sdk/actions/workflows/publish-pypi.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

The official Python client library for the [nRouter](https://nrouter.ai) LLM gateway.

One API key for models across six provider clouds — OpenAI, Anthropic, AWS Bedrock, Google Vertex AI, Azure Foundry, and Alibaba Cloud. Features built-in automatic cost tracking (`x-nr-*` metadata capture), guardrails, response caching, prompt templates, and typed exception handling.

---

## Installation

```bash
pip install nrouter-sdk
```

---

## Authentication & Setup

The SDK automatically reads your API key from the `NROUTER_API_KEY` environment variable.

### 1. Set your environment variable
```bash
# Get your API key from https://nrouter.ai/dashboard/keys
export NROUTER_API_KEY="sk-nrouter-your-api-key-here"
```

### 2. (Optional) Pass the key explicitly in code
```python
from nroutersdk import nRouter

client = nRouter(api_key="sk-nrouter-your-api-key-here")
```

All API keys must start with the `sk-nrouter-` prefix.

---

## Quick Start

### Synchronous Client (`nRouter`)

```python
from nroutersdk import nRouter

# Automatically reads NROUTER_API_KEY from environment
client = nRouter()

response = client.chat.completions.create(
    model="claude-sonnet-4-5-20250929",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello from Python!"},
    ],
)

# Output completion text
print(response.choices[0].message.content)

# Cost and Request Metadata (captured automatically)
meta = client.last_response
print(f"Request ID: {meta.request_id}")
print(f"Model: {meta.model}")
if meta.cost is not None:
    print(f"Cost: ${meta.cost:.6f}")
else:
    print(f"Cost: unpriced ({meta.cost_status})")
```

### Asynchronous Client (`AsyncnRouter`)

```python
import asyncio
from nroutersdk import AsyncnRouter

async def main():
    client = AsyncnRouter()

    response = await client.chat.completions.create(
        model="claude-sonnet-4-5-20250929",
        messages=[{"role": "user", "content": "Explain quantum computing in one sentence."}],
    )

    print(response.choices[0].message.content)
    print(f"Cost: ${client.last_response.cost}")

asyncio.run(main())
```

---

## Core Capabilities

### 1. Streaming Responses

Stream completions incrementally using Server-Sent Events (SSE):

```python
from nroutersdk import nRouter

client = nRouter()

stream = client.chat.completions.create(
    model="claude-sonnet-4-5-20250929",
    messages=[{"role": "user", "content": "Write a short poem about routers."}],
    stream=True,
)

for chunk in stream:
    content = chunk.choices[0].delta.content
    if content:
        print(content, end="", flush=True)
print()
```

### 2. Anthropic Messages API

Use Anthropic's Messages format directly on the exact same `sk-nrouter-` API key:

```python
from nroutersdk import nRouter

client = nRouter()

message = client.messages.create(
    model="claude-sonnet-4-5-20250929",
    messages=[{"role": "user", "content": "Hello via Anthropic Messages!"}],
    max_tokens=256,
)

print(message["content"][0]["text"])
print(f"Cost: ${client.last_response.cost}")
```

Count tokens before calling:
```python
token_count = client.messages.count_tokens(
    model="claude-sonnet-4-5-20250929",
    messages=[{"role": "user", "content": "How many tokens is this?"}],
)
print(f"Tokens: {token_count['input_tokens']}")
```

### 3. Response Metadata & Cost Tracking

The gateway emits canonical `x-nr-*` headers with every response. `client.last_response` captures these automatically:

```python
meta = client.last_response

print("Request ID:        ", meta.request_id)
print("Exact Cost (USD):  ", meta.cost)
print("Cost Status:       ", meta.cost_status)        # "exact" or "unpriced"
print("Served Model:      ", meta.model)
print("Input Tokens:      ", meta.input_tokens)
print("Output Tokens:     ", meta.output_tokens)
print("Total Tokens:      ", meta.total_tokens)
print("Cache Read Tokens: ", meta.cache_read_tokens)
print("Cache Write Tokens:", meta.cache_write_tokens)
print("Gateway Cache:     ", meta.response_cache)     # "hit", "miss", or None
print("Cache Age (s):     ", meta.response_cache_age) # seconds on hits
```

> **Note on Cost Accuracy:** Unpriced models return `cost=None` and `cost_status="unpriced"`. Never treat `None` as `$0.00` — free routes (like `/v1/messages/count_tokens`) emit no cost header, while billable inferences always track usage.

### 4. Prompt Templates & Versioning

Pass managed prompt template IDs and variable substitutions directly with requests:

```python
from nroutersdk import nRouter, prompt_template

client = nRouter()

# Inject template ID and variables
extra_body = prompt_template(
    template_id="pt_customer_support_v2",
    variables={"customer_name": "Alice", "issue_type": "Billing"}
)

response = client.chat.completions.create(
    model="claude-sonnet-4-5-20250929",
    messages=[{"role": "user", "content": "I need help with my account."}],
    extra_body=extra_body,
)
```

### 5. Client-Side Conversation Memory

Safely manage turn history and multi-turn context without leaking tenant headers:

```python
from nroutersdk import create_memory

memory = create_memory()
memory.add({"role": "user", "content": "My name is Bob."})
memory.add({"role": "assistant", "content": "Nice to meet you, Bob!"})
memory.add({"role": "user", "content": "What is my name?"})

response = client.chat.completions.create(
    model="claude-sonnet-4-5-20250929",
    messages=memory.messages(),
)
print(response.choices[0].message.content)
```

### 6. Model Discovery & Smart Routing

List all models currently enabled for your organization:

```python
models = client.models.list()
for m in models.data:
    print(f"Model ID: {m.id}")
```

#### Smart Router Aliases
You can specify Smart Router aliases in the `model` parameter to activate automatic fallback and load-balancing chains:

```python
# Alias routes through configured strategies and failovers
response = client.chat.completions.create(
    model="my-production-router",
    messages=[{"role": "user", "content": "Hello!"}],
)
```

---

## Error Handling

All gateway refusals are converted into typed exceptions:

```python
from nroutersdk import (
    nRouter,
    nRouterGuardrailBlockedError,
    nRouterCreditError,
    nRouterRateLimitError,
    nRouterAuthenticationError,
    nRouterNotFoundError,
    nRouterRequestError,
    nRouterServiceError,
    nRouterError,
)

client = nRouter()

try:
    response = client.chat.completions.create(
        model="claude-sonnet-4-5-20250929",
        messages=[{"role": "user", "content": "Analyze sensitive data..."}],
    )
except nRouterGuardrailBlockedError as e:
    print(f"Request blocked by guardrails: {e}")
except nRouterCreditError as e:
    print(f"Insufficient credits: {e}")
except nRouterRateLimitError as e:
    print(f"Rate limit exceeded: {e}")
except nRouterAuthenticationError as e:
    print(f"Invalid API key: {e}")
except nRouterNotFoundError as e:
    print(f"Model not found: {e}")
except nRouterServiceError as e:
    print(f"Gateway service unavailable: {e}")
except nRouterError as e:
    print(f"General nRouter error: {e}")
```

| Exception | HTTP Status | Meaning |
|---|---|---|
| `nRouterRequestError` | 400 | Malformed request body or parameters |
| `nRouterGuardrailBlockedError` | 400 | Content blocked by pre-call / post-call guardrail |
| `nRouterAuthenticationError` | 401 | Invalid or missing `sk-nrouter-` API key |
| `nRouterCreditError` | 402 | Account has insufficient credits |
| `nRouterBudgetExceededError` | 402 / 429 | Key, team, or org spend ceiling exceeded |
| `nRouterNotFoundError` | 404 | Model or endpoint not found |
| `nRouterRateLimitError` | 429 | RPM or TPM rate limit exceeded |
| `nRouterServiceError` | 503 | Gateway or upstream provider temporary outage |

---

## Advanced Configuration

### Custom Base URL & Timeouts

```python
import httpx
from nroutersdk import nRouter

client = nRouter(
    base_url="https://api-stage.nrouter.ai/v1",  # Stage gateway
    timeout=httpx.Timeout(60.0, connect=10.0),
    max_retries=3,
)
```

---

## Supported Endpoints

All endpoints route through `https://api.nrouter.ai/v1`:

| Endpoint | Method | Description |
|---|---|---|
| `/v1/chat/completions` | `client.chat.completions.create()` | OpenAI-compatible chat |
| `/v1/messages` | `client.messages.create()` | Anthropic-compatible Messages |
| `/v1/messages/count_tokens` | `client.messages.count_tokens()` | Pre-call token counting |
| `/v1/completions` | `client.completions.create()` | Legacy text completions |
| `/v1/embeddings` | `client.embeddings.create()` | Text embeddings |
| `/v1/images/generations` | `client.images.generate()` | Image generation |
| `/v1/audio/speech` | `client.audio.speech.create()` | Text-to-Speech (TTS) |
| `/v1/audio/transcriptions` | `client.audio.transcriptions.create()` | Speech-to-Text (STT) |
| `/v1/audio/translations` | `client.audio.translations.create()` | Audio translations |
| `/v1/responses` | `client.responses.create()` | OpenAI Responses API |
| `/v1/models` | `client.models.list()` | Organization model catalog |
| `/v1/videos` | `POST /v1/videos` | Video generation jobs |

---

## Documentation & Resources

* [nRouter Documentation](https://nrouter.ai/docs)
* [API Reference](https://nrouter.ai/docs/api-reference)
* [Python Quickstart Guide](https://nrouter.ai/docs/sdks/python)
* [Live Model Catalog](https://nrouter.ai/models)
* [Dashboard & API Keys](https://nrouter.ai/dashboard/keys)
