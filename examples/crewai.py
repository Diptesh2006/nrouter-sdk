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

# ━━━ 1. SEE WHAT'S PROTECTING YOUR AGENTS ━━━━━━━━━━━━━━━━━

guardrails = client.guardrails.list()
print("Guardrails protecting all agents:")
for g in guardrails.get("data", []):
    if g.get("enabled"):
        print(f"  • {g['guardrail_name']} ({g['provider']})")

balance = client.credits.balance()
print(f"Credits: ${balance.get('available', 0):.2f}")

# ━━━ 2. MULTI-MODEL AGENTS (each can use a different model) ━

# Researcher uses Claude (best for analysis)
researcher = Agent(
    role="Researcher",
    goal="Find accurate information about a topic",
    backstory="You are an expert researcher with attention to detail.",
    llm="claude-sonnet-4-20250514",
    verbose=True,
)

# Writer uses GPT-4o (best for creative writing)
writer = Agent(
    role="Writer",
    goal="Write clear, engaging content",
    backstory="You are a skilled technical writer.",
    llm="gpt-4o",
    verbose=True,
)

# Every agent call goes through nRouter:
#   Agent prompt → nRouter → Cache + Guardrails + Prompt template → Model → Response
# Cache, guardrails, and rate limits auto-apply from org config.
# If any agent tries to leak PII or gets a prompt injection, guardrails block it.

# Per-request overrides:
# By default, ALL org-enabled guardrails apply automatically.
# CrewAI does not support extra body fields natively — use the nRouter SDK
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

# ━━━ 4. CHECK COST FOR THE ENTIRE CREW RUN ━━━━━━━━━━━━━━━━

new_balance = client.credits.balance()
print(f"\nCrew cost: ${balance.get('available', 0) - new_balance.get('available', 0):.4f}")
print(f"Remaining: ${new_balance.get('available', 0):.2f}")
