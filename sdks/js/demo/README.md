# JS SDK demo agent

This folder contains a tiny demo agent that exercises the JS SDK from built
`dist/` output.

```bash
cd sdks/js
npm run build
node demo/agent.js --dry-run
```

Dry-run mode uses an in-memory requester and does not spend credits.

To hit the live gateway, set `NROUTER_API_KEY` or keep it in the repo-root
`.env` file, then run:

```bash
node demo/agent.js --live
```

The live mode defaults to `claude-haiku-4-5-20251001`. Override it with:

```bash
NROUTER_DEMO_MODEL=claude-sonnet-4-5-20250929 node demo/agent.js --live
```

The demo verifies:

- model discovery through `client.nrouterModels.list()`
- an agent chat/message request
- nRouter response metadata, including request id and cost status
- local guardrail override refusal

## Aggressive live test

`aggressive-agent-test.js` repeatedly exercises the live JS SDK until it reaches
the observed cost target or the request limit. It prints one JSON line per
request and a final summary.

Start small:

```bash
NROUTER_TARGET_USD=0.05 NROUTER_MAX_REQUESTS=20 node demo/aggressive-agent-test.js
```

To target about five dollars:

```bash
NROUTER_TARGET_USD=5 NROUTER_MAX_REQUESTS=500 NROUTER_MAX_TOKENS=1024 node demo/aggressive-agent-test.js
```

On PowerShell:

```powershell
$env:NROUTER_TARGET_USD="5"
$env:NROUTER_MAX_REQUESTS="500"
$env:NROUTER_MAX_TOKENS="1024"
node demo\aggressive-agent-test.js
```

It currently tests:

- `client.nrouterModels.list()`
- local refusal of `guardrailIds`
- local refusal of non-nRouter API keys
- `client.nr.countTokens()`
- `client.nr.chat()`
- `client.nr.messages()`
- `client.nr.responses()`
- `client.nr.stream()`

The spend number comes from `x-nr-request-cost` response metadata. If a response
is unpriced, it counts as zero in this script because there is no exact cost to
sum.

## Local browser UI

The UI calls a tiny local Node server. The browser never receives the API key;
the server loads `NROUTER_API_KEY` and calls the JS SDK package through
`require('../..')`, which resolves `sdks/js/package.json` and uses built `dist/`.

```bash
cd sdks/js
npm run build
node demo/ui/server.js
```

Open:

```text
http://127.0.0.1:4317
```

The UI can:

- check whether the server loaded the API key
- list models
- run `client.nr.chat()`
- run `client.nr.messages()`
- verify local guardrail override refusal

## Feature spend test

`feature-spend-test.js` is for testing feature billing beyond normal LLM text
calls.

```powershell
cd D:\nrouter-sdk\sdks\js
npm run build
node demo\feature-spend-test.js
```

By default it tries:

- embeddings with `text-embedding-3-small`
- image generation with `gemini-2.5-flash-image`

Speech, transcription and video need exact model IDs. If those models are added
to your key later, run:

```powershell
$env:NROUTER_SPEECH_MODEL="your-speech-model-id"
$env:NROUTER_TRANSCRIBE_MODEL="your-transcription-model-id"
$env:NROUTER_VIDEO_MODEL="your-video-model-id"
node demo\feature-spend-test.js
```

Useful overrides:

```powershell
$env:NROUTER_EMBEDDING_MODEL="text-embedding-3-large"
$env:NROUTER_IMAGE_MODEL="gemini-3-pro-image"
$env:NROUTER_IMAGE_SIZE="1024x1024"
node demo\feature-spend-test.js
```

To spend more on embeddings, repeat the embedding call:

```powershell
$env:NROUTER_EMBEDDING_REPEAT="100"
node demo\feature-spend-test.js
```

Embeddings are very cheap, so even 100 calls may still be only a tiny amount of
credit.
