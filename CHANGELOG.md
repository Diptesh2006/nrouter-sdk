# Changelog

⚠️ **Each SDK has its own version line.** They are one product against one
gateway contract (`spec/nrouter-sdk-spec.json`), but every registry versions
independently — so Python 2.1.1 and JavaScript 1.1.2 are the *same* generation
of the same SDK, not a newer and an older release. Do not read across the
sections.

Dates are the registry upload date, which is the only date a consumer can
observe. Versions are immutable once published; nothing here is ever rewritten
to correct a release, only appended to.

## JavaScript / TypeScript — npm `@nrouter_ai/sdk`

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
