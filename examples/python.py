# nRouter — Python
# OpenAI SDK + guardrails + prompt templates + cache + cost tracking.
#
# pip install openai

import os
import httpx
from openai import OpenAI

NROUTER_BASE = "https://api.nrouter.ai"
NROUTER_KEY = os.environ.get("NROUTER_API_KEY")
if not NROUTER_KEY:
    raise SystemExit("Set NROUTER_API_KEY environment variable. Get your key at https://nrouter.ai/keys")
headers = {"Authorization": f"Bearer {NROUTER_KEY}"}

client = OpenAI(api_key=NROUTER_KEY, base_url=f"{NROUTER_BASE}/v1")

# ━━━ 1. DISCOVER ORG CONFIG ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
guardrails = httpx.get(f"{NROUTER_BASE}/nrouter/guardrail/list", headers=headers).json()
print("Guardrails:", [g["guardrail_name"] for g in guardrails.get("data", [])])

prompts = httpx.get(f"{NROUTER_BASE}/nrouter/prompt/list", headers=headers).json()
print("Prompts:", [p["name"] for p in prompts.get("data", [])])

balance = httpx.get(f"{NROUTER_BASE}/api/credits/balance", headers=headers).json()
print(f"Credits: ${balance['available']}")

# ━━━ 2. BASIC CALL (org defaults auto-apply) ━━━━━━━━━━━━━━━
# Guardrails, cache, and rate limits are all enforced server-side.
# No extra code needed — just call the API normally.
response = client.chat.completions.create(
    model="claude-sonnet-4-20250514",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)

# ━━━ 3. WITH PROMPT TEMPLATE + VARIABLES ━━━━━━━━━━━━━━━━━━━
# Prompt templates are opt-in: pass the template ID + Jinja2 variables.
# The template's system prompt is injected server-side before the LLM call.
with_prompt = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Q1 revenue was $4.2M..."}],
    extra_body={
        "nrouter_prompt_template_id": "your-summarizer-id",
        "nrouter_prompt_variables": {"language": "Spanish", "max_length": "100"},
    },
)

# ━━━ 4. OVERRIDE GUARDRAILS (run only specific ones) ━━━━━━━
# By default, ALL org-enabled guardrails apply automatically.
# Pass nrouter_guardrail_ids to run only a subset on this request.
with_guardrails = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Summarize Q1 earnings..."}],
    extra_body={"nrouter_guardrail_ids": ["guardrail-uuid-1", "guardrail-uuid-2"]},
)

# ━━━ 5. DISABLE CACHE (per-request opt-out) ━━━━━━━━━━━━━━━━
# Cache is enabled by default. Pass nrouter_cache: false for fresh responses.
no_cache = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "What's the latest news?"}],
    extra_body={"nrouter_cache": False},
)

# ━━━ 6. READ COST + METADATA FROM RESPONSE ━━━━━━━━━━━━━━━━━
raw = client.chat.completions.with_raw_response.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hi"}],
)
cost = raw.headers.get("x-nr-request-cost")
cost_status = raw.headers.get("x-nr-cost-status")
print(f"Cost: ${cost}" if cost is not None else f"Cost status: {cost_status}")
print(f"Model: {raw.headers.get('x-nr-model')}")
print(f"Total tokens: {raw.headers.get('x-nr-total-tokens')}")

# ━━━ 7. HANDLE ERRORS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from openai import BadRequestError
try:
    client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "My SSN is 123-45-6789"}],
    )
except BadRequestError as e:
    if e.status_code == 400: print(f"Guardrail blocked: {e.message}")
    if e.status_code == 402: print(f"Insufficient credits: {e.message}")
    if e.status_code == 429: print(f"Rate limited: {e.message}")

# ━━━ 8. STREAMING + EMBEDDINGS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
stream = client.chat.completions.create(
    model="gpt-4o", messages=[{"role": "user", "content": "Write a haiku"}], stream=True
)
for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="", flush=True)

embed = client.embeddings.create(model="text-embedding-3-small", input="Hello world")

# ━━━ 9. CHECK SPEND ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
new_balance = httpx.get(f"{NROUTER_BASE}/api/credits/balance", headers=headers).json()
print(f"\nSpent: ${balance['available'] - new_balance['available']:.4f}")
