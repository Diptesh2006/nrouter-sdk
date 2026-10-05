# nRouter Pure-Curl Health Checks

This directory contains modular, grouped pure-curl health checks for nRouter (`https://api.nrouter.ai/v1`).

By testing using raw `curl` requests rather than language-specific SDKs, these health checks continuously verify the true wire contract, edge WAF, response headers, and upstream provider connectivity with zero SDK bias.

## Grouped Health Checks

| Check Group | Script | Focus / Description |
|---|---|---|
| **Consolidated Suite** | [`run_all.sh`](run_all.sh) / [`run_all.py`](run_all.py) | Executes all health check groups sequentially, aggregates results, and generates a unified status report. |
| **Shared plumbing** | [`_curl_common.py`](_curl_common.py) | Not a check group — the ONE curl invocation, response parser and credential rule every module imports. Carries its own `--self-test`. |
| **Models & Providers** | [`model_curl.sh`](model_curl.sh) / [`model_curl.py`](model_curl.py) | Verifies the `GET /v1/models` catalog's SHAPE (at least one entry, every `id` a non-empty string; the count is reported, not judged), provider discovery & distribution, and a live inference probe on the route under test. |
| **Guardrails** | [`guardrail_curl.sh`](guardrail_curl.sh) / [`guardrail_curl.py`](guardrail_curl.py) | Verifies platform moderation floor, PII redaction, prompt injection & secret leakage detection, evasion resistance, and wire contract assertions. |
| **Endpoints & Features** | [`feature_curl.sh`](feature_curl.sh) / [`feature_curl.py`](feature_curl.py) | 40 probes across the request surface. The inference-path ones ask the ROUTE UNDER TEST in that wire's shape; the rest are pinned to their own path and carry the fixed-route scope guard. |
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

Every check reports one of four results, and the last two are the important ones:

| Result | Meaning |
|---|---|
| `PASS` | The assertion held: status **and** headers **and** body. |
| `FAIL` | The assertion did not hold. The `detail` field says which clause failed. |
| `NOT-CONFIGURED` | The precondition for this check does not exist on this plane — no second tenant key, no MCP server, no exhausted-budget key, no routing headers, a key not scoped to this route, a parameter this wire does not carry. **It is never reported as `PASS`.** A run with any `NOT-CONFIGURED` check is PARTIAL and is not release evidence for that property. |
| `NOT-EVALUATED` | The wire response could not be evaluated (e.g. a rate-limit store outage where a 429 response lacks both `Retry-After` and `x-nr-limit-source`). **Counts as NOT PROVEN (never a pass)**, making the suite PARTIAL and listed by name under its own heading in consolidated reports. |

⚠️ **NOT-CONFIGURED is for what the script can SEE.** A precondition is absent
only when the response proves it (a 403 naming `key_route_not_allowed`, a route
that does not exist, a fixture variable nobody set). Where the script cannot see
the plane's configuration, the check stays `FAIL` and the detail states both
readings — see the guardrail case below. Downgrading on a guess is how a real
defect becomes a yellow row nobody reads.

### A moderation prompt that was SERVED stays FAIL

`guardrail_curl` sends prompts the platform floor is supposed to refuse. When one
comes back `200 x-nr-guardrails: pass`, that is real evidence and it stays a
failure — but the detail says which floor let it through, because the two mean
different things and this script cannot tell which plane it is on:

| Category | Detail says | Read it as |
|---|---|---|
| toxicity, harassment, violence, self-harm, harmful-intent, injection, evasion | *"the model-scored moderation floor did not block; on a plane where content scoring is not required this is expected, on stage/prod it is a defect"* | Check whether content scoring is required on this plane. |
| explicit, secret | *"the deterministic … scanner did not block … NOT conditional on content scoring … a defect on every plane"* | A defect, wherever you ran it. |

### A 429 lacking Retry-After and x-nr-limit-source stays NOT-EVALUATED

When the rate-limit store is unreachable, the gateway fails closed by design with a 429 that carries neither `Retry-After` nor `x-nr-limit-source`. Because the gateway's documented fail-closed "unevaluatable" shape carries neither header by design, the wire alone cannot distinguish an infrastructure store outage from a measured 429 that forgot its contract headers.

These checks remain `NOT-EVALUATED` — they count as **NOT PROVEN** (never a pass), leave the suite `PARTIAL`, and are listed by name under their own heading in `run_all.py` consolidated summaries. The operator's gateway log is the arbiter: check for:
```
rate-limit store unreachable — REFUSING
```

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
| `NROUTER_MCP_URL` | the MCP endpoint, when it is not `<API origin>/mcp` (see below) |
| `NROUTER_HEALTH_MIN_MODELS` | a **minimum catalog size** you expect on this plane; unset means the count is reported and not judged (see below) |
| `NROUTER_CONTROL_PLANE_KEY` | the real management-credential refusal check |
| `NROUTER_DEPLETED_API_KEY` | the 402 limit-source check |
| `NROUTER_UNPRICED_MODEL` | the "unpriced is never $0" check |
| `NROUTER_HEALTH_FALLBACK_MODEL` | a **healthy secondary this key can route to**, for the two fallback happy-path checks (see below) |
| `NROUTER_HEALTH_SECOND_FALLBACK_MODEL` | an optional third target, so the ordered walk has two ranks to walk |
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

This holds for **all thirteen** modules including `model_curl`, `guardrail_curl`
and `feature_curl`, which used to print their banner above the document and made
`--json > report.json` unparseable. Each one's self-test now drives its real
`main()` and parses what it wrote to stdout, so a banner that creeps back onto
stdout fails the self-test rather than the next consumer.

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

**All thirteen modules honour the pair**, including `model_curl` and
`feature_curl`. Their historical model flags — `model_curl --probe-model`,
`feature_curl --chat-model`, `fallbacks_curl --primary-model` — are DEPRECATED
aliases for `--model`, kept working because a script somewhere uses them; an
explicit `--model` wins over any of them.

`feature_curl` splits its 40 probes into two kinds, and the difference is
load-bearing:

* **Route-under-test** (`chat_`, `fallback_`, `ratelimit_`, `cache_`,
  `context_limit_`, `guardrail_`, `routing_`, `metering_`,
  `waf_malformed_json`) ask the route under test, in that wire's body shape. A
  probe whose PARAMETER does not exist on that wire — `response_format` or
  `logprobs` on the Anthropic-shaped wire — reports NOT-CONFIGURED naming the
  wire, instead of earning a 400 about its own request.
* **Fixed-route** (`messages_`, `tokens_`, `embed_`, `completions_`, `models_`,
  the two `waf_` refusals) are pinned by their own nature and carry the
  fixed-route scope guard below.

`mcp_curl` is the one module the pair does not steer: `/mcp` is its own fixed
path, so it accepts the flags for symmetry and ignores them. **It does NOT live
under `/v1`.** The MCP surface is at the API **origin** (`/mcp`, and
`/mcp/{server_id}` for the path-addressed form), while `NROUTER_BASE_URL` names
the inference base and ends in `/v1` — so the module strips one trailing `/v1`
and appends `/mcp`. Set `NROUTER_MCP_URL` (or `--mcp-url`) to name the endpoint
outright. A 404 from `<origin>/v1/mcp` would be the module asking the wrong URL
and says nothing about the plane; a 404 from the real `/mcp` with a configured
server header means the plane names no such server, and reports NOT-CONFIGURED.

### The catalog size is a plane fact, not a contract

`model_curl` asserts the SHAPE of `GET /v1/models` — at least one entry, every
`id` a non-empty string — and **reports** the count rather than judging it. A
virtual key scoped to two models legitimately lists two; a built-in floor of ten
reported a correct gateway as broken. Set `NROUTER_HEALTH_MIN_MODELS=<n>` to
assert a floor you actually expect on the plane you are pointing at.

**If the key may not use the route**, the gateway answers `403` with
`x-nr-auth-reason: key_route_not_allowed`. That is a provably absent
precondition, so the module reports **NOT-CONFIGURED**, names the header value
and the variable to set, and stops — rather than reporting every remaining check
as a gateway failure that never happened. A `403` for any *other* reason, and a
`401`, are still real failures.

**A check pinned to a DIFFERENT fixed route** — `metering_curl`'s two embeddings
checks, `mcp_curl`'s `/mcp` probes, `contract_curl`'s `/openapi.json` — behaves
the same way but does **not** stop the module: a key scoped away from one route
says nothing about the route under test, so that single check reports
NOT-CONFIGURED naming the route and every other check still runs.

## Choosing the fallback targets

Same reasoning, one level down. `fallbacks_curl` needs a **secondary this key
can actually route to**, and the built-in default is only a guess. A key scoped
to two models refuses the guess with `400 fallback_not_allowed` — which is the
gateway being **right**, not a defect:

| Variable | Flag | Applies to |
|---|---|---|
| `NROUTER_HEALTH_FALLBACK_MODEL` | `--fallback-model` | `direct_serve_with_fallback_list`, `request_list_is_walked_in_order` |
| `NROUTER_HEALTH_SECOND_FALLBACK_MODEL` | `--second-fallback-model` | `request_list_is_walked_in_order` (the ordered walk) |

```bash
NROUTER_HEALTH_ROUTE=/messages \
NROUTER_HEALTH_MODEL=claude-haiku-4-5-20251001 \
NROUTER_HEALTH_FALLBACK_MODEL=<a second model this key allows> \
  python3 scripts/curl_health_checks/fallbacks_curl.py
```

While the variable is **unset**, a `400 fallback_not_allowed` on those two checks
is reported NOT-CONFIGURED and names the variable. Three narrowings keep that
from becoming a hiding place, and each is mutation-checked:

* a `400` carrying any **other** code is a real FAIL;
* any other **status** is a real FAIL;
* a target you **named yourself** and the gateway refused is a real FAIL — you
  asserted the key can route it and the gateway disagreed.

The refused-target check (`unpermitted_target_is_400`) is unaffected: it uses a
deliberately unroutable name, so its `400` is about the policy and never about
which models your particular key happens to hold.

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

