# JS SDK test coverage and current issues

The permanent JS test suite lives in `sdks/js/test`. It is not temporary. The
suite is run by `npm test`, which builds `dist/` first and then executes every
`*.test.ts` file through Node's built-in test runner.

Current coverage by file:

| File | Tests | Coverage area |
|---|---:|---|
| `chat-guardrail.test.ts` | 5 | Guardrail-block classification across gateway error envelope shapes. |
| `chat.test.ts` | 35 | Chat calls, OpenAI/Anthropic routing, Claude translation, usage, tool calls, images, retry/error behavior and key redaction. |
| `client.test.ts` | 35 | API key validation, env fallback, base URL, custom fetch, auth header safety, key rotation and request body handling. |
| `errors.test.ts` | 25 | Error-code mapping, retryability, abort handling, `Retry-After`, request IDs and credential redaction. |
| `json.test.ts` | 10 | Generic JSON endpoints, malformed JSON, non-JSON success bodies and gateway error envelopes. |
| `live.test.ts` | 4 | Optional billed live probes for Messages, Chat Completions, Responses and discovered opaque model wires. |
| `memory.test.ts` | 26 | Client-side memory, ordering, clearing, deep copies, async store safety and tenancy-field protection. |
| `meta.test.ts` | 16 | All `x-nr-*` response headers, billing/cost metadata and case-insensitive header parsing. |
| `models.test.ts` | 8 | Model list/get/has helpers, model ID encoding and bad model response handling. |
| `multimodal.test.ts` | 6 | Speech, image, video, embeddings, transcription and media input validation. |
| `multipart.test.ts` | 5 | Multipart request construction, reserved field protection and data URL validation. |
| `options.test.ts` | 36 | Cache flags, guardrail refusal, prompt templates, images, system prompts, extra body fields and tenancy guards. |
| `prompts.test.ts` | 31 | Prompt template IDs, variables, merging, system variable conflicts and prototype pollution defenses. |
| `sampling.test.ts` | 7 | Claude/OpenAI sampling rules and invalid sampling value refusal. |
| `stream.test.ts` | 35 | SSE parsing, streaming chat, aborts, truncation detection, streaming errors and Claude/OpenAI stream translation. |

Total: 325 named tests.

## Issues to track

1. **Local Node version is below the test runner requirement.** The current
   runner executes `.test.ts` files directly. That requires Node with native
   TypeScript stripping support, so Node 22.16 fails before the tests run.
   Use Node 22.18+ or 23+ for local test runs.

2. **Resolved: the test command now fails early on unsupported Node 22 patch
   versions.** `package.json`, `package-lock.json` and `test/smoke.js` now
   require Node 22.18+ so the failure explains the runtime mismatch before the
   TypeScript tests are loaded.

3. **Permanent live gateway coverage is still small compared with the full SDK
   surface.** Most tests use fake transports so they are fast and deterministic.
   That proves SDK behavior, but it does not prove every live model family or
   feature endpoint is available at the gateway.

4. **Live tests are opt-in and skipped by default.** `live.test.ts` only runs
   when live credentials/configuration are present, so CI will not catch a live
   gateway outage unless a separate credentialed smoke workflow is added.

5. **Guardrail behavior is covered as local refusal, not remote selection.**
   The SDK currently prevents `guardrailIds` and guardrail-shaped fields from
   reaching the wire. If the gateway adds first-class guardrail selection, this
   behavior needs a spec change first and then SDK/test updates.

6. **Published-package install smoke is not part of `npm test`.** The suite
   builds and tests local `dist/`, which is good for package contents, but a
   separate smoke test should install the packed tarball or published package in
   a clean temp project before release.

7. **Model ID normalization is inconsistent across discovery and endpoint
   errors.** Model discovery returns ids such as `gemini-2.5-flash-image`, while
   the image endpoint error reports `google/gemini-2.5-flash-image`. That makes
   debugging harder for users.

8. **The aggressive spend target is approximate, not a hard ceiling.** The
   harness checks observed spend after each completed request, so it can
   overshoot the target by the cost of the final request.

9. **No SDK-level capability preflight exists before unsupported endpoint
   calls.** A caller can send a Claude model to `nr.responses()` or a listed
   Gemini image model to `nr.media.image()` and only learn from the gateway
   response that the model is not servable on that endpoint.

10. **Feature endpoint availability depends on exact enabled model ids.**
    Embeddings are confirmed for the tested key, but image, speech,
    transcription and video need endpoint-compatible model ids before a live
    feature test can pass.
