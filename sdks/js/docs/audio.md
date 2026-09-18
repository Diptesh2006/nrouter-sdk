# Audio and voice

Three calls, on `client.nr.media`:

| Call | Endpoint | Returns |
|---|---|---|
| `speech(params)` | `POST /v1/audio/speech` | `BinaryResult` — audio bytes |
| `transcribe(params)` | `POST /v1/audio/transcriptions` | `TranscriptionResult` — text, in the caller's language |
| `translate(params)` | `POST /v1/audio/translations` | `TranscriptionResult` — text, always in English |

**All three audio routes are served by OpenAI only.** This is a provider
allowlist in the gateway, not a catalogue accident: no other provider declares an
upstream path for speech, transcription or translation at a path this gateway
mounts, so an audio call routed to Anthropic, AWS Bedrock, Vertex AI, Azure AI
Foundry or Alibaba DashScope is refused, and a fallback chain entry on any of
them is skipped rather than tried. The same holds for images, video and
embeddings; `count_tokens` is the mirror image, served by Anthropic alone. Full
table: [`routing.md`](./routing.md).

Fewer models serve audio than serve chat, and the set is the live catalogue's
rather than this page's. Fetch it — `await client.models.list()`, or
`curl https://nrouter.ai/api/public/models` — and pick an id that declares the
modality, rather than assuming a model your key can reach for chat can also
speak or listen.

Every one of them returns `meta: ResponseMeta` — the same parsed `x-nr-*`
metadata as a chat call, including on the binary one. That is the point of
`speech()` returning a struct rather than a `Uint8Array`: the bytes and the
request id that identifies the billed request arrive together, and neither can
be dropped by accident.

## Speech: bytes, and an empty body is an error

```ts
const out = await client.nr.media.speech({
  model: 'tts-1',
  input: 'The build is green.',
  voice: 'alloy',
  response_format: 'mp3',   // mp3 | wav | opus | aac | flac
  speed: 1.0,               // optional
  instructions: 'Read it flatly.',  // optional, and it is scanned — see below
});

await fs.writeFile('out.mp3', out.bytes);
out.contentType;   // 'audio/mpeg', or null when the gateway did not say
out.meta.cost;     // number | null
```

`bytes` is never empty. A `2xx` with a zero-length body is refused as a
transport error naming the consequence — the request was billed and no media
arrived — rather than handed back as a success you would write to a zero-byte
file. A JSON body on this endpoint is likewise refused: it is an error envelope
that lost its status somewhere in the chain, and it is re-thrown as the typed
error its `code` names, so an existing `catch` keeps working.

`pcm` is missing from `SpeechResponseFormat` deliberately. It is headerless raw
samples, so the file opens in no player without the sample rate passed out of
band. If you want it and know what to do with it, put it in `extra`.

## Transcription and translation: two arms, because four media types

`response_format` decides what comes back, and the result type is discriminated
on it rather than flattened:

```ts
const res = await client.nr.media.transcribe({
  file: bytes,                 // Uint8Array | ArrayBuffer
  fileName: 'speech.mp3',      // MUST carry the real extension
  model: 'gpt-4o-mini-transcribe',
  response_format: 'verbose_json',
  language: 'en',              // ISO-639-1 hint: accuracy and latency, not a filter
  timestampGranularities: ['word'],
});

if (res.kind === 'json') {
  res.body;    // segments, words, timings
  res.text;    // string | null — the `text` field when the provider sent one
} else {
  res.text;    // 'text' | 'srt' | 'vtt', verbatim; for srt/vtt the line breaks ARE the format
}
```

`translate()` takes the same parameters minus two. There is no `language`,
because the output is always English. There is no `timestampGranularities`,
because the translations wire accepts only file, model, prompt, `response_format`
and temperature — offering it would have let you ask for word timings that never
arrive, with nothing saying why.

Three upload rules. The last two are checked in this SDK, before anything
reaches the network; the first is the gateway's:

- **25 MiB.** A larger upload is refused at the gateway's edge, before any credit
  is reserved. This SDK does not pre-check the size, so measure your own bytes if
  you would rather fail without a round trip.
- **The filename needs a real extension** — `speech.mp3`, not `speech`. Upstream
  providers pick their decoder from it and reject an extensionless name outright.
  A path separator or a line break in the name is refused too: the name lands in
  a MIME header parameter, and MIME header parameters have no escape for either.
- **`timestampGranularities` is sent as repeated `timestamp_granularities[]`
  fields**, not a comma-joined string. A joined string matches no enum value at
  the provider, so it is dropped and the word timings simply never appear.

`extra` on these calls is form fields, and a name the endpoint already owns is
**dropped** rather than emitted first. Multipart is not JSON: the gateway settles
each field from the FIRST part carrying that name, so emitting `extra` ahead of
the named parameter — the ordering that makes the named field win in a JSON body —
would do the opposite here and let `extra.model` be the model that is authorized,
routed and billed while the one you passed is ignored.

## What a call costs, and when it is not priced

Audio is metered on quantities that are not tokens, and the three routes get
there differently.

| Route | Priced from | Priced when |
|---|---|---|
| `speech` | **characters** of `input` (`input_cost_per_character`) | always — the quantity is in the request, so it is known before the call |
| `transcribe`, `translate` | **tokens**, when the model reports `usage.type = tokens` (`gpt-4o-mini-transcribe`, `gpt-4o-transcribe`) | whenever the provider states the usage |
| `transcribe`, `translate` | **seconds**, from the response's `duration` | only with `response_format: 'verbose_json'` — a plain `json`, `text`, `srt` or `vtt` body carries no duration at all |

So the one that bites: **a `whisper-1` transcription without
`response_format: 'verbose_json'` is served normally and settles UNPRICED.** The
gateway has no readable quantity, so it records `x-nr-cost-status: unpriced` and
sends no `x-nr-request-cost`, and the credit reserved for the call is *settled*,
never released. Releasing it would make the request free, which no billable call
is. You get your transcript; you do not get a figure.

Speech is the opposite case: the character count is in the request, so the
reservation taken before the call is replaced by the exact amount after it. An
empty `input` is a 400 before any of that happens.

Never sum a missing cost as zero:

```ts
import { isPriced } from '@nrouter_ai/sdk';

if (isPriced(res.meta)) total += res.meta.cost!;
else                    incomplete.push(res.meta.requestId);
```

A total computed over a run containing an unpriced call is not the run's cost —
it is a lower bound. Say so where you print it. The real figure lands on the
dashboard spend row afterwards; join it on `x-nr-request-id`.

**The quantity itself is not a header.** Characters and seconds are not published
on the response — they live on the spend row, in `metadata.nrouter_units`. There
is no client-side field to read them from, so an app that needs to show "42
seconds transcribed" measures its own input rather than reading it back.

The general rule and the rest of `meta` are in [cost.md](./cost.md).

## Two things that do not exist here

- **No streaming TTS.** A `stream_format` passed through `extra` is buffered:
  you get the complete audio when the call returns, not a first byte sooner.
  Latency is what it is; design the turn around that rather than around a stream
  that never starts.
- **No realtime or WebSocket surface.** Voice is a request/response cascade on
  these three routes, not a session.

## `meta.guardrails` on an audio response

The guardrail posture **is** published on all three audio routes:
`meta.guardrails` carries the same `none | monitor | redacted | pass | partial | blocked`
token here as on the text wires, read from `x-nr-guardrails`. It reports the
PRE-CALL chain's posture over your REQUEST, upgraded to `blocked` when a
post-call chain withheld the response.

**Expect `partial` on `transcribe()` and `translate()`, and do not alarm on it.**
Those two wires carry an upload that is not itself a text channel, so an
enforcing chain answers `partial` on the ordinary path rather than `pass`. A
client that treats `partial` as an anomaly will treat every speech-to-text call
it makes as one. On `speech()` an enforcing chain that inspected the whole
request answers `pass`.

It is still not a claim about the audio. Pre-call guardrails scan the text you
send — `input` and `instructions` on speech, `prompt` on an upload — and no
`Check` in the chain scans bytes, so the generated audio is never inspected. A
`pass` on `speech()` means *your request was inspected and allowed*, never *the
spoken output is clean*. If the spoken output matters to your policy, transcribe
it and scan the text.

`null` remains possible and still means the gateway made no claim — never
"nothing ran", which is the explicit `none`.

## The voice cascade

There is no voice endpoint. A voice turn is three calls you compose yourself:

```
audio in → transcribe() → nr.chat() → speech() → audio out
```

Each leg is separately authenticated, rate-limited, guardrailed, priced and
recorded, so a turn produces three request ids and three spend rows — and any
one of them can be the unpriced one. Track cost per leg, not per turn.

A runnable version, with a per-call cost table and a session total that reports
`TOTAL INCOMPLETE` the moment any leg comes back unpriced, is at
[`demo/voice-agent/`](../demo/voice-agent/).

For interactive testing and building conversational voice agents:
- **Interactive Terminal Agent**: [`demo/interactive-agent.mjs`](../demo/interactive-agent.mjs) runs a conversational REPL in your terminal with streaming text, turn latency/cost tracking, and optional speech synthesis playback (`node demo/interactive-agent.mjs --live --voice`).
- **Interactive Web UI**: [`demo/ui/server.js`](../demo/ui/server.js) serves a browser interface on `http://127.0.0.1:4317` with browser microphone input (`SpeechRecognition`), real-time SSE streaming, voice turn generation, and instant audio replay.

Two things worth copying from it. Latency is the sum of the legs, and each leg
reports its own on `meta.latencyMs` — milliseconds from the gateway's edge until
that response's headers were ready, present on every response — so the STT model
is a UX decision measurable per leg and not only a cost one. And a failed leg is not a failed
turn: a transcription that throws leaves you holding audio you were billed for,
which is worth logging with its request id rather than retrying blind — the
retry is a second call and a second bill.
