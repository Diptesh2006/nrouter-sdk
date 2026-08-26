# Cross-SDK conformance

Nine SDKs, one gateway. Each SDK has its own test suite proving it is
self-consistent. **None of those prove the SDKs agree with each other**, and a
gateway serving nine clients is only as correct as the one that drifted.

This gate closes that gap. It reads `spec/nrouter-sdk-spec.json` — the source of
truth under Rule #14 — and asserts every SDK's source encodes the same base URL,
environment variable, key prefix, thirteen `x-nr-*` headers and nine error codes.

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

It proves a constant is *present*, not that it is *used correctly*. An SDK could
name every header and read none of them. That is what each SDK's own
mutation-checked suite is for; the two gates are complements, and neither
replaces the other.

## Exemptions, stated rather than silent

- **`java`, `js`** — wrap a vendor OpenAI SDK, which owns the transport and the
  error types. Held to the connection contract only.
- **`android`** — delegates every wire concern to the shared `sdks/kotlin`
  artifact. It must *prove* the delegation by referencing
  `NRouter.DEFAULT_BASE_URL`, and it **fails if it hardcodes the base URL**,
  because a second copy of that constant is the drift this gate is looking for.

## When it goes red

Either the spec changed and an SDK has not caught up, or an SDK dropped
something. Fix the SDK — the spec is derived from the gateway and is the
authority, not the other way round.
