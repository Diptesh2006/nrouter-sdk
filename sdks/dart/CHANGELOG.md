# Changelog

## 3.1.5

- Tracks the coordinated 3.1.5 nRouter SDK release.
- Documents `nrouter_cost_band` (`"low"`, `"mid"`, `"high"`) for cost-mode `nrouter/auto` requests and maps `cost_band_unsatisfiable` to `NRouterRequestError`.
- Reads `x-nr-pot-fallback` and `x-nr-byok-fallback` as typed response metadata; adds generated model-name constants.

## 3.1.4

- Tracks the coordinated 3.1.4 nRouter SDK release.
- Added `nrouter/promo` and `nrouter/hack` pool routes, four pot refusal error codes, and `model_denied_by_*` policy refusal documentation.
- Unified `retry_after` on service errors (`NRouterServiceError`).

## 3.1.3

- Tracks the coordinated 3.1.3 nRouter SDK release.
- Added deprecation headers and complete auth refusal reasons.
- Mapped remaining refusal error codes.

## 3.1.2

- Tracks the coordinated 3.1.2 nRouter SDK release.
- Hardened 502/504 error classification with permanent "too large" carve-out.
- Enforced secret redaction at construction in error bodies and diagnostics.

## 3.1.1

- Tracks the coordinated 3.1.1 nRouter SDK release. No Dart-specific API change;
  the shared gateway contract in `spec/nrouter-sdk-spec.json` is unchanged for
  Dart callers.
- First pub.dev publication since 2.1.1. Versions 2.2.0 through 3.1.0 were built
  and conformance-tested but not published, so this release skips them.

## 3.1.0

- Tracks the coordinated 3.1.0 release: repository metadata, SCM links and
  distribution references moved to `nRouterGateway/nrouter-sdk`.

## 3.0.0

- Advances Dart to the coordinated 3.0.0 major release train.
- Unified conversation memory with sliding window token pruning.
- Prompt template variable substitution and multi-tenant trace header injection.
- RFC 9110 Retry-After backoff and stream latency diagnostic tracking.

## 2.2.1

- Keeps Dart aligned with the coordinated nRouter SDK patch release; Dart wire
  behavior is unchanged.

## 2.2.0

- Joins the coordinated 2.2.0 release train shared by all nRouter SDKs.
- Includes the current full gateway contract, examples, and security gates.

## 2.1.1

- Add `example/nrouter_example.dart` for pub.dev documentation and package analysis.

## 2.1.0

- Cover all 15 nRouter gateway operations with named helpers.
- Add Anthropic Messages streaming with terminal-event validation.
- Preserve all 13 `x-nr-*` response metadata fields and nine typed errors.
- Add prompt, guardrail, cache, memory, sampling, multipart, and raw-byte support.
- Reject invalid API keys and malformed successful responses before reporting success.
