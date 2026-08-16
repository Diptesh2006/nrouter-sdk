# nRouter SDKs

OpenAI-compatible SDKs for the [nRouter](https://nrouter.ai) LLM gateway. One key, one bill, 240+ models, built-in guardrails and prompt management.

## SDKs

> ⚠️ **Status corrected 2026-08-02.** This table used to mark six branded SDKs "Ready" with
> copy-pasteable install commands. Only **Python** exists on disk (`sdks/` contains exactly one
> directory) and only Python is published. Every other install line 404s. Verified against the
> registries on 2026-08-02: `pypi.org/pypi/nroutersdk` → 200 (v0.1.0, uploaded 2026-03-31);
> `registry.npmjs.org/@nrouter/sdk` → 404. Do not restore a "Ready" status without a
> registry check.

| Language | Package | Install | Status |
|----------|---------|---------|--------|
| **Python** | `nroutersdk` | `pip install nroutersdk` | **Published** — v0.1.0 on PyPI |
| **cURL** | None needed | Built-in | **Available** — see `examples/curl.sh` |
| **Node.js** | `@nrouter/sdk` *(reserved name)* | — | **NOT BUILT** — no `sdks/node/`, not on npm |
| **Go** | `github.com/nrouter/nrouter-go` | — | **NOT BUILT** — no repo, no `sdks/go/` |
| **Java** | `com.nrouter:sdk` | — | **NOT BUILT** — not on Maven Central |
| **Ruby** | `nrouter` | — | **NOT BUILT** — no `sdks/ruby/` |
| **PHP** | `nrouter/sdk` | — | **NOT BUILT** — no `sdks/php/` |

**Until a branded SDK ships for your language, use the stock OpenAI SDK** pointed at
`https://api.nrouter.ai/v1` — that is the supported path and it is what every file under
`examples/` demonstrates.

## Architecture

Every SDK is a thin wrapper around the language's OpenAI SDK. The magic happens server-side.

```
spec/nrouter-sdk-spec.json          ← Single source of truth
    ↓
sdks/
└── python/                       ← pip install nroutersdk   (the ONLY one that exists)

(planned, not built: node/ go/ java/ ruby/ php/ — see the status table above)
```

## What Every SDK Does (Same Features, Every Language)

1. **Pre-configured** — `base_url` and `api_key` (from `NROUTER_API_KEY`) set automatically
2. **Auto-captures metadata** — `lastResponse` populated with cost, guardrails, prompt version from `x-nrouter-*` headers
3. **Typed errors** — `GuardrailBlockedError`, `CreditError`, `RateLimitError` (not generic 400/402/429)
4. **Blocks unsupported endpoints** — `audio`, `files`, `fine_tuning`, etc. give clear errors, not confusing 404s
5. **nRouter APIs** — `credits.balance()`, `guardrails.list()`, `prompts.list()`, `nrouterModels.pricing()`
6. **Prompt template override** — `nrouter_prompt_template_id` + `nrouter_prompt_variables` per request

## Keeping SDKs in Sync

All SDKs are driven by `spec/nrouter-sdk-spec.json`:

```json
{
  "version": "0.1.0",
  "response_headers": { "x-nrouter-request-cost": { "type": "float" }, ... },
  "errors": { "guardrail_blocked": { "http": 400, "class": "GuardrailBlockedError" }, ... },
  "unsupported_endpoints": { "audio": "...", "files": "...", ... },
  "nrouter_apis": { "credits": { "balance": "/api/credits/balance" }, ... }
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
response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": "Hello!"}])
print(f"Cost: ${client.last_response.cost}")
```

### Node.js
```typescript
import { nRouter } from "@nrouter/sdk";
const client = new nRouter();
const res = await client.chat.completions.create({ model: "gpt-4o", messages: [{ role: "user", content: "Hello!" }] });
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
response = client.chat(parameters: { model: "gpt-4o", messages: [{ role: "user", content: "Hello!" }] })
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
  -d '{"model":"gpt-4o","messages":[{"role":"user","content":"Hello!"}]}'
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
| Pricing change | Server-side, returned via `nrouterModels.pricing()` |
| Rate limit change | Server-side enforcement |
| New provider key | Server-side routing |

This is the key advantage of the thin-wrapper approach: **90% of product changes need zero SDK updates.**
