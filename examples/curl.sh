#!/usr/bin/env bash
# nRouter — cURL Examples
# Guardrails + prompt templates + cost tracking. No SDK needed.
#
# export NROUTER_API_KEY="sk-nr-..."

BASE="https://api.nrouter.ai"

# Guardrails, prompt templates, rate limits and budgets are configured in the
# dashboard and enforced server-side on every request. There is deliberately no
# endpoint to list or override them: a request cannot opt out of its org policy.
# Balances and spend history live at https://app.nrouter.ai — org billing data,
# not inference. Per-request cost arrives on the x-nr-request-cost header.
# ━━━ 1. CHAT (org defaults auto-apply) ━━━━━━━━━━━━━━━━━━━━━━
# Cache, guardrails, and rate limits auto-apply from org config.

curl "$BASE/v1/chat/completions" \
  -H "Authorization: Bearer $NROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "anthropic/claude-sonnet-4-5-20250929", "messages": [{"role": "user", "content": "Hello!"}]}'

# ━━━ 2. SEE COST + USAGE IN RESPONSE HEADERS ━━━━━━━━━━━━━━━

curl -i "$BASE/v1/chat/completions" \
  -H "Authorization: Bearer $NROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "anthropic/claude-sonnet-4-5-20250929", "messages": [{"role": "user", "content": "Hi"}]}'
# Response headers:
#   x-nr-request-id: nrouter-a1b2c3d4e5f67890
#   x-nr-request-cost: 0.000015
#   x-nr-cost-status: exact
#   x-nr-model: anthropic/claude-sonnet-4-5-20250929
#   x-nr-input-tokens: 8
#   x-nr-output-tokens: 4
#   x-nr-total-tokens: 12

# ━━━ 3. WITH PROMPT TEMPLATE + VARIABLES ━━━━━━━━━━━━━━━━━━━━
# Prompt templates are opt-in: pass the template ID + Jinja2 variables.
# The template's system prompt is injected server-side before the LLM call.

curl "$BASE/v1/chat/completions" \
  -H "Authorization: Bearer $NROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "anthropic/claude-sonnet-4-5-20250929",
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
    "model": "anthropic/claude-sonnet-4-5-20250929",
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
    "model": "anthropic/claude-sonnet-4-5-20250929",
    "messages": [{"role": "user", "content": "What is the latest news?"}],
    "nrouter_cache": false
  }'

# ━━━ 4. PII BLOCKED BY GUARDRAIL ━━━━━━━━━━━━━━━━━━━━━━━━━━

curl "$BASE/v1/chat/completions" \
  -H "Authorization: Bearer $NROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "anthropic/claude-sonnet-4-5-20250929", "messages": [{"role": "user", "content": "My SSN is 123-45-6789"}]}'
# Returns 400: {"error": "Request blocked by guardrail: PII detected", "code": "guardrail_blocked"}

# ━━━ 5. STREAMING ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

curl -N "$BASE/v1/chat/completions" \
  -H "Authorization: Bearer $NROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "anthropic/claude-sonnet-4-5-20250929", "messages": [{"role": "user", "content": "Count to 10"}], "stream": true}'

# ━━━ 6. AUDIO (TTS) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

curl "$BASE/v1/audio/speech" \
  -H "Authorization: Bearer $NROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "tts-1", "voice": "alloy", "input": "Welcome to nRouter!"}' \
  --output welcome.mp3

# ━━━ 7. EMBEDDINGS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# NOTE: embeddings and image generation are MOUNTED endpoints, but the model
# must be enabled for your org before it will answer. Measured on 2026-08-25 the
# served catalogue carried no embedding and no image model, so the names in the
# next two sections are illustrative. Check what YOUR key can reach first:
#     curl -s "$BASE/v1/models" -H "Authorization: Bearer $NROUTER_API_KEY"

curl "$BASE/v1/embeddings" \
  -H "Authorization: Bearer $NROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "text-embedding-3-small", "input": "The quick brown fox"}'

# ━━━ 8. IMAGE GENERATION ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

curl "$BASE/v1/images/generations" \
  -H "Authorization: Bearer $NROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "dall-e-3", "prompt": "A cat astronaut on Mars", "size": "1024x1024"}'

# ━━━ 9. MODERATIONS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

curl "$BASE/v1/moderations" \
  -H "Authorization: Bearer $NROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": "I want to harm someone"}'

# ━━━ 10. LIST MODELS + PRICING ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

curl -s "$BASE/v1/models" -H "Authorization: Bearer $NROUTER_API_KEY"
# ━━━ 11. TOOL CALLING ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

curl "$BASE/v1/chat/completions" \
  -H "Authorization: Bearer $NROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "anthropic/claude-sonnet-4-5-20250929",
    "messages": [{"role": "user", "content": "What is the weather in Tokyo?"}],
    "tools": [{"type": "function", "function": {"name": "get_weather", "description": "Get weather", "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}}]
  }'
