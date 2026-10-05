# TypeSafe Jev Examples

`typesafe/jev` is a normal nRouter model ID for rapid System One decisions. It
does not enable a separate API, request flag, classification endpoint, or
JEV-specific response schema. Send it through `/v1/chat/completions`, ask for
the JSON shape your application needs, and validate that JSON before acting on
it.

Every example needs `NROUTER_API_KEY` and sends one live request. They print
the model's decision plus standard nRouter response metadata where the SDK
exposes it: request ID, served model, usage, cost, and optional guardrail,
routing, or intent information. Never treat absent metadata as a negative
result.

## Example index

| SDK | File | Run command |
| --- | --- | --- |
| JavaScript/TypeScript | `sdks/js/examples/typesafe-jev-decision.ts` | `cd sdks/js && npm run build && npx tsx examples/typesafe-jev-decision.ts` |
| Python | `sdks/python/examples/typesafe_system_one.py` | `python sdks/python/examples/typesafe_system_one.py` |
| Go | `sdks/go/demo/jev_system_one.go` | `go run sdks/go/demo/jev_system_one.go` |
| Java | `sdks/java/demo/JevSystemOneExample.java` | See the Java SDK README for the Maven classpath setup. |
| Kotlin | `sdks/kotlin/demo/jev_system_one.kt` | Run with the Kotlin SDK classpath after `./gradlew build`. |
| Android | `sdks/android/demo/JevSystemOneDemo.kt` | Call `run()` from an Android coroutine with a backend-minted key. |
| Rust | `sdks/rust/demo/jev_system_one.rs` | Copy into your Cargo project's `examples/`, then run `cargo run --example jev_system_one`. |
| Swift | `sdks/swift/demo/jev_system_one.swift` | Add to an executable SwiftPM target that depends on `NRouter`. |
| Dart | `sdks/dart/demo/jev_system_one.dart` | `dart run sdks/dart/demo/jev_system_one.dart` |
| R | `sdks/r/demo/jev_system_one.R` | `Rscript sdks/r/demo/jev_system_one.R` |

## What is and is not demonstrated

- **Basic JEV / classification:** The examples request a small JSON incident
  triage decision from `typesafe/jev`. The fields are requested application
  output, not gateway-provided JEV fields.
- **Guardrails:** Dashboard-assigned guardrails run automatically. If a guardrail
  blocks a request, the SDK reports its normal typed gateway error; if the
  gateway sends a guardrail status, it appears in normal response metadata.
  There is no JEV toxicity or safety-score API to invoke.
- **Auto-routing and fallbacks:** These are separate nRouter routing features.
  The gateway exposes an optional served-model/routing result, but it does not
  expose a JEV model-selection score. JEV examples therefore pin the explicit
  `typesafe/jev` model.
- **Streaming:** The SDKs offer generic streaming on chat completions, but the
  gateway has no JEV-specific streaming metadata. Use each SDK's normal stream
  helper when incremental output is required.

For a supported model and wire route on a particular key, query `/v1/models`
before choosing an endpoint. The canonical contract is
[`spec/nrouter-sdk-spec.json`](../spec/nrouter-sdk-spec.json).
