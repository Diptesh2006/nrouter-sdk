# Changelog

Starting with 2.2.0, all ten SDKs use one coordinated version sourced from
`spec/nrouter-sdk-spec.json`. Older entries retain the independent versions
under which they were actually published; immutable registry history is never
rewritten.

Dates are the registry upload date, which is the only date a consumer can
observe. Versions are immutable once published; nothing here is ever rewritten
to correct a release, only appended to.

## [Unreleased]

## [3.1.5] - pending registry upload

- Coordinated release 3.1.5 across all ten SDKs.
- **Cost band for `nrouter/auto`**:
  - New `nrouter_cost_band` request option (`"low"`, `"mid"`, `"high"`; default `"mid"`) for cost-mode `nrouter/auto` requests (`nrouter_optimize: "cost"`). It caps each eligible model's blended list rate, `(3 * input + 1 * output) / 4` per 1M tokens: `"low"` admits models under $1, `"mid"` models under $7 (the low band included), `"high"` every band. Typed options with local validation in JavaScript (`costBand`), Python (`cost_band`), Go (`CostBand`) and Rust (`cost_band`); the other SDKs send it as a request body field, documented in each README.
  - New error code `cost_band_unsatisfiable` (HTTP 400, request error class in every SDK): the active band left zero eligible models. Refused before any charge; nRouter never escalates to a higher band. Sending `nrouter_cost_band` on a named model, with an unknown value, or under `"quality"` returns `400 invalid_request`; an `nrouter_fallbacks` entry outside the band returns `400 fallback_not_allowed`.
  - `x-nr-model` is documented as the concrete model that served the request: the named model, the fallback that answered, or the model `nrouter/auto` selected.
- **Bring your own key (BYOK)**: every SDK's error table documents `byok_plan_required` (402), `byok_fair_use_exceeded` (429), `byok_credential_rejected` (401) and `byok_credential_unavailable`. JavaScript, Python and Dart read `x-nr-byok-fallback` as typed metadata. `x-nr-funding-source: byok` pairs with `x-nr-cost-status: byok` and no `x-nr-request-cost`.
- **Model name constants**: every SDK ships generated constants for the served model catalog.
- Kotlin: `org.json` updated to `20260719` (security advisory GHSA-ghc9-756g-vrcv).
- **Paid fallback for promo- and hack-labeled models**:
  - New `x-nr-pot-fallback` response header, read as typed metadata by every SDK (`pot_fallback` / `potFallback` / `PotFallback`). Present only when a request for a `promo`- or `hack`-labeled model was charged to prepaid credits because the organization turned on paid fallback in Settings; values `pot_empty`, `pot_insufficient`, `window_hour`, `window_day`, `window_week`, `window_month`, `platform_day`, `platform_month`, `policy_excluded`, `feature`, `fallbacks_ineligible`. Absent otherwise.
  - An organization that holds promotional or hackathon credit is no longer charged prepaid credits for those models unless it turns on paid fallback; until then `insufficient_promo_credit` / `insufficient_hack_credit` (402), `pot_spend_limit_exceeded` (429) and `pot_route_feature_unsupported` (400) refuse instead, and the message names the remedy. Frozen promotional or hackathon credit answers the same 402 codes even with paid fallback on. No new error codes.

## [3.1.4] - 2026-10-30

- Coordinated release 3.1.4 across all ten SDKs.
- **Dedicated Pool Routes & Pot Refusals (`nrouter/promo`, `nrouter/hack`)**:
  - Added support for promotional and hackathon credit pool selection routes (`nrouter/promo`, `nrouter/hack`). Promotional credit is spent exclusively through `nrouter/promo` and hackathon credit through `nrouter/hack`; neither route draws from prepaid credits or plan allowances. Requests naming any other model never draw promotional or hackathon credit.
  - Added and mapped the four pot refusal error codes across all 10 SDKs:
    - `insufficient_promo_credit` (HTTP 402, `nRouterCreditError`): Available promotional credit cannot cover the request's hold. Refused before provider egress ($0 reserved, $0 spent).
    - `insufficient_hack_credit` (HTTP 402, `nRouterCreditError`): Available hackathon credit cannot cover the request's hold. Refused before provider egress ($0 reserved, $0 spent).
    - `pot_spend_limit_exceeded` (HTTP 429, `nRouterRateLimitError`): Request would take organization spend past configured UTC calendar windows (hourly, daily, weekly, monthly).
    - `pot_route_feature_unsupported` (HTTP 400, `nRouterRequestError`): Request asked for features unsupported on pot routes (web search, multiple completions `n > 1`, or tool-billed features).
  - Updated `x-nr-funding-source` response header values to include `"promo"` and `"hack"` alongside `"allowance"` and `"credits"`.
- **Optimization Strategy & Policy Access Refusals**:
  - Added `nrouter_optimize` option (`"quality"` | `"cost"`) for `nrouter/auto` requests, with strongly typed options builders and local validation in JavaScript, Python, Go, and Rust.
  - Supported per-request `nrouter_fallbacks` on `nrouter/auto`, allowing callers to supply an explicit fallback chain of up to 4 models that overrides the server-chosen pool.
  - Added and documented the three HTTP 403 policy refusal codes across all 10 SDKs (preserved on the base `nRouterError` class in JavaScript/Python and the `Other` variant in Java, Kotlin, Android, Go, Rust, Swift, Dart, and R):
    - `model_denied_by_org` (HTTP 403): Model is prohibited by organization-level policy. Deny lists take absolute precedence over allow lists and strip the model from `nrouter/auto`, `nrouter/promo`, and `nrouter/hack` candidate pools; refused before provider egress.
    - `model_denied_by_team` (HTTP 403): Model is prohibited by team-level policy.
    - `model_denied_by_key` (HTTP 403): Model is prohibited by virtual key policy.
- **Transport Reliability & Options Conformance**:
  - Unified `retry_after` on service errors (`nRouterServiceError`) across Python, Kotlin, Swift, and Dart for consistent backoff evaluation on transient gateway refusals.
  - Hardened transport retryable classification (`is_retryable()`) in Python and other SDKs to treat low-level connection and timeout errors (`ConnectionError`, `TimeoutError`, httpx `TransportError`, `APIConnectionError`, `APITimeoutError`) as retryable alongside transient HTTP statuses (408, 425, 429, 502, 503, 504), while preserving non-retryable invariants (aborted operations, configuration errors, response too large).
  - Achieved full request options conformance in the Rust SDK (`sdks/rust/src/options.rs`), adding `nrouter_fallbacks` (max 4), `nrouter_guardrails` (max 8), and `nrouter_optimize` to `FeatureOptions` and extra body generation; removed Rust's temporary builder exemption in `check_conformance.py`.
- **Documentation & Spec Parity (All 23 Error Codes)**:
  - Synchronized documentation across all 10 SDK READMEs with complete reference tables mapping all 23 gateway error codes to their canonical HTTP status codes and typed exception classes.
  - Clarified that `rate_limit_exceeded` (HTTP 429) covers RPM, TPM, RPS, and RPD limits as well as sub-monthly allowance windows (not RPM alone).
  - Clarified `plan_required` and allowance refusal semantics: pay-as-you-go organizations use credits with 0% platform fee and do not receive `plan_required`; monthly allowance exhaustion returns 402 `plan_allowance_exhausted`, while sub-monthly windows return 429 `rate_limit_exceeded` with `Retry-After`.
  - Added documentation and runnable examples for TypeSafe Jev System One decision models, deprecation headers (`x-nr-model-deprecated`, `x-nr-deprecation-notice`), and two-mode routing (Direct model access vs `nrouter/auto`).
- **Rebuilt First-Party SDK Agents & Automated Gate Coverage**:
  - Rebuilt all three first-party SDK agents (`image-prompt-generator`, `video-prompt-generator`, `social-media-content-generator`) with streamlined architectures, isolated prompt skills (`skills/brand.md`, `skills/instructions.md`), runnable examples (`examples/basic.ts`), and typed error handling (`src/errors.ts`).
  - Removed obsolete Playwright scaffolding, mock flags, and duplicate test fixtures across agent directories.
  - Added comprehensive automated contract and release gate coverage (`tests/test_agents_contract.py`) and wired agent suites into `scripts/test-all.sh`.
- **Dependency Security Updates**:
  - Upgraded `Guava` to `33.7.2` on the Android test classpath (`sdks/android/build.gradle.kts`, `gradle.lockfile`).
  - Upgraded `Tokio` to `1.53.3` in the Rust SDK (`sdks/rust/Cargo.lock`).
  - Upgraded `rustls-webpki` to `0.103.16` and `webpki-root-certs` to `1.0.10` in the Rust SDK.
  - Upgraded `rustls` to `0.23.46` in the Rust SDK addressing `RUSTSEC-2026-0346..0349`.
  - Upgraded `jackson-databind` to `2.22.3` in the Java SDK resolving published CVEs.
  - Documented unreachable `block-buffer` advisory until 2027-01-29 in `sdks/rust/osv-scanner.toml`.

## Coordinated SDK release — 3.1.3 — 2026-10-15

- Coordinated release 3.1.3 across all ten SDKs.
- Synchronized OpenAPI spec contract and response header metadata (`x-nr-funding-source`, `x-nr-allowance-reset`, `x-nr-model-deprecated`, `x-nr-deprecation-notice`).
- Added initial `nrouter/promo` and `nrouter/hack` route aliases, `nrouter_optimize` option on `nrouter/auto`, and error-code mappings across all 10 SDKs.

## Coordinated SDK release — 3.1.2 — 2026-09-10

- Coordinated release 3.1.2 across all ten SDKs.
- 50 hardening fixes across all ten SDKs:
  - Error classification parity: Unified HTTP 502 Bad Gateway and 504 Gateway Timeout handling across Python, JS, Go, Rust, Java, Kotlin, Android, Swift, Dart, and R with the canonical "response too large" carve-out (mapped to non-retryable error).
  - Retry policy hardening: Enforced that retry predicates reject cancelled/aborted operations and "too large" error conditions across SDKs.
  - Secret redaction at construction: Hardened exception and condition initializers across Swift (`NRouterErrorBody`), Dart (`errorBodyFrom`), Go (`configErr`), R, and Java to guarantee immediate `sk-nrouter-*` redaction before logging or formatting.
  - Cross-SDK parity & documentation: Updated all 10 manifests, lockfiles, READMEs, playbooks, and demos to canonical release version 3.1.2.
  - Tooling: Hardened `scripts/check_sdk_parity.py` to enforce active cross-SDK parity on all open-source assets.

## Coordinated SDK release — 3.1.1 — 2026-09-07

- Coordinated release 3.1.1 across all ten SDKs.
- JavaScript / TypeScript (`@nrouter_ai/sdk`):
  - Added Anthropic deprecated sampling parameters protection (`SAMPLING_DEPRECATED`, `samplingParamsDeprecated()`, `canonicalModel`) to strip temperature and top_p on Claude 4.7+, Claude 5+, and Opus 5 models to prevent HTTP 400 gateway rejections.
  - Added sampling parameters validation (`validateSamplingParams`) ensuring non-negative temperatures and top_p within [0, 1].
  - Added runnable end-to-end Playground Parity simulation demo (`sdks/js/demo/playground-simulation.mjs`) verifying parameters, wires, TTFT streaming metrics, dual-model comparisons, and dynamic discovery.
- Python (`nrouter-sdk`):
  - Synchronized `samplingParamsDeprecated` and `SAMPLING_DEPRECATED` list in `nroutersdk.sampling`.
  - Exported sampling utilities and updated client surface tests.

## Coordinated SDK release — 3.1.0 — 2026-09-07

- Coordinated release 3.1.0 across all ten SDKs.
- Repository migration: updated repository metadata, SCM links, and distribution references to `nRouterGateway/nrouter-sdk`.
- Go module path updated to `github.com/nRouterGateway/nrouter-sdk/sdks/go/v3`.
- JavaScript / TypeScript (`@nrouter_ai/sdk`):
  - Exported audio parameter and result types (`AudioSpeechParams`, `AudioTranscriptionParams`, etc.).
  - Parameter validation for image and video requests before execution.
  - Formatted video duration seconds as wire string expected by the gateway.
  - Added runnable mock-gateway testing and e2e demo harness.
- Java (`ai.nrouter:nrouter-sdk`): HTML entity escaping in `NRouterPrompts` javadoc.
- Python (`nrouter-sdk`): dependency hygiene, mypy/ruff cleanups, spend-row metadata contract tests.
- Conformance & CI: hardened cross-SDK conformance gate with dynamic SDK count scanning.

## Coordinated SDK release — 3.0.0 — 2026-09-04

- Coordinated major release 3.0.0 across all ten SDKs.
- 10 rounds of harness improvements (50 features across all 10 SDKs):
  - Unified Conversation Memory with sliding window pruning and token estimators across JS, Python, Go, Rust, Swift, Dart, Java, Kotlin, Android, and R.
  - Portable Prompt Templates & Variable Substitution across client transports with variable interpolation.
  - Multi-tenant Context Injection & Trace Parent Observability (`x-nr-trace-id`, `x-nr-tenant-id`, `x-nr-feature`).
  - Native Multimodal Content Block Builders (text, image_url, audio, base64 payload encoders).
  - Cross-Wire Claude Sampling Parameter Normalizers (`max_tokens`, `temperature`, `top_p`, `stop`).
  - Stream Health, Chunk Latency & SSE Diagnostics with first-chunk TTFT and anomaly tracking.
  - Strict RFC 9110 Retry-After Parser & Jittered Exponential Backoff.
  - Strict Transport Security, Private-IP Egress Guardrails, and Auth Token Redaction across all HTTP clients.
  - Conformance Gates for Memory, Templates, Headers, and Stream diagnostics across all 10 SDKs.
  - Complete Playproxy / Playground backend parity for direct drop-in integration with `@nrouter_ai/sdk`.
- Go module path migrated to `github.com/nRouterAI/nrouter-sdk/sdks/go/v3`.
- Android and Kotlin synchronized at 3.0.0.
- SwiftPM tag bumped to 3.0.0.
- All 15 release lanes tested and verified green with 0 skips and 0 failures.

## Coordinated SDK release — 2.2.1 — 2026-08-31

- Migrates the Python SDK to OpenAI 3.6's `httpx2` transport contract and pins
  the tested OpenAI/httpx2 compatibility floors.
- Eliminates all Python mypy and Ruff findings under the current clean-runner
  toolchain without suppressing either gate.
- Advances every SDK together so all registries and source tags remain on the
  same immutable release train; non-Python wire behavior is unchanged.
- Makes the Kotlin and Android workflows honest source-preview verification:
  no release credentials, staging uploads, false green publishes, or doomed
  waits for artifacts outside the supported registry set.

## Coordinated SDK release — 2.2.0 — 2026-08-31

- Aligns JavaScript, Python, Java, Kotlin, Android, Rust, Swift, Dart, R and Go
  on one release version and adds a fail-closed cross-SDK version gate to every
  publish workflow through conformance.
- Moves the Go module to the SemVer-required `/v2` import path.
- Makes Android wait for the same-version Kotlin core to be visible on Maven
  Central before its own publication can begin.
- Includes the expanded standalone examples, Python context managers and
  static typing/lint coverage already present on `main`.

## JavaScript / TypeScript — npm `@nrouter_ai/sdk`

### 2.0.0 — 2026-08-29

**BREAKING, and both breaks are deliberate.**

- **Node 22 or newer is now required**, declared in `engines`. `openai` 7 sets
  that floor and this package inherits it. Previously nothing declared a floor
  at all, so an unsupported runtime failed somewhere further in.
- **`apiKey` must be a string.** openai 7 also accepts a function that returns a
  key; this SDK refuses it, in the types as well as at runtime, because its job
  is to check the `sk-nrouter-` prefix before a request and a function cannot be
  checked until the request is already in flight.
- **SECURITY: OpenAI environment credentials can no longer reach the gateway.**
  openai 7 reads `OPENAI_CUSTOM_HEADERS`, `OPENAI_ORG_ID`, `OPENAI_PROJECT_ID`
  and `OPENAI_ADMIN_KEY` from the environment, and merges parsed custom headers
  BEFORE `defaultHeaders` — so they beat the auth header derived from
  `apiKey`. Measured: with those set, `nr.chat()` sent
  `Authorization: Bearer sk-openai-…` to api.nrouter.ai. One process using both
  clients was enough. The constructor now nulls those channels and sets the
  nRouter bearer last, so the key on the wire is the one that was validated.
  `withOptions({ apiKey })` is covered by the same path — it re-enters the
  constructor with the vendor's branded header bag, and an earlier spread-based
  fix left the OLD key on the wire, billing the wrong tenant on a call the
  caller believed re-keyed. `fetchOptions.headers` is dropped for the same
  reason — it is spread onto the request AFTER these headers and overwrote them
  wholesale; every other transport setting there is kept, and headers have a
  supported home in `defaultHeaders`.
- **`httpAgent` is gone.** openai 7 removed it in favour of `fetchOptions`. If
  you passed an agent for a proxy or custom TLS, move it there — a `dispatcher`
  under `fetchOptions` is the undici equivalent. This SDK's docs promised
  `httpAgent` applied to every call, and that promise is withdrawn rather than
  quietly left to fail.
- **`provider`, `workloadIdentity`, `dataResidency`, `credential` and
  `x509Transport` are not accepted**, in the constructor or in
  `withOptions()`. They
  are mutually exclusive with the `apiKey` and `baseURL` this constructor always
  injects, so they could never work; they are now removed from the type instead
  of failing inside the vendor.

**Why the upgrade: the dependency tree goes from 37 packages to zero.**
`openai` 4 pulled `node-fetch`, `form-data`, `agentkeepalive` and 34 others;
7 has no dependencies. Every supply-chain alert on this package's dependency
tab came from that set — `Uses eval`, `Unmaintained (>5 years)`, `Deprecated`,
`Network access` — and none of it was ever this SDK's code. Nothing else buys
that reduction.

- The byte-request path no longer passes `__binaryRequest`, which openai 7
  removed: passing typed arrays through verbatim is now the default. The test
  that pinned the old version floor is replaced by one that sends real bytes
  and reads what `fetch` was handed, so a future release that re-encodes them
  goes red instead of a version number changing.

### 1.2.1 — 2026-08-29
- First release published with **no credential at all** — npm trusted
  publishing (OIDC). The `NPM_TOKEN` secret is gone. No library code changed;
  the release exists because nothing short of a publish exercises the OIDC
  exchange.

### 1.2.0 — 2026-08-29
- `nrouter` JSON helpers (`sdks/js/src/json.ts`), contributed in #6. MINOR, not
  patch: this adds surface, and semver is the only warning a consumer gets.
- README links the gateway-side capability docs. npmjs.com renders this README,
  so a docs change reaches the package page only on a release.

### 1.1.2 — 2026-08-28
- Ships the rewritten `sdks/js/README.md`, which is the page npmjs.com renders,
  now carrying npm / Socket / licence badges.
- First release published through the split `verify` → `publish` pipeline: the
  job that holds publish credentials runs no repository dependency.
- No library code changed.

### 1.1.1 — 2026-08-28
- Ships an improved `sdks/js/README.md`. No library code changed.
- First release published by CI rather than by hand.

### 1.1.0 — 2026-08-28
- A cost that underflowed to zero was reported as a free request.
- A cancelled request could be resent, and the vendor's own abort was invisible
  to the caller.
- A stream ending without `[DONE]` is now refused rather than reported complete.
- The declared `openai` range allowed a version that corrupts every request
  body; the floor moved to `^4.50.0`.
- An `Authorization` header could reach a log through a sanitised error cause.

### 1.0.0 — 2026-08-26
- First public release.

## Python — PyPI `nrouter-sdk`

### 2.1.3 — 2026-08-29
- README now links the gateway-side capability docs (guardrails, budgets,
  routing, observability). PyPI renders this README, so the links only reach
  the package page on a release. No library behaviour changed.

### 2.1.2 — 2026-08-28
- README refresh. No library behaviour changed.

### 2.1.1 — 2026-08-27
- `__version__` brought back into step with the packaged version.

### 2.1.0 — 2026-08-25
### 2.0.2 · 2.0.1 — 2026-08-22
### 2.0.0 — 2026-08-22
- First release under the `nrouter-sdk` distribution name. The import package
  remains `nroutersdk`; because the two differ,
  `[tool.hatch.build.targets.wheel] packages = ["nroutersdk"]` is load-bearing —
  without it the wheel builds containing no package at all.

⚠️ `nemoroutersdk` 0.1.0 on PyPI (2026-03-31) predates a rebrand, is **not**
maintained, and is not this project.

## Java — Maven Central `ai.nrouter:nrouter-sdk`

### 1.0.0 — 2026-08-26
- First release. Wraps `com.openai:openai-java`; transport and error handling
  are the vendor's, so this SDK is checked for the connection contract only.

## Other SDKs

`sdks/{kotlin,android,go,rust,swift,dart,r}` build from this repository and
are not yet published to a registry. They are covered by the same conformance
gate as the published ones.
