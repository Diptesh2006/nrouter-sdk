# JS SDK live agent and feature report

Generated from local checks after pulling `origin/main` on 2026-09-01.

## Environment

- Package: `@nrouter_ai/sdk`
- Local package version: `3.0.0`
- Local Node version: `22.16.0`
- SDK import path used by demos: built `dist/`
- API key source: `NROUTER_API_KEY` from local environment or repo-root `.env`
- Default live model: `claude-haiku-4-5-20251001` (`nrouter-doc-wire: messages`)

The API key is intentionally not printed or stored in this report.

## Build

Command:

```powershell
cd D:\nrouter-sdk\sdks\js
npm run build
```

Result: passed.

This proves the TypeScript SDK compiles and produces `dist/`, which is the code
the npm package exposes through `package.json`.

## Unit test suite status

The permanent JS tests live in `sdks/js/test`.

Current named test count:

| File | Tests |
|---|---:|
| `chat-guardrail.test.ts` | 5 |
| `chat.test.ts` | 35 |
| `client.test.ts` | 35 |
| `errors.test.ts` | 25 |
| `live.test.ts` | 4 |
| `json.test.ts` | 10 |
| `memory.test.ts` | 26 |
| `meta.test.ts` | 16 |
| `models.test.ts` | 8 |
| `multimodal.test.ts` | 6 |
| `multipart.test.ts` | 5 |
| `options.test.ts` | 36 |
| `prompts.test.ts` | 31 |
| `sampling.test.ts` | 7 |
| `stream.test.ts` | 35 |

Total: 284 named tests.

Local blocker: Node `22.16.0` cannot execute `.test.ts` files directly. The
test runner expects a newer Node 22 patch line with native TypeScript stripping.
Running `node --test test/live.test.ts` fails before test execution with a
TypeScript syntax parse error. Use Node `22.18+` or `23+`.

## Demo agent

File:

```text
sdks/js/demo/agent.js
```

Commands:

```powershell
node demo\agent.js --dry-run
node demo\agent.js --live
```

Dry-run result: passed.

- Uses an in-memory requester.
- Does not spend credits.
- Verifies model discovery, message call shape, response text extraction,
  metadata, and local `guardrailIds` refusal.

Live result: passed.

- Model: `claude-haiku-4-5-20251001`
- Text returned: `Demo agent OK`
- Metadata included a real request id.
- Cost status: `exact`

## Aggressive live agent test

File:

```text
sdks/js/demo/aggressive-agent-test.js
```

Small live run:

```powershell
$env:NROUTER_TARGET_USD="0.002"
$env:NROUTER_MAX_REQUESTS="8"
$env:NROUTER_MAX_TOKENS="128"
node demo\aggressive-agent-test.js
```

Result:

- Requests made: 8
- Observed exact cost: about `$0.002136`
- Spend target behavior: approximate, not a strict ceiling. The script checks
  total spend after each completed request, so it can overshoot by one request.
- Passing checks: 11
- Failing checks: 1

Working:

- `client.nrouterModels.list()`
- local refusal of `guardrailIds`
- local refusal of non-nRouter API keys
- `client.nr.countTokens()`
- `client.nr.chat()`
- `client.nr.messages()`
- `client.nr.stream()`

Observed failing check:

- `client.nr.responses()` when intentionally tried with the default Anthropic
  messages model

Gateway error observed:

```text
unknown model: the default Anthropic messages model is not available on /v1/responses
```

Conclusion: Anthropic Claude works through `chat`, `messages`, and streaming,
but this model is not served on `/v1/responses`.

## Feature spend test

File:

```text
sdks/js/demo/feature-spend-test.js
```

Command:

```powershell
$env:NROUTER_EMBEDDING_REPEAT="2"
node demo\feature-spend-test.js
```

Result:

- Embeddings: passed.
- Image generation: failed for listed Gemini image model.
- Speech: skipped unless `NROUTER_SPEECH_MODEL` is provided.
- Transcription: skipped unless `NROUTER_TRANSCRIBE_MODEL` is provided.
- Video: skipped unless `NROUTER_VIDEO_MODEL` is provided.

Embedding details:

- Model: `text-embedding-3-small`
- Calls: 2
- Observed exact cost: about `$0.00000076`
- Returned embedding data for two input strings per call.

Image generation details:

- Model: `gemini-2.5-flash-image`
- Result: failed.

Error:

```text
unknown model: google/gemini-2.5-flash-image is not available on /v1/images/generations
```

Conclusion: the model appears in `/v1/models`, but the gateway says it is not
servable on the image-generation endpoint for this key/provider route.

## Local browser UI

Files:

```text
sdks/js/demo/ui/server.js
sdks/js/demo/ui/public/index.html
sdks/js/demo/ui/public/styles.css
sdks/js/demo/ui/public/app.js
```

Run:

```powershell
cd D:\nrouter-sdk\sdks\js
npm run build
node demo\ui\server.js
```

Open:

```text
http://127.0.0.1:4317
```

The UI calls the server, and the server calls the JS SDK package through
`require('../..')`. The browser never receives the API key.

Backend checks already passed:

- `/api/health`: passed, API key loaded server-side.
- `/api/models`: passed, returned model list.
- `/api/chat`: passed, returned `SDK UI OK`.
- `/api/messages`: passed, returned `SDK UI OK`.
- `/api/guardrail-check`: passed as a local refusal.

## Guardrails

SDK-side behavior:

- `guardrailIds` is refused locally.
- This is intentional: guardrails are assigned in the nRouter dashboard at
  key/team/org/default scope, not selected per request.

Gateway-side live behavior observed:

- PII probe did not hard-block or redact fake email/phone values.
- Jailbreak/prompt-injection probes did not hard-block; the model itself
  refused safely.

Likely reasons:

- guardrail created but not assigned to the tested key/team/org/default scope
- wrong key tested
- dashboard setting not saved/applied yet
- propagation delay
- probe did not match the configured guardrail rule

## Main issues found

1. **Local Node is too old for `.test.ts` execution.** Build passes, but the
   Node test runner fails on TypeScript syntax under Node `22.16.0`.

2. **`package.json` says `node >=22`, but tests need a newer patch line.** The
   runtime floor and test-runner floor are different. Add a preflight check or
   tighten the documented test requirement.

3. **`/v1/responses` does not support the tested Anthropic model.** The SDK
   reports the gateway error correctly; users need a model that is actually
   served on `/v1/responses`.

4. **Some catalogue-listed feature models are not servable on their feature
   endpoint.** `gemini-2.5-flash-image` is listed, but image generation rejects
   it on `/v1/images/generations`.

5. **Gateway guardrail enforcement was not visible in live probes.** SDK local
   refusal works, but dashboard-assigned blocking/redaction was not observed
   for the tested key.

6. **Feature spend is currently limited by available model IDs.** Embeddings are
   confirmed. Speech, transcription, and video need exact enabled model IDs
   before the SDK can test those live.

7. **The demo scripts are useful release diagnostics but are not part of the
   package files yet.** `package.json` currently publishes only `dist` and
   `docs`, so `demo/` is local/repo-only unless the package file list changes.

8. **Model ID normalization is inconsistent across discovery and endpoint
   errors.** Discovery returns `gemini-2.5-flash-image`, while the image
   endpoint error reports `google/gemini-2.5-flash-image`. That is likely a
   gateway/API consistency issue, not a local SDK crash.

9. **The aggressive spend target is not a strict ceiling.** The run targeted
   `$0.002` and ended at about `$0.002136` because spend is known only after the
   billed response returns.

10. **Permanent live tests cover only part of the SDK's feature surface.**
    `live.test.ts` has 4 named live tests, while the SDK exposes chat,
    messages, responses, streaming, embeddings, images, audio, transcription,
    video, guardrail behavior, metadata and model discovery.

11. **There is no SDK-level capability preflight before unsupported endpoint
    calls.** `client.nr.responses()` accepts the Claude model and makes the
    request before the gateway rejects it. Image generation shows the same
    pattern for the listed Gemini image model. A future improvement should use
    `nrouter_endpoints` from model discovery rather than hardcoded name
    guesses.

## How to continue testing

Basic live agent:

```powershell
node demo\agent.js --live
```

Spend on chat/messages/stream:

```powershell
$env:NROUTER_TARGET_USD="1"
$env:NROUTER_MAX_REQUESTS="2000"
$env:NROUTER_MAX_TOKENS="1024"
node demo\aggressive-agent-test.js
```

Spend on embeddings:

```powershell
$env:NROUTER_EMBEDDING_REPEAT="100"
node demo\feature-spend-test.js
```

Test another image model:

```powershell
$env:NROUTER_IMAGE_MODEL="your-image-model-id"
node demo\feature-spend-test.js
```
