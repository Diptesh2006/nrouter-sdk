# nRouter — Python
#
#   pip install nrouter-sdk
#
# One key, one base URL, models across six provider clouds. Every line below was
# executed against a live gateway on 2026-08-25 before being committed.
#
# `nrouter-sdk` subclasses the OpenAI SDK, so everything you already know works.
# What it adds: typed nRouter errors, and per-request cost on `last_response`.

import os

from nroutersdk import (
    nRouter,
    nRouterAuthenticationError,
    nRouterCreditError,
    nRouterGuardrailBlockedError,
    nRouterNotFoundError,
    nRouterRateLimitError,
)

if not os.environ.get("NROUTER_API_KEY"):
    raise SystemExit("Set NROUTER_API_KEY. Get a key at https://nrouter.ai/keys")

# Reads NROUTER_API_KEY and defaults to https://api.nrouter.ai/v1.
client = nRouter()

MODEL = "gpt-5.4-mini"

# ━━━ 1. WHAT THIS KEY CAN REACH ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Scoped to your key — you see exactly the models you may call.
print("Models:", [m.id for m in client.models.list().data][:5], "...")

# Guardrails, prompt templates, rate limits and budgets are configured in the
# dashboard and enforced server-side on every request. There is no client call
# to list or override them, by design: a request cannot opt out of its org's
# own policy.

# ━━━ 2. A BASIC CALL ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
response = client.chat.completions.create(
    model=MODEL,
    messages=[{"role": "user", "content": "Hello!"}],
    max_tokens=512,
)
print(response.choices[0].message.content)

# ━━━ 3. WHAT IT COST ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Populated after every call from the x-nr-* response headers.
meta = client.last_response
print(f"request {meta.request_id} | model {meta.model} | "
      f"{meta.input_tokens} in / {meta.output_tokens} out")

# `cost` is None when the model is unpriced. nRouter never reports a confident
# $0 — branch on `cost_status`, never on `cost` being falsy.
if meta.cost_status == "exact":
    print(f"cost ${meta.cost:.6f}")
else:
    print(f"cost unpriced ({meta.cost_status})")

# ━━━ 4. STREAMING ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# The FINAL chunk carries usage and an EMPTY `choices` list. Indexing
# `choices[0]` unguarded raises IndexError at the very end of an otherwise
# successful stream — guard it.
stream = client.chat.completions.create(
    model=MODEL,
    messages=[{"role": "user", "content": "Write a haiku about routing."}],
    max_tokens=512,
    stream=True,
)
for chunk in stream:
    if chunk.choices:
        print(chunk.choices[0].delta.content or "", end="", flush=True)
print()

# ━━━ 5. THE ANTHROPIC WIRE, SAME KEY ━━━━━━━━━━━━━━━━━━━━━━━
# `/v1/messages` speaks Anthropic's format. Use it with an Anthropic model.
message = client.messages.create(
    model="anthropic/claude-sonnet-4-5-20250929",
    messages=[{"role": "user", "content": "Hello!"}],
    max_tokens=512,
)
print(message["content"][0]["text"])

# Count input tokens without generating anything.
print(client.messages.count_tokens(
    model="anthropic/claude-sonnet-4-5-20250929",
    messages=[{"role": "user", "content": "Hello!"}],
))

# ━━━ 6. THE RESPONSES API ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print(client.responses.create(model=MODEL, input="Hello!").output_text)

# ━━━ 7. HANDLING FAILURE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Typed errors, so you branch on a class rather than string-matching a message.
try:
    client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": "My SSN is 123-45-6789"}],
        max_tokens=512,
    )
except nRouterGuardrailBlockedError as e:
    print(f"blocked by a guardrail: {e} (request {e.request_id})")
except nRouterCreditError as e:
    # The reserve happens BEFORE the provider call, so nothing was spent.
    print(f"top up at https://app.nrouter.ai/billing: {e}")
except nRouterRateLimitError as e:
    # `limit_source` names WHICH ceiling refused: key, plan, team, user or
    # budget. It is None when the gateway could not attribute the refusal —
    # it does not guess, and neither should you.
    print(f"rate limited by {e.limit_source}; retry after {e.retry_after}s")
except nRouterNotFoundError as e:
    print(f"no such model, or not visible to this key: {e}")
except nRouterAuthenticationError as e:
    # `auth_reason` is the stable refusal reason from x-nr-auth-reason —
    # e.g. key_route_not_allowed, meaning the key's endpoint scope does not
    # cover this path. The key itself may be perfectly valid.
    print(f"key refused ({e.auth_reason}): {e}")

# ━━━ 8. ASYNC ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# from nroutersdk import AsyncnRouter
# client = AsyncnRouter()
# response = await client.chat.completions.create(...)
