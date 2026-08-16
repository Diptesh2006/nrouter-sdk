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

# ━━━ 1. SEE GUARDRAILS + BALANCE ━━━━━━━━━━━━━━━━━━━━━━━━━━

guardrails = client.guardrails.list()
print("Guardrails:", [g["guardrail_name"] for g in guardrails.get("data", []) if g.get("enabled")])

balance = client.credits.balance()
print(f"Credits: ${balance.get('available', 0):.2f}")

# ━━━ 2. MULTI-MODEL CONFIG (use different models per agent) ━

config_list = [
    {
        "model": "claude-sonnet-4-20250514",
        "api_key": NROUTER_KEY,
        "base_url": f"{NROUTER_BASE}/v1",
    },
    {
        "model": "gpt-4o",
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

# Per-request overrides:
# By default, ALL org-enabled guardrails apply automatically.
# AutoGen does not support extra body fields natively — use the nRouter SDK
# for per-request control:
#   response = client.nrouter.chat(
#       messages=[{"role": "user", "content": "..."}],
#       prompt_template_id="your-summarizer-id",
#       prompt_variables={"language": "Spanish"},
#   )
# Or use cURL with these fields in the JSON body:
#   "nrouter_guardrail_ids": ["uuid1","uuid2"]
#   "nrouter_prompt_template_id": "your-summarizer-id"
#   "nrouter_prompt_variables": {"language": "Spanish", "max_length": "100"}
#   "nrouter_cache": false   // disable cache for this request

user_proxy.initiate_chat(
    assistant,
    message="Write a Python function that validates email addresses.",
)

# ━━━ 4. CHECK COST ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

new_balance = client.credits.balance()
print(f"\nConversation cost: ${balance.get('available', 0) - new_balance.get('available', 0):.4f}")
