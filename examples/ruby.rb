# nRouter — Ruby
# ruby-openai gem + guardrails + prompt templates + cost tracking.
#
# gem install ruby-openai

require "openai"
require "net/http"
require "json"

NROUTER_BASE = "https://api.nrouter.ai"
NROUTER_KEY = ENV["NROUTER_API_KEY"]

# Helper to call nRouter APIs
def nrouter_get(path)
  uri = URI("#{NROUTER_BASE}#{path}")
  req = Net::HTTP::Get.new(uri)
  req["Authorization"] = "Bearer #{NROUTER_KEY}"
  res = Net::HTTP.start(uri.hostname, uri.port, use_ssl: true) { |http| http.request(req) }
  JSON.parse(res.body)
end

# ━━━ 1. See guardrails + prompts + balance ━━━━━━━━━━━━━━━━━

guardrails = nrouter_get("/nrouter/guardrail/list")
puts "Guardrails: #{guardrails['data']&.select { |g| g['enabled'] }&.map { |g| g['guardrail_name'] }}"

prompts = nrouter_get("/nrouter/prompt/list")
puts "Prompts: #{prompts['data']&.map { |p| p['name'] }}"

balance = nrouter_get("/api/credits/balance")
puts "Credits: $#{balance['available']}"

# ━━━ 2. Chat (org defaults auto-apply) ━━━━━━━━━━━━━━━━━━━━━━
# Cache, guardrails, and rate limits auto-apply from org config.

client = OpenAI::Client.new(
  access_token: NROUTER_KEY,
  uri_base: "#{NROUTER_BASE}/v1",
)

response = client.chat(
  parameters: {
    model: "claude-sonnet-4-20250514",
    messages: [{ role: "user", content: "Hello!" }],
  }
)
puts response.dig("choices", 0, "message", "content")

# ━━━ 3. With prompt template ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

response = client.chat(
  parameters: {
    model: "gpt-4o",
    messages: [{ role: "user", content: "Summarize Q1 earnings..." }],
    nrouter_prompt_template_id: "your-summarizer-id",
    nrouter_prompt_variables: { language: "Spanish", max_length: "100" },
  }
)

# Per-request guardrail selection
# By default, ALL org-enabled guardrails apply automatically.
# Pass nrouter_guardrail_ids to run only specific guardrails on this request.
response = client.chat(
  parameters: {
    model: "gpt-4o",
    messages: [{ role: "user", content: "Summarize Q1 earnings..." }],
    nrouter_guardrail_ids: ["guardrail-uuid-1", "guardrail-uuid-2"],
  }
)

# Disable cache for a single request
# Cache is enabled by default. Pass nrouter_cache: false for a fresh response.
response = client.chat(
  parameters: {
    model: "gpt-4o",
    messages: [{ role: "user", content: "What is the latest news?" }],
    nrouter_cache: false,
  }
)

# ━━━ 4. PII blocked by guardrail ━━━━━━━━━━━━━━━━━━━━━━━━━━━

begin
  client.chat(
    parameters: {
      model: "gpt-4o",
      messages: [{ role: "user", content: "My SSN is 123-45-6789" }],
    }
  )
rescue => e
  puts "Guardrail blocked: #{e.message}"
end

# ━━━ 5. Check spend ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

new_balance = nrouter_get("/api/credits/balance")
spent = balance["available"].to_f - new_balance["available"].to_f
puts "Spent: $#{spent.round(4)}"
