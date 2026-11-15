---
name: nrouter-sdk
description: >-
  Use when developing, testing or auditing the official nRouter multi-language SDKs: generated model
  constants, request/response types, conformance suites, wire serialization, error classification,
  retries, the @nrouter_ai/support-agent library. Not for registry publishing (use deploy-nrouter-sdk).
metadata:
  version: 1.3.0
---

# nRouter SDKs (router)

## When to use / not for

- **What:** Client SDK development across 10 languages, generated model constants from spec/model-catalog-snapshot.json (scripts/generate-model-constants.mjs, MCAT-39), conformance testing, wire serialization, error classification, and retry semantics.
- **When:** Adding SDK features, regenerating or checking SDK model constants, updating request/response types, running conformance test suites, or testing the @nrouter_ai/support-agent library.
- **Not for:** Publishing packages to external package registries (use deploy-nrouter-sdk) or gateway wire implementation (use nrouter-rust-modalities).

Ten SDKs, one gateway contract. Shared facts here; open the sub-skill for the change.

| Sub-skill | When to open |
|---|---|
| sub-skill `parity` | Any wire, endpoint, header, error code, body option, example, README or version change — propagation, sync matrix, README standard, coordinated version. |
| sub-skill `hardening` | Error classification (incl. undocumented 502/504), streaming, cancellation, secret redaction, retries, timeouts. |
| sub-skill `testing` | Per-language runners, offline suites, the `NROUTER_LIVE` billed probe, curl harness, in-process fakes, required coverage, registry contents. |
| sub-skill `support-agent` | `@nrouter_ai/support-agent` (repo `nRouterGateway/customer-support-agent`): `support-agent build-kb`, zero-DB retrieval, SSE. |

A new wire is `parity` (all SDKs) + `testing` (a contract test per SDK); a classification change is `hardening` + `testing` (a behavioural test per status).

## Shared facts

### SDKs and the spec

- SDKs live under `sdks/<tech>/` (`js python java go rust kotlin android swift dart r`); derive: `ls -d sdks/*/ | wc -l`.
- `spec/nrouter-sdk-spec.json` (derived from the gateway) is the sole source of truth for base URL, `NROUTER_API_KEY`, `sk-nrouter-` prefix, headers and value enums, error codes, body fields, version. **Read values from it; never retype.** SDK ≠ spec → the SDK is wrong; a contract change is never single-language.
- **Generated Model Constants (`MCAT-39`, `CATREC-010`):** `spec/model-catalog-snapshot.json` (pinned `schema_version` + `catalog_revision` snapshot exported from `mo_models_final`) is the sole input to `scripts/generate-model-constants.mjs`, which emits deterministic `MODEL_*` constants across all 10 SDKs (preserving `canonical` and `moving` identifiers and marking retired models `@deprecated` / `Deprecated`, never deleted). Verify with `node scripts/generate-model-constants.mjs --check` and `node --test scripts/generate-model-constants.test.mjs`.
- **Branching & release workflow (Rule #20):** Active SDK changes and coordinated version bumps are authored and verified on `development` (`origin/development`), merged into locked-down `main` **only via Pull Request (`development` → `main`)**, and published/tagged from `main`.

```bash
python3 - <<'PY'
import json; s = json.load(open('spec/nrouter-sdk-spec.json'))
for k in ('response_headers', 'errors', 'extra_body_fields'):
    print(k, len(s[k]), sorted(s[k]))
print('version', s['version'])
PY
```

### The request body is a wire surface

`spec.extra_body_fields` is the **closed** set of lifted `nrouter_*` keys; the rest is forwarded verbatim; an **unknown `nrouter_*` key is 400**. The three most mis-modelled:

| Field | Shape | Refusal |
|---|---|---|
| `nrouter_fallbacks` | 1–4 model ids in order; **REPLACES** (never merges) the org fallback policy; `model` stays primary, unlisted. Text wires. | unroutable target (incl. alias/auto/allowance names) → `400 fallback_not_allowed`, before egress |
| `nrouter_guardrails` | 1–8 ids/names; **ADD-ONLY** — never removes, relaxes or replaces an assigned guardrail or the moderation floor. Text wires. | not owned by the org → `400 guardrail_not_found` |
| `nrouter_cache` | Boolean; `false` forces egress for buffered text (streams never cached). | none; `x-nr-response-cache: bypass` |

Typed option builders exist in only some SDKs; never claim all. Derive:

```bash
python3 -c "import sys;sys.path.insert(0,'conformance');import check_conformance as c;\
print('typed:',sorted(c.OPTION_BUILDERS));print('none:',sorted(c.NO_OPTION_BUILDER))"
```

`check_option_builders` fails a builder that omits a spec field, a `NO_OPTION_BUILDER` entry that grew a builder, and a builder naming an invented `nrouter_*` key.

### Reading a response

Each is a `spec.response_headers` entry — read it, don't retype it.

- **`x-nr-routing`** (`direct` | `fallback:<n>`, 0-based, primary = 0) and **`x-nr-attempts`** (provider calls incl. retries/failovers) are emitted; **both ABSENT on a cache hit and on every refusal** (pinned by `tracing_curl`).
- **`x-nr-guardrails`** (case-sensitive; `value_semantics` in the spec): `redacted` = the prompt was REWRITTEN before sending; `partial` = some content went uninspected (normal on audio uploads), not that anything was acted on. Absence ≠ `none`. No policy name, id or count, ever.
- **`x-nr-response-cache`**: `hit` | `miss` | `bypass`.
- **`x-nr-limit-source`** is present on 402 as well as 429; `budget` is a value.
- A model outside the key's access list is **403 `x-nr-auth-reason: key_model_not_allowed`**, not 404; `model_not_found` = alias absent or invisible to the key.
- **Bring-your-own-key responses & errors:**
  - `x-nr-funding-source` can be `byok`; on `byok`, `x-nr-cost-status: byok` and `x-nr-request-cost` is absent.
  - `x-nr-byok-fallback` is present when a saved key attempt fails non-billably and credit fallback answers on credits (`x-nr-funding-source: credits`).
  - Error codes: `byok_plan_required` (402), `byok_credential_rejected` (401), `byok_credential_unavailable` (409; no usable customer key and credit fallback not enabled), and `byok_fair_use_exceeded` (429, with `x-nr-limit-source: byok_fair_use`).
  - Sole source of truth: `spec/nrouter-sdk-spec.json`.

### Conformance gate — the only cross-SDK check

```bash
python3 conformance/check_conformance.py --self-test   # prove it bites, FIRST
python3 conformance/check_conformance.py
```

Python 3 only — it greps SDK source text, so a missing toolchain never reads as a skipped pass. Enforces base URL, env name, key prefix, every header and error code, the route-ownership matrix (native helper or declared delegation seam per route × SDK), the coordinated version across manifests and JS/Rust lockfiles, the option-builder pin, and sub-gates `doc_wires`, `source_defaults`, `doc_header_count`, `client_timeouts`.

**Green is necessary, never sufficient:** it cannot bind a code to its status, prove a header lands in the right field, see statuses outside the spec (502/504 — sub-skill `hardening`), or see the gateway. Behaviour needs a test in the SDK's own suite (sub-skill `testing`).

### Curl proof harness — what the wire actually answers

`nrouter-sdk/scripts/curl_health_checks/` (its `README.md` is authoritative) is the only contract proof in this repo.

```bash
python3 nrouter-sdk/scripts/curl_health_checks/run_all.py --self-test            # offline, proves checks bite
export NROUTER_API_KEY="sk-nrouter-..."
python3 nrouter-sdk/scripts/curl_health_checks/run_all.py --route /messages --model <a model this key may use>
python3 nrouter-sdk/scripts/curl_health_checks/run_all.py --quick                # sampled
python3 nrouter-sdk/scripts/curl_health_checks/run_all.py --json > report.json   # stdout is one document
```

- Modules (`ls nrouter-sdk/scripts/curl_health_checks/*_curl.py`) run standalone; `fallbacks_curl`, `guardrails_request_curl`, `cache_curl` pin the body options; `contract_curl` diffs the live wire against the spec.
- **Only `PASS` passes**; `NOT-CONFIGURED` / `NOT-EVALUATED` make the run PARTIAL, never release evidence.
- Key only from `NROUTER_API_KEY` (or `--api-key`, which leaks to history); no credentials-file fallback.
- Pass a `--route` (and `--fallback-model`) the key may use, or you test key policy, not the gateway.

### Zero client retries on billed calls

Every SDK pins automatic client retries to zero on billed calls: the gateway reserves once and owns retry/failover, so a client retry is a second bill. SDKs wrapping a vendor client override its non-zero default — re-assert the pin with a test on any swap or upgrade.

### `@nrouter_ai/support-agent`

Separate repo; pins an exact `@nrouter_ai/sdk` version, so a breaking JS SDK change breaks it. Detail: sub-skill `support-agent`.
