---
name: nrouter-sdk
description: Use when changing or adding any SDK wire, endpoint, header, error code, per-request body option, demo, example, validation playbook, README or version and running the conformance gate, when changing error classification, streaming abort/cancellation, secret redaction, retry policy or timeouts, when running the pure-curl proof harness against a live gateway, when developing or testing the public @nrouter_ai/support-agent library, or when adding, running or auditing tests in any of the ten nRouter SDKs (runner commands, offline default, NROUTER_LIVE probe, fake transports).
metadata:
  version: 1.2.0
---

# nRouter SDKs (router)

Ten SDKs, one gateway contract, plus the public zero-DB customer support agent (`@nrouter_ai/support-agent`). This router holds the facts every SDK change shares; open the
sub-skill for the kind of change you are making.

## Sub-skills

| Sub-skill | When to open |
|---|---|
| sub-skill `parity` | Any wire, endpoint, header, error code, request-body option, demo, example, validation playbook, README or version change — the cross-SDK propagation protocol, the synchronization matrix, the README standard, the coordinated version. |
| sub-skill `hardening` | Error classification (and the undocumented 502/504 arms), streaming and abort/cancellation, secret redaction, client retry policy, timeouts. |
| sub-skill `testing` | Adding, changing, running or auditing tests — per-language runner commands, the offline-by-default suite, the `NROUTER_LIVE` billed probe, the pure-curl proof harness, in-process fakes per ecosystem, what a change must be covered by, what each registry publishes. |
| sub-skill `support-agent` | Developing, configuring, or testing the public `@nrouter_ai/support-agent` package (`agents/customer-support-agent/`), building knowledge base indices with `support-agent build-kb`, or verifying in-process zero-DB retrieval and SSE streaming. |

Most changes touch more than one: a new wire is `parity` (all ten SDKs) plus `testing` (a contract
test per SDK); a classification change is `hardening` plus `testing` (a behavioural test per status).

## Shared facts

### The ten SDKs

`js python java go rust kotlin android swift dart r`, each under `sdks/<tech>/`. Derive the list
rather than trusting this sentence: `ls -d sdks/*/ | wc -l`.

### The spec is canonical

`spec/nrouter-sdk-spec.json` is the sole source of truth, derived from the gateway: base URL,
`NROUTER_API_KEY`, the `sk-nrouter-` key prefix, every `x-nr-*` header and its value enum, the
documented error codes, the request-body fields the gateway lifts, and the coordinated release
version. **Read a value from the spec; never retype one here.** Every count below grows — derive it:

```bash
python3 - <<'PY'
import json; s = json.load(open('spec/nrouter-sdk-spec.json'))
for k in ('response_headers', 'errors', 'extra_body_fields'):
    print(k, len(s[k]), sorted(s[k]))
print('version', s['version'])
PY
```

When an SDK and the spec disagree, the SDK is wrong. A contract change is never single-language.

### Three wire surfaces, not two — the request BODY is one of them

`spec.extra_body_fields` is the **closed** set of `nrouter_*` keys the gateway lifts off a request
body. Everything else in the body is forwarded to the provider verbatim, and **an unknown `nrouter_*`
key is refused 400** rather than passed through — so a field an SDK does not model is not a gap a
caller can route around. Read each field's own `description` in the spec; the three a client must not
get wrong:

| Field | Shape | Refusal |
|---|---|---|
| `nrouter_fallbacks` | 1–4 model ids, tried in order. **REPLACES** the organization's fallback policy for this one call; never merged with it. `model` stays the primary and is never listed. Text wires only. | a target this key cannot route — including an alias, auto-router, allowance or capacity-pool name — is `400 fallback_not_allowed`, before any provider egress |
| `nrouter_guardrails` | 1–8 guardrail ids or names. **ADD-ONLY**: they run *in addition to* what is assigned to the key, team and organization, and a request can never remove, relax or replace an assigned guardrail or the platform moderation floor. Text wires only. | an id or name the organization does not own is `400 guardrail_not_found` — refused, never silently ignored |
| `nrouter_cache` | Boolean. `false` forces provider egress for a buffered text request; streams are never cached anyway. | none — the response carries `x-nr-response-cache: bypass` |

**Typed option builders exist in three of the ten SDKs today, and the gate says which** — the other
seven are recorded with a reason rather than assumed, so never claim ten of ten. Derive:

```bash
python3 -c "import sys;sys.path.insert(0,'conformance');import check_conformance as c;\
print('typed:',sorted(c.OPTION_BUILDERS));print('none:',sorted(c.NO_OPTION_BUILDER))"
```

`check_option_builders` fails an SDK whose builder omits a spec field, an entry in
`NO_OPTION_BUILDER` that has quietly grown a builder, and a builder naming an invented `nrouter_*`
key — the gateway refuses any key outside `spec.extra_body_fields` with a 400 before the provider
is called, so such a builder can only ever produce refusals.

### Reading a response: routing, guardrails, cache

Each of these is a `spec.response_headers` entry — read the entry rather than retyping its values.

- **`x-nr-routing` and `x-nr-attempts` are EMITTED, not planned.** Routing names which chain entry
  answered — `direct`, or `fallback:<n>` where `n` is the 0-based index of the answering entry with
  the primary at 0; attempts counts provider calls, retries and failovers alike. **Both are ABSENT on
  a cache hit and on every refusal**; a refusal advertising routing it never performed is a defect,
  and `tracing_curl` pins that.
- **`x-nr-guardrails` carries seven values**, each with its own `value_semantics` entry, matched
  case-sensitively. Two are routinely mis-read: `redacted` means an enforcing rule REWROTE part of
  the prompt before it was sent, so the model did not see what the caller sent; `partial` means some
  content went uninspected — never that anything was acted on, and it is the ORDINARY answer on the
  two audio upload wires. Absence is not `none`; `none` is an explicit token. The token is the whole
  payload by design: no policy name, id, detector family or rule count, ever.
- **`x-nr-response-cache` includes `bypass`** beside `hit` and `miss`.
- **`x-nr-limit-source` is present on 402 as well as 429**, and `budget` is one of its values.
- **A model outside the key's access list is 403 with `x-nr-auth-reason: key_model_not_allowed`** —
  not a 404. `model_not_found` is the alias being absent or invisible to the key.

### The conformance gate — the only cross-SDK check, and it needs nothing

```bash
python3 conformance/check_conformance.py --self-test   # prove the gate bites, FIRST
python3 conformance/check_conformance.py               # then run it
```

**Requires Python 3 and nothing else** — no toolchains, no network, no key. That is deliberate: it
greps each SDK's SOURCE TEXT for spec constants rather than importing or compiling it, because a
missing toolchain would otherwise be silently "skipped", and a skip that reads as a pass is the
failure mode the gate exists to prevent.

It enforces the base URL, the `NROUTER_API_KEY` env name, the `sk-nrouter-` key prefix, every
`x-nr-*` header and every gateway error code the spec documents; the route-ownership matrix (every route × every
SDK, each either exposing a native helper or declaring an explicit delegation seam); and the
coordinated release version across all ten distribution manifests plus the JS and Rust lockfiles.
It also drives the option-builder pin above and four sub-gates — doc wires, source defaults, doc
header counts, and client timeouts.

**Run `--self-test` before trusting a green run.** A conformance gate that passes while checking
nothing is worse than no gate.

### What the conformance gate cannot see

Reading source text is the right design, but it has consequences the gate's own
`conformance/README.md` states plainly. Do not let the gate stand in for a real test:

1. **It cannot bind an error code to its status.** It proves the full set of codes and the full set
   of statuses each appear *somewhere* in the dispatch. A code wired to the wrong status passes.
2. **It cannot prove a header is used correctly.** It proves the header name is *referenced*. A
   header parsed into the wrong field passes.
3. **By construction, any status outside the spec's documented errors is invisible to the gate.**
   502 and 504 are the live examples. That is where the worst divergence lives (sub-skill
   `hardening`, §1).
4. **It cannot see the gateway.** It reads this repository only. What the wire actually answers is
   the curl proof harness below.

**A green conformance run is necessary and never sufficient.** Behaviour needs a behavioural test in
the SDK's own suite (sub-skill `testing`).

### The curl proof harness — what the wire actually answers

`scripts/curl_health_checks/` asks the gateway in raw `curl`, with zero SDK bias, and is the only
thing in this repo that proves a contract claim rather than a source-text claim. Its own
`README.md` is authoritative; the facts that decide whether a run means anything:

```bash
python3 scripts/curl_health_checks/run_all.py --self-test            # offline, no key, proves the checks bite
export NROUTER_API_KEY="sk-nrouter-..."
python3 scripts/curl_health_checks/run_all.py --route /messages --model <a model this key may use>
python3 scripts/curl_health_checks/run_all.py --quick                # sampled
python3 scripts/curl_health_checks/run_all.py --json > report.json   # stdout is exactly one document
```

- **Per-domain modules run standalone** with the same flags and the same JSON shape — derive them
  rather than listing them: `ls scripts/curl_health_checks/*_curl.py`. `fallbacks_curl`,
  `guardrails_request_curl` and `cache_curl` are the three that pin the per-request body options
  above; `contract_curl` compares the live wire against the spec directly.
- **Four results, and only one is a pass.** `PASS` · `FAIL` · `NOT-CONFIGURED` (the precondition
  provably does not exist on this plane) · `NOT-EVALUATED` (the response could not be judged).
  **Neither of the last two is ever a pass** — a run carrying either is PARTIAL and is not release
  evidence for that property.
- **The key comes from `NROUTER_API_KEY` (or `--api-key`) and nowhere else.** There is deliberately
  no credentials-file fallback: this repository is public, so a hardcoded path would publish an
  internal convention. Prefer the environment variable — an argv key lands in the shell history and
  the process table.
- **Pass `--route`.** A virtual key is commonly scoped to a subset of routes and models, so pointing
  the suite at a route the key may not use tests the key policy, not the gateway. The same reasoning
  one level down is why `--fallback-model` exists.

### The client retries nothing on a billed path

**Every SDK pins automatic client-side retries to zero on billed calls.** The gateway reserves
credit once per request and owns retry and failover itself; a client-side retry is a second call and
a second bill, with nothing to deduplicate against.

⚠️ **The two SDKs wrapping a vendor client had to OVERRIDE a non-zero vendor default.** If you swap,
upgrade, or reconfigure a vendor client, re-assert the pin and prove it with a test — this is the
one place the default silently comes back.

### The customer support agent (`@nrouter_ai/support-agent`)

Located at `agents/customer-support-agent/`. It is a zero-database streaming agent package built
exclusively on `@nrouter_ai/sdk`. It implements in-process cosine similarity search over static JSON
indices built via `support-agent build-kb`, supports PII masking and citation formatting, and streams
SSE frames. Tested with `npm test` from `agents/customer-support-agent/` (offline-by-default).
Detail in sub-skill `support-agent`.

