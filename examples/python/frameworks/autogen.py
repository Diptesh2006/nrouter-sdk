# nRouter — AutoGen (Microsoft) Integration
# Multi-agent conversations with guardrails on every message.
#
# pip install autogen-agentchat nroutersdk

import os
from nroutersdk import nRouter

NROUTER_BASE = "https://api.nrouter.ai"
NROUTER_KEY = os.environ["NROUTER_API_KEY"]

# nRouter SDK for guardrails, credits, prompts.
# AutoGen uses config_list for LLM calls pointed at nRouter.
client = nRouter()  # reads NROUTER_API_KEY from env
MODEL = "gpt-5.4-mini"

# ━━━ 1. SEE WHAT THIS KEY CAN REACH ━━━━━━━━━━━━━━━━━━━━━━━

# Scoped to your key: exactly the models you may call.
print("Models:", [m.id for m in client.models.list().data])

# Guardrails, prompt templates and budgets are configured in the dashboard and
# applied server-side to every request. There is deliberately no client call to
# list or override them — a request cannot opt out of its own org's policy.

# ━━━ 2. MULTI-MODEL CONFIG (use different models per agent) ━

config_list = [
    {
        "model": "gpt-5.4-mini",
        "api_key": NROUTER_KEY,
        "base_url": f"{NROUTER_BASE}/v1",
    },
    {
        "model": "gpt-5.4-mini",
        "api_key": NROUTER_KEY,
        "base_url": f"{NROUTER_BASE}/v1",
    },
]

from autogen import AssistantAgent, UserProxyAgent

# ━━━ 3. AGENTS WITH GUARDRAIL PROTECTION ━━━━━━━━━━━━━━━━━━

assistant = AssistantAgent(
    name="assistant",
    llm_config={"config_list": config_list},
    system_message="You are a helpful coding assistant.",
)

user_proxy = UserProxyAgent(
    name="user",
    human_input_mode="NEVER",
    max_consecutive_auto_reply=3,
)

# Every message between agents is checked by guardrails.
# Cache, guardrails, and rate limits auto-apply from org config.
# PII in agent conversations → blocked.
# Prompt injection in agent prompts → blocked.

# Guardrails are assigned per key, team or org in the dashboard and apply
# automatically — the narrowest assignment wins. There is no per-request
# override to send in the body.

# Per-request overrides:
# AutoGen does not support extra body fields natively — use the nRouter SDK
# for per-request control:
#   response = client.nrouter.chat(
#       messages=[{"role": "user", "content": "..."}],
#       prompt_template_id="your-summarizer-id",
#       prompt_variables={"language": "Spanish"},
#   )
# Or use cURL with these fields in the JSON body:
#   "nrouter_prompt_template_id": "your-summarizer-id"
#   "nrouter_prompt_variables": {"language": "Spanish", "max_length": "100"}
#   "nrouter_cache": false   // disable cache for this request

user_proxy.initiate_chat(
    assistant,
    message="Write a Python function that validates email addresses.",
)

# ━━━ 4. WHAT THAT COST ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Cost is reported per request on the response itself, not polled from a
# balance endpoint. Call through the nRouter client to read it.
client.chat.completions.create(
    model=MODEL,
    messages=[{"role": "user", "content": "One-line summary of the run."}],
    max_tokens=256,
)

meta = client.last_response
print(f"\nrequest  {meta.request_id}")
print(f"tokens   {meta.input_tokens} in / {meta.output_tokens} out")

# `cost` is None when the model is unpriced — nRouter never reports a
# confident $0. Always branch on `cost_status`.
if meta.cost_status == "exact":
    print(f"cost     ${meta.cost:.6f}")
else:
    print(f"cost     unpriced ({meta.cost_status})")

# Balances and spend history live in the dashboard at https://app.nrouter.ai —
# they are org-scoped billing data, not inference.
