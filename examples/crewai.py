# nRouter — CrewAI Integration
# Multi-agent workflows with guardrails on every agent call.
#
# pip install crewai nroutersdk

import os
from nroutersdk import nRouter

os.environ["OPENAI_API_KEY"] = os.environ["NROUTER_API_KEY"]
os.environ["OPENAI_API_BASE"] = "https://api.nrouter.ai/v1"

from crewai import Agent, Task, Crew

# nRouter SDK for guardrails, credits, prompts.
# CrewAI uses env vars (OPENAI_API_KEY/OPENAI_API_BASE) for LLM calls.
client = nRouter()  # reads NROUTER_API_KEY from env
MODEL = "anthropic/claude-sonnet-4-5-20250929"

# ━━━ 1. SEE WHAT THIS KEY CAN REACH ━━━━━━━━━━━━━━━━━━━━━━━

# Scoped to your key: exactly the models you may call.
print("Models:", [m.id for m in client.models.list().data])

# Guardrails, prompt templates and budgets are configured in the dashboard and
# applied server-side to every request. There is deliberately no client call to
# list or override them — a request cannot opt out of its own org's policy.

# ━━━ 2. MULTI-MODEL AGENTS (each can use a different model) ━

# Researcher uses Claude (best for analysis)
researcher = Agent(
    role="Researcher",
    goal="Find accurate information about a topic",
    backstory="You are an expert researcher with attention to detail.",
    llm="anthropic/claude-sonnet-4-5-20250929",
    verbose=True,
)

# Writer uses GPT-4o (best for creative writing)
writer = Agent(
    role="Writer",
    goal="Write clear, engaging content",
    backstory="You are a skilled technical writer.",
    llm="anthropic/claude-sonnet-4-5-20250929",
    verbose=True,
)

# Every agent call goes through nRouter:
#   Agent prompt → nRouter → Cache + Guardrails + Prompt template → Model → Response
# Cache, guardrails, and rate limits auto-apply from org config.
# If any agent tries to leak PII or gets a prompt injection, guardrails block it.

# Guardrails are assigned per key, team or org in the dashboard and apply
# automatically — the narrowest assignment wins. There is no per-request
# override to send in the body.

# Per-request overrides:
# CrewAI does not support extra body fields natively — use the nRouter SDK
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

# ━━━ 3. RUN THE CREW ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

research_task = Task(
    description="Research the latest trends in AI safety and guardrails.",
    expected_output="A summary of key trends.",
    agent=researcher,
)

write_task = Task(
    description="Write a 300-word blog post based on the research.",
    expected_output="A blog post.",
    agent=writer,
)

crew = Crew(agents=[researcher, writer], tasks=[research_task, write_task], verbose=True)
result = crew.kickoff()
print(f"\nResult: {result}")

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
