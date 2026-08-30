# Cross-SDK conformance

Ten SDKs, one gateway. Each SDK has its own test suite proving it is
self-consistent. **None of those prove the SDKs agree with each other**, and a
gateway serving ten clients is only as correct as the one that drifted.

This gate closes that gap. It reads `spec/nrouter-sdk-spec.json` — the source of
truth under Rule #14 — and asserts every SDK's source encodes the same base URL,
environment variable, key prefix, thirteen `x-nr-*` headers and nine error codes.
For the six first-party native transports it also requires a named helper for
every operation the spec marks supported, plus incremental streaming helpers
for chat completions, legacy completions, Messages, and Responses.

```bash
python3 conformance/check_conformance.py             # check
python3 conformance/check_conformance.py --self-test # prove the gate bites
```

No toolchains needed — it reads source text, so it runs anywhere.

## Why source text and not imports

Importing each SDK would need nine toolchains installed, and the ones that were
missing would be **skipped**. A skipped check reads as a pass, which is the
exact failure mode this gate exists to prevent. A missing source file is
therefore an error here, not a skip — the self-test asserts that.

## What it will not catch

Two things, stated because a gate whose limits are unwritten gets read as
covering more than it does.

**It cannot bind each code to ITS status.** It requires every spec status to
appear in a dispatch, but moving `invalid_request` from 400 to 503 leaves that
set unchanged and passes. A per-code binding is not expressible here: these SDKs
dispatch on the code first and the status second, in separate blocks — the
correct architecture — so a code and its status are legitimately far apart in
the source. A proximity heuristic was tried and flagged six false positives on a
conformant tree; widening the window until they vanished would have measured
nothing, so it was removed rather than tuned.

**It proves a constant is used, not used CORRECTLY.** The declared-and-used rule
catches a deleted parser lookup, but an SDK could still read a header into the
wrong field.

Both gaps are covered per SDK by that SDK's own suite — `each gateway code maps
to its type`, the codeless-status tests, and the metadata parsing tests, every
one mutation-checked. This gate covers what those cannot: that all nine agree
with each other. Neither replaces the other.

## Exemptions, stated rather than silent

- **`java`** — the vendor-compatible factory remains, while the additive Java
  11 HTTP surface now owns and is checked for all thirteen metadata headers and
  all nine gateway error codes.
- **`android`** — delegates every wire concern to the shared `sdks/kotlin`
  artifact. It must *prove* the delegation by referencing
  `NRouter.DEFAULT_BASE_URL`, and it **fails if it hardcodes the base URL**,
  because a second copy of that constant is the drift this gate is looking for.

## When it goes red

Either the spec changed and an SDK has not caught up, or an SDK dropped
something. Fix the SDK — the spec is derived from the gateway and is the
authority, not the other way round.
