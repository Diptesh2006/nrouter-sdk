# nRouter SDKs

SDKs for the [nRouter](https://nrouter.ai) LLM gateway — one API key for models across six
provider clouds. One key, one bill,
the live multi-provider catalog, built-in guardrails, and prompt management. The exact current
models are published at [nrouter.ai/api/public/models](https://nrouter.ai/api/public/models).

As of 2026-08-29, the runnable examples use Anthropic Claude models because
those are the models currently live through the gateway. Check
`client.models.list()` with your key before choosing another model.

## SDKs

| Language | Package | Install | Status |
|----------|---------|---------|--------|
| **Python** | `nrouter-sdk` | `pip install nrouter-sdk` | **Published** on PyPI — imports as `nroutersdk` |
| **cURL** | none needed | built in | **Ready** — see `examples/curl.sh` |
| **JavaScript / TypeScript** | `@nrouter_ai/sdk` | — | `npm install @nrouter_ai/sdk` — PUBLISHED; source in `sdks/js/` |
| **Java** | — | — | Source in `sdks/java/`; not on Maven Central |
| **Rust** | — | — | Source in `sdks/rust/`; not on crates.io |
| **R** | — | — | Source in `sdks/r/`; not on CRAN |

Python is the only language published to a package registry today. The others are
usable from source in this repository, and ship to their registries as they are ready.

**Until a branded SDK ships for your language, use the stock OpenAI SDK** pointed at
`https://api.nrouter.ai/v1` — that is the supported path and it is what every file under
`examples/` demonstrates.

## Architecture

Every SDK is a thin wrapper around the language's OpenAI SDK. The magic happens server-side.

```
spec/nrouter-sdk-spec.json          ← Single source of truth
    ↓
sdks/
└── python/                       ← pip install nrouter-sdk  (the only PUBLISHED one)

(planned, not built: node/ go/ java/ ruby/ php/ — see the status table above)
```

## What Every SDK Does (Same Features, Every Language)

1. **Pre-configured** — `base_url` and `api_key` (from `NROUTER_API_KEY`) set automatically
2. **Auto-captures metadata** — `last_response` populated from the gateway's canonical `x-nr-*` cost, model, token, request, and limit headers
3. **Typed errors** — `nRouterGuardrailBlockedError`, `nRouterCreditError`, `nRouterRateLimitError`, `nRouterAuthenticationError`, `nRouterNotFoundError`, `nRouterRequestError`, `nRouterServiceError` (not a generic 400/401/402/404/429/503)
4. **Blocks unsupported endpoints** — `files`, `fine_tuning`, batches, and other unmounted resources give clear errors, not confusing 404s
5. **Anthropic wire on the same key** — `messages.create()` and `messages.count_tokens()`
6. **Prompt template override** — `nrouter_prompt_template_id` + `nrouter_prompt_variables` per request

## Keeping SDKs in Sync

All SDKs are driven by `spec/nrouter-sdk-spec.json`:

```json
{
  "version": "2.0.0",
  "response_headers": { "x-nr-request-cost": { "type": "float" }, ... },
  "errors": { "guardrail_blocked": { "http": 400, "class": "nRouterGuardrailBlockedError" }, ... },
  "unsupported_endpoints": { "files": "...", "fine_tuning": "...", ... }
}
```

**When the backend changes:**
1. Update `spec/nrouter-sdk-spec.json`
2. Re-publish the Python SDK

(There is no CI that "regenerates + publishes all SDKs" — only the Python package exists, and
its release is manual. Do not describe an automated multi-language pipeline that isn't wired.)

## Quick Start

Only the Python snippet below is runnable today. The rest show the intended shape of branded
SDKs that have **not** been built — do not paste them into a customer doc.

### Python
```python
from nroutersdk import nRouter
client = nRouter()
response = client.chat.completions.create(model="anthropic/claude-sonnet-4-5-20250929", messages=[{"role": "user", "content": "Hello!"}])
print(f"Cost: ${client.last_response.cost}")
print(client.last_response.response_cache)      # "hit", "miss", or None
print(client.last_response.response_cache_age)  # seconds on hits, otherwise None
```

### Anthropic Messages
```python
message = client.messages.create(
    model="anthropic/claude-sonnet-4-5-20250929",
    messages=[{"role": "user", "content": "Hello!"}],
    max_tokens=256,
)
print(message["content"][0]["text"])
print(f"Cost: ${client.last_response.cost}")
```

Buffered Messages calls are supported in both `nRouter` and `AsyncnRouter`. `stream=True` refuses
explicitly until the branded SDK has a tested SSE parser; use the official Anthropic-compatible
HTTP endpoint directly if you need streaming today.

The Python client also exposes every mounted OpenAI-compatible namespace: chat completions,
legacy completions, Responses, embeddings, image generation, speech, transcription, translation,
model list/retrieve, and the video create/retrieve/download collection. `messages.count_tokens()`
is available in both sync and async clients. Binary audio/video responses remain bytes; multipart
audio uploads remain multipart; large JSON message bodies are not truncated by the wrapper.

### Node.js
```typescript
import { nRouter } from "@nrouter_ai/sdk";
const client = new nRouter();
const res = await client.chat.completions.create({ model: "anthropic/claude-sonnet-4-5-20250929", messages: [{ role: "user", content: "Hello!" }] });
```

### Go
```go
client := nrouter.New()
resp, _ := client.Chat.Completions.New(ctx, openai.ChatCompletionNewParams{...})
fmt.Println(client.LastResponse.Cost)
```

### Ruby
```ruby
client = nRouter::Client.new
response = client.chat(parameters: { model: "anthropic/claude-sonnet-4-5-20250929", messages: [{ role: "user", content: "Hello!" }] })
```

### PHP
```php
$client = new \nRouter\nRouter();
$response = $client->chat()->create([...]);
```

### Java
```java
nRouter nrouter = new nRouter();
ChatCompletion resp = nrouter.openai().chat().completions().create(...);
```

### cURL
```bash
curl https://api.nrouter.ai/v1/chat/completions \
  -H "Authorization: Bearer $NROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"anthropic/claude-sonnet-4-5-20250929","messages":[{"role":"user","content":"Hello!"}]}'
```

---

## How We Keep SDKs Updated

### Industry Standard (What OpenAI, Stripe, Anthropic Do)

| Company | Approach | Tool |
|---------|----------|------|
| **OpenAI** | OpenAPI spec → generated SDKs | [Stainless](https://stainless.com) |
| **Anthropic** | OpenAPI spec → generated SDKs | [Stainless](https://stainless.com) |
| **Stripe** | OpenAPI spec → generated SDKs | Custom generator |
| **AWS** | Smithy model → generated SDKs | [Smithy](https://smithy.io) |
| **Google Cloud** | Protobuf → generated SDKs | [gapic-generator](https://github.com/googleapis/gapic-generator) |
| **Twilio** | OpenAPI spec → generated SDKs | Custom generator |

**The pattern is universal:** one spec file → code generation → publish.

### Our Approach

```
┌─────────────────────────────────────────┐
│  spec/nrouter-sdk-spec.json                │   ← YOU EDIT THIS
│  (headers, errors, APIs, version)       │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│  scripts/generate-sdks.py               │   ← READS SPEC
│  (validates + generates SDK code)       │
│                                         │
│  For each language:                     │
│    1. Read spec                         │
│    2. Generate response meta class      │
│    3. Generate error classes            │
│    4. Generate unsupported blockers     │
│    5. Generate nRouter API helpers         │
│    6. Write to sdks/{lang}/             │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│  CI Pipeline (GitHub Actions)           │
│                                         │
│  On spec change:                        │
│    1. Regenerate all SDKs               │
│    2. Run tests per language            │
│    3. Version bump (from spec.version)  │
│    4. Publish:                          │
│       PyPI, npm, Maven, RubyGems,      │
│       Packagist, Go module tag          │
└─────────────────────────────────────────┘
```

### What Triggers an Update

| Backend Change | Spec Update | SDK Impact |
|----------------|-------------|------------|
| New response header | Add to `response_headers` | All SDKs parse new header |
| New error code | Add to `errors` | All SDKs get new error class |
| New nRouter API endpoint | Add to `nrouter_apis` | All SDKs get new method |
| New unsupported block | Add to `unsupported_endpoints` | All SDKs block it |
| Version bump | Change `version` | All packages publish same version |
| OpenAI adds new method | Nothing — inherited automatically | SDKs get it for free |

### What DOESN'T Need an Update

| Change | Why No SDK Update |
|--------|-------------------|
| New model added | Just use `model="new-model-name"` — no SDK change |
| Guardrail config change | Dashboard config, not SDK |
| Prompt template change | Dashboard config, not SDK |
| Pricing change | Server-side; per-request cost arrives on `x-nr-request-cost` |
| Rate limit change | Server-side enforcement |
| New provider key | Server-side routing |

This is the key advantage of the thin-wrapper approach: **90% of product changes need zero SDK updates.**
