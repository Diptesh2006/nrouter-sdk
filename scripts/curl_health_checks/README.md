# nRouter Pure-Curl Health Checks

This directory contains modular, grouped pure-curl health checks for nRouter (`https://api.nrouter.ai/v1`).

By testing using raw `curl` requests rather than language-specific SDKs, these health checks continuously verify the true wire contract, edge WAF, response headers, and upstream provider connectivity with zero SDK bias.

## Grouped Health Checks

| Check Group | Script | Focus / Description |
|---|---|---|
| **Consolidated Suite** | [`run_all.sh`](run_all.sh) / [`run_all.py`](run_all.py) | Executes all health check groups sequentially, aggregates results, and generates a unified status report. |
| **Shared plumbing** | [`_curl_common.py`](_curl_common.py) | Not a check group — the ONE curl invocation, response parser and credential rule every module imports. Carries its own `--self-test`. |
| **Models & Providers** | [`model_curl.sh`](model_curl.sh) / [`model_curl.py`](model_curl.py) | Verifies `GET /v1/models` catalog, provider discovery & distribution, and live provider chat completion inference. |
| **Guardrails** | [`guardrail_curl.sh`](guardrail_curl.sh) / [`guardrail_curl.py`](guardrail_curl.py) | Verifies platform moderation floor, PII redaction, prompt injection & secret leakage detection, evasion resistance, and wire contract assertions. |
| **Request Fallbacks** | [`fallbacks_curl.sh`](fallbacks_curl.sh) / [`fallbacks_curl.py`](fallbacks_curl.py) | Per-request fallback chains: the answering rank is named in the routing headers, and an unpermitted target, a self-reference, an over-long list, a non-array value, an unknown `nrouter_*` key and an auto-router chain are each refused with a code and no cost. |
| **Per-Request Guardrails** | [`guardrails_request_curl.sh`](guardrails_request_curl.sh) / [`guardrails_request_curl.py`](guardrails_request_curl.py) | Requested guardrails are ADD-ONLY: an unknown or foreign id is refused identically (no cross-tenant existence oracle), the tenant's own block rule survives any addition, and the platform floor cannot be displaced. |
| **Response Cache** | [`cache_curl.sh`](cache_curl.sh) / [`cache_curl.py`](cache_curl.py) | Miss → hit → bypass, hit billing that is strictly positive, tenant isolation across keys, and a fingerprint that changes when the body or the guardrail chain changes. |
| **Rate Limits** | [`rate_limit_curl.sh`](rate_limit_curl.sh) / [`rate_limit_curl.py`](rate_limit_curl.py) | A burst past the key ceiling answers 429 with a usable `Retry-After` and a named limit source, charges nothing, and leaks no internals; authentication is refused before throughput is measured. |
| **Context & Output Ceilings** | [`context_limit_curl.sh`](context_limit_curl.sh) / [`context_limit_curl.py`](context_limit_curl.py) | An oversize prompt and an over-ceiling `max_tokens` are refused with a code, before the provider is paid, on every wire shape. |
| **Metering** | [`metering_curl.sh`](metering_curl.sh) / [`metering_curl.py`](metering_curl.py) | Every served response states its cost and tokens; embeddings are priced on input only; every refusal states nothing; an unpriced model omits the cost header rather than reporting `0`. |
| **Request Identity & Tracing** | [`tracing_curl.sh`](tracing_curl.sh) / [`tracing_curl.py`](tracing_curl.py) | `x-nr-request-id` is present and unique on every response including refusals, is the gateway's own rather than the caller's, and refusals advertise no routing they never performed. |
| **Moderation Floor** | [`moderation_floor_curl.sh`](moderation_floor_curl.sh) / [`moderation_floor_curl.py`](moderation_floor_curl.py) | Both directions: hostile prompts are refused at $0, and an ordinary business prompt that merely contains an email address, a phone number or a card number is **served** — over-blocking is a defect too. |
| **MCP** | [`mcp_curl.sh`](mcp_curl.sh) / [`mcp_curl.py`](mcp_curl.py) | JSON-RPC `tools/list` over the customer credential, with the credential boundary proved: no key, a management-shaped key, an unknown server, a missing server header and a traversal-shaped name are all refused. |
| **Wire Contract** | [`contract_curl.sh`](contract_curl.sh) / [`contract_curl.py`](contract_curl.py) | Compares the live wire against [`spec/nrouter-sdk-spec.json`](../../spec/nrouter-sdk-spec.json): documented headers, header-value enums, refusal envelopes and error codes, plus no upstream, internal or reflected header. |

## Quickstart

### 1. Offline Self-Test (No API key needed)
```bash
# Run all health checks offline
bash scripts/curl_health_checks/run_all.sh --self-test
# or python3 scripts/curl_health_checks/run_all.py --self-test

# Individual module self-tests:
bash scripts/curl_health_checks/model_curl.sh --self-test
bash scripts/curl_health_checks/guardrail_curl.sh --self-test
bash scripts/curl_health_checks/fallbacks_curl.sh --self-test
bash scripts/curl_health_checks/guardrails_request_curl.sh --self-test
bash scripts/curl_health_checks/cache_curl.sh --self-test
bash scripts/curl_health_checks/rate_limit_curl.sh --self-test
bash scripts/curl_health_checks/context_limit_curl.sh --self-test
bash scripts/curl_health_checks/metering_curl.sh --self-test
bash scripts/curl_health_checks/tracing_curl.sh --self-test
bash scripts/curl_health_checks/moderation_floor_curl.sh --self-test
bash scripts/curl_health_checks/mcp_curl.sh --self-test
bash scripts/curl_health_checks/contract_curl.sh --self-test
```

## Reading a result

Every check reports one of three results, and the third is the important one:

| Result | Meaning |
|---|---|
| `PASS` | The assertion held: status **and** headers **and** body. |
| `FAIL` | The assertion did not hold. The `detail` field says which clause failed. |
| `NOT-CONFIGURED` | The precondition for this check does not exist on this plane — no second tenant key, no MCP server, no exhausted-budget key, no routing headers. **It is never reported as `PASS`.** A run with any `NOT-CONFIGURED` check is PARTIAL and is not release evidence for that property. |

Roughly two thirds of the checks are adversarial (`expected_failure: true`): they
send something the gateway must refuse, and they assert the shape of the refusal
— its code, the headers it must carry and, above all, the money headers it must
**not** carry. A refusal that quietly charges the caller is the defect these
modules exist to catch.

Some checks need a plane fixture before they can do anything. Supply what you
have; anything missing degrades to `NOT-CONFIGURED` rather than silently
passing:

| Environment variable | Unlocks |
|---|---|
| `NROUTER_API_KEY_B` | cache tenant isolation (a key in a *different* organization) |
| `NROUTER_GUARDRAIL_ID` | requested-guardrail checks and the cache fingerprint check |
| `NROUTER_GUARDRAIL_BLOCK_KEYWORD` | the keyword an added guardrail blocks |
| `NROUTER_TENANT_BLOCK_KEYWORD` | the keyword the tenant's own rule blocks |
| `NROUTER_FOREIGN_GUARDRAIL_ID` | the cross-tenant existence-oracle check |
| `NROUTER_MCP_SERVER` | the MCP happy path |
| `NROUTER_CONTROL_PLANE_KEY` | the real management-credential refusal check |
| `NROUTER_DEPLETED_API_KEY` | the 402 limit-source check |
| `NROUTER_UNPRICED_MODEL` | the "unpriced is never $0" check |
| `NROUTER_FAILING_PRIMARY_MODEL`, `NROUTER_HEALTHY_FALLBACK_MODEL`, `NROUTER_FAILING_FALLBACK_MODEL` | forced-failover and exhausted-chain checks |
| `NROUTER_GUARDRAILS_DISABLED_API_KEY` | proof that the platform floor is not tenant-disableable |

### 2. Live Health Check
```bash
export NROUTER_API_KEY="sk-nrouter-..."

# Run all health checks live (quick or full)
bash scripts/curl_health_checks/run_all.sh --quick
bash scripts/curl_health_checks/run_all.sh

# Individual checks:
bash scripts/curl_health_checks/model_curl.sh
bash scripts/curl_health_checks/guardrail_curl.sh --quick
bash scripts/curl_health_checks/guardrail_curl.sh
```

### 3. CI / GitHub Actions Step Summary
```bash
bash scripts/curl_health_checks/run_all.sh --step-summary
```

### 4. JSON Output
```bash
python3 scripts/curl_health_checks/run_all.py --json

# One feature at a time
python3 scripts/curl_health_checks/cache_curl.py --json
```

Each per-feature module emits the same JSON report, so a run is a reproducible
artifact rather than scrollback:

```json
{
  "feature": "cache",
  "base_url": "https://api.nrouter.ai/v1",
  "checks": [
    {
      "name": "miss_then_hit",
      "request": "curl -sS -D - -X POST \"$NROUTER_BASE_URL/chat/completions\" ...",
      "status": 200,
      "headers": { "x-nr-response-cache": "hit", "x-nr-request-cost": "0.000003" },
      "assertion": "both 200; first x-nr-response-cache == miss; second == hit; ...",
      "result": "PASS",
      "expected_failure": false
    }
  ]
}
```

The `request` field is a curl command you can paste into a terminal. The key is
always rendered as `$NROUTER_API_KEY` and the host as `$NROUTER_BASE_URL`, so a
report can be attached to an issue without redacting it first.

**With `--json`, stdout carries exactly one JSON document and nothing else.**
The human report still exists — it goes to stderr — so both of these work:

```bash
python3 scripts/curl_health_checks/cache_curl.py --json > report.json   # parseable
python3 scripts/curl_health_checks/cache_curl.py --json                 # both, on screen
```

## Choosing the route and the model

A virtual key is commonly **scoped** to a subset of routes and models. Pointing
the suite at a route your key may not use does not test the gateway — it tests
the key policy, once per check. So both are a runtime choice:

| Variable | Flag | Default | Values |
|---|---|---|---|
| `NROUTER_HEALTH_ROUTE` | `--route` | `/chat/completions` | `/chat/completions`, `/messages`, `/responses`, `/completions` |
| `NROUTER_HEALTH_MODEL` | `--model` | `openai/gpt-4o-mini` | any model your key may use |

```bash
# A key scoped to the Anthropic-shaped wire:
NROUTER_HEALTH_ROUTE=/messages \
NROUTER_HEALTH_MODEL=claude-haiku-4-5-20251001 \
  python3 scripts/curl_health_checks/run_all.py
```

Each wire has its own request shape and its own place for a completion, and the
checks follow both — a chat-shaped assertion would fail a perfectly good
Anthropic response:

| Route | Request carries | A completion lives at |
|---|---|---|
| `/chat/completions` | `messages` + `max_tokens` | `choices[0].message.content` |
| `/messages` | `messages` + `max_tokens` (**required**) | `content[0].text` |
| `/responses` | `input` + `max_output_tokens` | `output_text` / `output[0].content[0].text` |
| `/completions` | `prompt` + `max_tokens` | `choices[0].text` |

`mcp_curl` is the one exception: `/mcp` is its own fixed path, so it accepts the
flags for symmetry and ignores them.

**If the key may not use the route**, the gateway answers `403` with
`x-nr-auth-reason: key_route_not_allowed`. That is a provably absent
precondition, so the module reports **NOT-CONFIGURED**, names the header value
and the variable to set, and stops — rather than reporting every remaining check
as a gateway failure that never happened. A `403` for any *other* reason, and a
`401`, are still real failures.

## Credentials

The key is read from `NROUTER_API_KEY` (or `--api-key`) and **nowhere else**.
These scripts will not search your disk for a credential: this repository is
public, so a hardcoded path would publish an internal convention, and a fallback
would send whatever key it found to whatever `NROUTER_BASE_URL` you had set —
including someone else's host. A missing key is a clear usage error.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | every check passed (possibly PARTIAL — check `not_configured_checks`) |
| `1` | at least one check FAILED |
| `2` | the module could not run at all, e.g. `NROUTER_API_KEY` is unset |

`2` is deliberately distinct from `1`: a pipeline can tell "the gateway is
broken" from "you did not give me a key".

