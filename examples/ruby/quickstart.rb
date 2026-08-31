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

# Guardrails, prompt templates, rate limits and budgets are configured in the
# dashboard and enforced server-side on every request. There is deliberately no
# endpoint to list or override them: a request cannot opt out of its org policy.
# Balances and spend history live at https://app.nrouter.ai — org billing data,
# not inference. Per-request cost arrives on the x-nr-request-cost header.
# ━━━ 1. Chat (org defaults auto-apply) ━━━━━━━━━━━━━━━━━━━━━━
# Cache, guardrails, and rate limits auto-apply from org config.

client = OpenAI::Client.new(
  access_token: NROUTER_KEY,
  uri_base: "#{NROUTER_BASE}/v1",
)

response = client.chat(
  parameters: {
    model: "anthropic/claude-sonnet-4-5-20250929",
    messages: [{ role: "user", content: "Hello!" }],
  }
)
puts response.dig("choices", 0, "message", "content")

# ━━━ 2. With prompt template ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

response = client.chat(
  parameters: {
    model: "anthropic/claude-sonnet-4-5-20250929",
    messages: [{ role: "user", content: "Summarize Q1 earnings..." }],
    nrouter_prompt_template_id: "your-summarizer-id",
    nrouter_prompt_variables: { language: "Spanish", max_length: "100" },
  }
)

# Guardrails are assigned per key, team or org in the dashboard and apply
# automatically — the narrowest assignment wins. There is no per-request
# override to pass here.

# Disable cache for a single request
# Cache is enabled by default. Pass nrouter_cache: false for a fresh response.
response = client.chat(
  parameters: {
    model: "anthropic/claude-sonnet-4-5-20250929",
    messages: [{ role: "user", content: "What is the latest news?" }],
    nrouter_cache: false,
  }
)

# ━━━ 3. PII blocked by guardrail ━━━━━━━━━━━━━━━━━━━━━━━━━━━

begin
  client.chat(
    parameters: {
      model: "anthropic/claude-sonnet-4-5-20250929",
      messages: [{ role: "user", content: "My SSN is 123-45-6789" }],
    }
  )
rescue => e
  puts "Guardrail blocked: #{e.message}"
end

