# nRouter Python SDK

[![PyPI](https://img.shields.io/pypi/v/nrouter-sdk?logo=pypi&logoColor=white&label=nrouter-sdk)](https://pypi.org/project/nrouter-sdk/)
[![Python Versions](https://img.shields.io/pypi/pyversions/nrouter-sdk.svg)](https://pypi.org/project/nrouter-sdk/)
[![CI](https://github.com/nRouterAI/nrouter-sdk/actions/workflows/ci.yml/badge.svg)](https://github.com/nRouterAI/nrouter-sdk/actions/workflows/ci.yml)
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

## Authentication & Environment Variables

The SDK automatically resolves its configuration from environment variables.

### 1. Set your environment variables
```bash
# Required: Get your API key from https://nrouter.ai/dashboard/keys
export NROUTER_API_KEY="sk-nrouter-your-api-key-here"

# Optional: Override base URL (e.g. for staging or local proxy)
export NROUTER_BASE_URL="https://api.nrouter.ai/v1"
```

### 2. Configuration Matrix

| Environment Variable | Parameter Name | Default Value | Description |
|---|---|---|---|
| `NROUTER_API_KEY` | `api_key` | *None* (Required) | API Key starting with `sk-nrouter-` |
| `NROUTER_BASE_URL` | `base_url` | `https://api.nrouter.ai/v1` | nRouter Gateway Base URL |

You can also pass parameters explicitly in code:
```python
from nroutersdk import nRouter

client = nRouter(
    api_key="sk-nrouter-your-api-key-here",
    base_url="https://api.nrouter.ai/v1",
)
```

---

## Quick Start

### Synchronous Client (`nRouter`)

```python
from nroutersdk import nRouter

# Uses context manager to ensure clean connection pool shutdown
with nRouter() as client:
    response = client.chat.completions.create(
        model="anthropic/claude-sonnet-4-5-20250929",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello from Python!"},
        ],
    )

    # Output completion text
    print(response.choices[0].message.content)

    # Cost and Request Metadata (captured automatically from x-nr-* headers)
    meta = client.last_response
    print(f"Request ID: {meta.request_id}")
    print(f"Model:      {meta.model}")
    if meta.cost is not None:
        print(f"Cost:       ${meta.cost:.6f}")
    else:
        print(f"Cost:       unpriced ({meta.cost_status})")
```

### Asynchronous Client (`AsyncnRouter`)

```python
import asyncio
from nroutersdk import AsyncnRouter

async def main():
    async with AsyncnRouter() as client:
        response = await client.chat.completions.create(
            model="anthropic/claude-sonnet-4-5-20250929",
            messages=[{"role": "user", "content": "Explain quantum computing in one sentence."}],
        )

        print(response.choices[0].message.content)
        print(f"Cost: ${client.last_response.cost}")

asyncio.run(main())
```

---

## Core Capabilities & Examples

| Example Script | Topic | Description |
|---|---|---|
| [`01_quickstart.py`](../../examples/python/01_quickstart.py) | **Quickstart** | Basic chat completion & metadata extraction |
| [`02_async_concurrency.py`](../../examples/python/02_async_concurrency.py) | **Async / Concurrency** | Concurrent requests with `asyncio.gather` |
| [`03_streaming.py`](../../examples/python/03_streaming.py) | **Streaming** | Server-Sent Events (SSE) token streaming |
| [`04_anthropic_messages.py`](../../examples/python/04_anthropic_messages.py) | **Anthropic Messages** | Native Messages format & token counting |
| [`05_metadata_cost_tracking.py`](../../examples/python/05_metadata_cost_tracking.py) | **Metadata & Cost** | Deep dive into `x-nr-*` headers |
| [`06_prompt_templates.py`](../../examples/python/06_prompt_templates.py) | **Prompt Templates** | Server-side prompt templates & variables |
| [`07_tool_calling.py`](../../examples/python/07_tool_calling.py) | **Tool Calling** | Function calling with JSON schema tools |
| [`08_structured_outputs.py`](../../examples/python/08_structured_outputs.py) | **Structured Outputs** | Strict JSON object output formatting |
| [`09_error_handling.py`](../../examples/python/09_error_handling.py) | **Error Handling** | Typed error handling & guardrail recovery |
| [`10_conversation_memory.py`](../../examples/python/10_conversation_memory.py) | **Memory** | Multi-turn memory without header leaks |
| [`11_embeddings.py`](../../examples/python/11_embeddings.py) | **Embeddings** | Vector embeddings generation |
| [`12_multimodal_vision.py`](../../examples/python/12_multimodal_vision.py) | **Multimodal Vision** | Image inputs via URL or base64 |

### 📓 Interactive Jupyter Notebook
Try the SDK interactively with [`notebooks/quickstart.ipynb`](../../notebooks/quickstart.ipynb).

---

### 1. Streaming Responses

```python
from nroutersdk import nRouter

with nRouter() as client:
    stream = client.chat.completions.create(
        model="anthropic/claude-sonnet-4-5-20250929",
        messages=[{"role": "user", "content": "Write a short poem about routers."}],
        stream=True,
    )

    for chunk in stream:
        if chunk.choices:
            content = chunk.choices[0].delta.content
            if content:
                print(content, end="", flush=True)
    print()
```

### 2. Anthropic Messages API

Use Anthropic's Messages format directly on the exact same `sk-nrouter-` API key:

```python
from nroutersdk import nRouter

with nRouter() as client:
    # Pre-call token counting (Free route)
    count = client.messages.count_tokens(
        model="anthropic/claude-sonnet-4-5-20250929",
        messages=[{"role": "user", "content": "Hello!"}],
    )
    print(f"Token count: {count['input_tokens']}")

    # Create message
    message = client.messages.create(
        model="anthropic/claude-sonnet-4-5-20250929",
        messages=[{"role": "user", "content": "Hello via Anthropic Messages!"}],
        max_tokens=256,
    )
    print(message["content"][0]["text"])
```

### 3. Function & Tool Calling

Define function schemas and let the model decide when to invoke external tools:

```python
import json
from nroutersdk import nRouter

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_stock_price",
            "description": "Get the current stock price for a symbol",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Stock ticker symbol, e.g. AAPL"},
                },
                "required": ["symbol"],
            },
        },
    }
]

with nRouter() as client:
    response = client.chat.completions.create(
        model="anthropic/claude-sonnet-4-5-20250929",
        messages=[{"role": "user", "content": "What is the stock price of AAPL?"}],
        tools=tools,
        tool_choice="auto",
    )

    msg = response.choices[0].message
    if msg.tool_calls:
        for tool_call in msg.tool_calls:
            print(f"Tool called: {tool_call.function.name} with args: {tool_call.function.arguments}")
```

### 4. Structured JSON Outputs

Enforce typed JSON object generation using `response_format`:

```python
import json
from nroutersdk import nRouter

with nRouter() as client:
    response = client.chat.completions.create(
        model="anthropic/claude-sonnet-4-5-20250929",
        messages=[
            {"role": "system", "content": "Extract data into JSON with keys: name, title, company."},
            {"role": "user", "content": "Sarah Connor is the Lead Security Engineer at Cyberdyne."}
        ],
        response_format={"type": "json_object"},
    )

    data = json.loads(response.choices[0].message.content)
    print(data)  # {'name': 'Sarah Connor', 'title': 'Lead Security Engineer', 'company': 'Cyberdyne'}
```

### 5. Response Metadata & Cost Tracking

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
print("Limit Source:      ", meta.limit_source)       # "key", "team", "org", or None
```

> **Note on Cost Accuracy:** Unpriced models return `cost=None` and `cost_status="unpriced"`. Never treat `None` as `$0.00` — free routes (like `/v1/messages/count_tokens`) emit no cost header, while billable inferences always track usage.

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

with nRouter() as client:
    try:
        response = client.chat.completions.create(
            model="claude-sonnet-4-5-20250929",
            messages=[{"role": "user", "content": "Analyze confidential data..."}],
        )
    except nRouterGuardrailBlockedError as e:
        print(f"Blocked by guardrail: {e}")
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

## Enterprise Configuration & Proxies

### Custom Proxy, SSL Certificates & Timeouts

Pass custom `httpx2.Client` or timeout configurations for corporate networks:

```python
import httpx2 as httpx
from nroutersdk import nRouter

# Configure proxy, custom SSL context, and timeouts
http_client = httpx.Client(
    proxy="http://proxy.corporate.internal:8080",
    verify="/path/to/corporate-ca.crt",
    timeout=httpx.Timeout(60.0, connect=10.0),
)

with nRouter(http_client=http_client, max_retries=3) as client:
    response = client.chat.completions.create(
        model="anthropic/claude-sonnet-4-5-20250929",
        messages=[{"role": "user", "content": "Hello behind enterprise proxy!"}],
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
| `/v1/videos` | `client.videos.create()` | Video generation jobs |

---

## Documentation & Resources

* [nRouter Documentation](https://nrouter.ai/docs)
* [API Reference](https://nrouter.ai/docs/api-reference)
* [Python Quickstart Guide](https://nrouter.ai/docs/sdks/python)
* [Live Model Catalog](https://nrouter.ai/models)
* [Dashboard & API Keys](https://nrouter.ai/dashboard/keys)
