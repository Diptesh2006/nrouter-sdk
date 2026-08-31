# Changelog

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
