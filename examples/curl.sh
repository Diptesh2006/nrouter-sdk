#!/usr/bin/env bash
# nRouter — cURL Examples
# Guardrails + prompt templates + cost tracking. No SDK needed.
#
# export NROUTER_API_KEY="sk-nr-..."

BASE="https://api.nrouter.ai"

# ━━━ 1. SEE GUARDRAILS + PROMPTS + BALANCE ━━━━━━━━━━━━━━━━━

# Active guardrails
curl -s "$BASE/nrouter/guardrail/list" \
  -H "Authorization: Bearer $NROUTER_API_KEY" | python3 -m json.tool

# Prompt templates
curl -s "$BASE/nrouter/prompt/list" \
  -H "Authorization: Bearer $NROUTER_API_KEY" | python3 -m json.tool

# Credit balance
curl -s "$BASE/api/credits/balance" \
  -H "Authorization: Bearer $NROUTER_API_KEY"
# {"balance": 96.50, "reserved": 0.05, "available": 96.45}

# ━━━ 2. CHAT (org defaults auto-apply) ━━━━━━━━━━━━━━━━━━━━━━
# Cache, guardrails, and rate limits auto-apply from org config.

curl "$BASE/v1/chat/completions" \
  -H "Authorization: Bearer $NROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-sonnet-4-20250514", "messages": [{"role": "user", "content": "Hello!"}]}'

# ━━━ 3. SEE COST + USAGE IN RESPONSE HEADERS ━━━━━━━━━━━━━━━

curl -i "$BASE/v1/chat/completions" \
  -H "Authorization: Bearer $NROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Hi"}]}'
# Response headers:
#   x-nr-request-id: nrouter-a1b2c3d4e5f67890
#   x-nr-request-cost: 0.000015
#   x-nr-cost-status: exact
#   x-nr-model: gpt-4o-mini
#   x-nr-input-tokens: 8
#   x-nr-output-tokens: 4
#   x-nr-total-tokens: 12

# ━━━ 4. WITH PROMPT TEMPLATE + VARIABLES ━━━━━━━━━━━━━━━━━━━━
# Prompt templates are opt-in: pass the template ID + Jinja2 variables.
# The template's system prompt is injected server-side before the LLM call.

curl "$BASE/v1/chat/completions" \
  -H "Authorization: Bearer $NROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Q1 revenue was $4.2M..."}],
    "nrouter_prompt_template_id": "your-summarizer-id",
    "nrouter_prompt_variables": {"language": "Spanish", "max_length": "100"}
  }'

# ━━━ 4b. WITH PER-REQUEST GUARDRAIL SELECTION ━━━━━━━━━━━━━━━

# By default, ALL org-enabled guardrails apply automatically.
# Pass nrouter_guardrail_ids to run only specific guardrails on this request.
curl "$BASE/v1/chat/completions" \
  -H "Authorization: Bearer $NROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Summarize Q1 earnings"}],
    "nrouter_guardrail_ids": ["guardrail-uuid-1", "guardrail-uuid-2"],
    "nrouter_prompt_template_id": "your-template-id"
  }'

# ━━━ 4c. DISABLE CACHE (per-request opt-out) ━━━━━━━━━━━━━━━━
# Cache is enabled by default. Pass nrouter_cache: false for a fresh response.

curl "$BASE/v1/chat/completions" \
  -H "Authorization: Bearer $NROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "What is the latest news?"}],
    "nrouter_cache": false
  }'

# ━━━ 5. PII BLOCKED BY GUARDRAIL ━━━━━━━━━━━━━━━━━━━━━━━━━━

curl "$BASE/v1/chat/completions" \
  -H "Authorization: Bearer $NROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-4o", "messages": [{"role": "user", "content": "My SSN is 123-45-6789"}]}'
# Returns 400: {"error": "Request blocked by guardrail: PII detected", "code": "guardrail_blocked"}

# ━━━ 6. STREAMING ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

curl -N "$BASE/v1/chat/completions" \
  -H "Authorization: Bearer $NROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-sonnet-4-20250514", "messages": [{"role": "user", "content": "Count to 10"}], "stream": true}'

# ━━━ 7. AUDIO (TTS) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

curl "$BASE/v1/audio/speech" \
  -H "Authorization: Bearer $NROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "tts-1", "voice": "alloy", "input": "Welcome to nRouter!"}' \
  --output welcome.mp3

# ━━━ 8. EMBEDDINGS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

curl "$BASE/v1/embeddings" \
  -H "Authorization: Bearer $NROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "text-embedding-3-small", "input": "The quick brown fox"}'

# ━━━ 9. IMAGE GENERATION ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

curl "$BASE/v1/images/generations" \
  -H "Authorization: Bearer $NROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "dall-e-3", "prompt": "A cat astronaut on Mars", "size": "1024x1024"}'

# ━━━ 10. MODERATIONS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

curl "$BASE/v1/moderations" \
  -H "Authorization: Bearer $NROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": "I want to harm someone"}'

# ━━━ 11. LIST MODELS + PRICING ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

curl -s "$BASE/v1/models" -H "Authorization: Bearer $NROUTER_API_KEY"
curl -s "$BASE/api/models/pricing" -H "Authorization: Bearer $NROUTER_API_KEY"

# ━━━ 12. GUARDRAIL LOGS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

curl -s "$BASE/nrouter/guardrail/logs?limit=5" \
  -H "Authorization: Bearer $NROUTER_API_KEY" | python3 -m json.tool

# ━━━ 13. TOOL CALLING ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

curl "$BASE/v1/chat/completions" \
  -H "Authorization: Bearer $NROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "What is the weather in Tokyo?"}],
    "tools": [{"type": "function", "function": {"name": "get_weather", "description": "Get weather", "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}}]
  }'
