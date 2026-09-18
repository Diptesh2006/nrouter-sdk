# Video

Video is the only **asynchronous** wire nRouter serves. Every other modality
hands you the product in the response; this one hands you a job, and you collect
the result over two more calls.

**All three video routes are served by OpenAI only** — generation, the status
poll and the byte download move together as one capability. This is a provider
allowlist in the gateway, not a catalogue accident: no other provider declares an
upstream video path at a path this gateway mounts, so a video call routed to
Anthropic, AWS Bedrock, Vertex AI, Azure AI Foundry or Alibaba DashScope is
refused, and a fallback chain entry on any of them is skipped rather than tried.
The same holds for images, audio and embeddings. Full table:
[`routing.md`](./routing.md).

| Call | Endpoint | Money |
|---|---|---|
| `video(params)` | `POST /v1/videos` | **bills** |
| `videoStatus(id)` | `GET /v1/videos/{id}` | free |
| `videoContent(id)` | `GET /v1/videos/{id}/content` | free |
| `waitForVideo(id, opts)` | polls `videoStatus` to a terminal status | free |

The money follows that split and nothing on the wire announces it, which is the
one thing to take from this page.

```ts
const created = await client.nr.media.video({
  model: 'sora-2',
  prompt: 'A lighthouse beam sweeping over water at dusk.',
  seconds: 4,           // number or numeric string
  size: '1280x720',     // WIDTHxHEIGHT
});

const jobId = String(created.body.id);        // an opaque nrouter_video_… handle
created.meta.cost;                            // the ONLY call here with one

const done = await client.nr.media.waitForVideo(jobId, {
  pollIntervalMs: 5000,
  timeoutMs: 600_000,
});

const file = await client.nr.media.videoContent(jobId);
await fs.writeFile('out.mp4', file.bytes);
file.contentType;                             // 'video/mp4', or null
```

Model availability is per-plane: no video model is guaranteed to be published for
your key, and an unpublished one answers `404 model_not_found` at create rather
than substituting something else. Check `await client.models.list()` first.

## Create bills; collection is free

The create takes a credit reservation before the provider is called and settles
it from the seconds the **accepted job** reports. The two collection routes take
no reservation, write no spend row, and send no cost header at all.

That asymmetry is deliberate in both directions. Billing on collection would mean
holding a reservation open across a render that takes minutes and may never be
collected — a customer who starts a job and walks away would leak the hold
forever. And a poll produces no seconds, no tokens and no images, so a billed
poll would have to settle at the full reservation estimate: the route that exists
to let you collect what you already bought would become the most expensive one on
the gateway.

**Free is a statement about money and nothing else.** A collection call is still
authenticated, still checked against your key's model access — revoke a key's
access to the model and its in-flight job becomes uncollectable — and still
spends a rate-limit slot. It still carries a request id and the gateway's own
latency measurement. So log the free calls too: they are exactly the traffic that
produces a 429.

## Absence is not `$0`, and it is not `unpriced` either

`x-nr-request-cost` is absent on a free call. It is *also* absent when the gateway
could not price a billed one. Byte-identical on the wire, three different facts:

| | `meta.costStatus` | `meta.cost` | Means |
|---|---|---|---|
| priced | `'exact'` | a number | settled; this is the bill |
| unpriced | `'unpriced'` | `null` | **served and billed**, but no price could be attached |
| free | `null` | `null` | the route bills nothing; the render was settled once, at create |

Both naive readings go wrong, and they go wrong loudly:

- counted as **unpriced**, a forty-poll render reports forty calls the gateway
  "failed to price", and someone goes hunting a pricing bug that does not exist;
- counted as **$0.00**, the client asserts a settled price for a call nobody
  priced — the confident zero the cost contract forbids.

So decide the bucket **at the call site, from the route** — `video()` bills and
`isPriced(meta)` then decides priced from unpriced; `videoStatus()` and
`videoContent()` bill nothing, full stop — never by inspecting a header that is
absent for two unrelated reasons. `costStatus: null` on a free record means the
gateway made no cost claim; writing `'unpriced'` there would claim it tried and
failed.

## What the create costs, and what it refuses first

The gateway places a credit hold sized to the requested duration before calling
the provider, so a long video job holds credits before a frame exists. If your
available balance is below the hold amount, the gateway refuses with HTTP 402
`insufficient_credits`. This is the most expensive single call the gateway serves.

`validateVideoParams()` — exported, and run for you inside `video()` — refuses
these **before the hold is taken**, so a bad argument costs nothing:

- **`seconds`** must be a positive finite number or numeric string, at most
  **1333**. That ceiling ensures your request does not exceed the gateway's
  maximum per-request hold ceiling, keeping credit preflight aligned with your
  account balance.
- **`size`** must be `WIDTHxHEIGHT` with both dimensions above zero. Size matters
  more here than on the images wire: a create **bills on acceptance**, so a
  malformed value the provider rejects downstream is a charge for nothing. On the
  images wire the same mistake is an unbilled 400.

Beyond that, the provider decides what combination it accepts, and a refusal at
create is the cheap place to find out — it bills zero seconds.

**A retry is not a second bill here, it is a second render.** The first job keeps
rendering and keeps being charged for, and you end up holding two handles and one
result you wanted. Pin `maxRetries: 0` on the client and do not wrap `video()` in
a retry loop.

## A job that is accepted and then fails stays billed

Settlement happens at create, and nothing observes the job's terminal state
afterwards, so the charge is **not** reversed when a render fails. That is the
gateway's documented behaviour, not a gap this SDK papers over. The amount is
bounded by the seconds you requested and is recorded on the spend row, so it is
refundable by hand — but you have to ask.

Keep it distinct from a job refused **at** create, which bills zero seconds and
never existed. `waitForVideo` throws a typed `video_failed` error carrying the
job's terminal status and its `meta`, so the two are distinguishable in a log;
record which one happened.

There is no cancellation route in this SDK surface, so a job you no longer want
runs to completion and stays billed.

## The job handle

The create does not return the provider's job id. It returns an opaque
`nrouter_video_…` handle, sealed and authenticated so it cannot be forged or
edited, which binds the job to your organization. That is what lets the two
collection routes — which carry no model and would otherwise have nothing to route
on — find your job and prove it is yours. Treat it as a token, not a structure:
nothing in it is documented to parse, and a future release may change what it
seals.

- **Every refusal a stranger can provoke is the same refusal.** A garbage id, a
  tampered handle and another tenant's handle all return an identical
  `404 job_not_found` with no detail. An error that told them apart would confirm
  that another tenant's job exists.
- **The handle is the only route back to a paid render.** Log it. Nothing else
  will find the job, and the render is already paid for.

## Polling etiquette

`waitForVideo` polls until the job reaches a terminal status — `completed` or
`succeeded` returns the response, `failed` or `cancelled` throws, and the deadline
throws a timeout.

| Option | Default | Bound |
|---|---|---|
| `pollIntervalMs` | 500 | at least **250** |
| `timeoutMs` | 60000 | at least `pollIntervalMs` |

The floor exists because **polling is free of credit but not free of quota**:
every poll is a metered request against your key's rate limit, and the gateway's
steady state for this route is a client polling every couple of seconds. A
tight loop spends your own RPM budget and 429s your real traffic. A `timeoutMs`
below the interval would return a timeout without ever polling once, so that is
refused too.

For a render measured in minutes, a multi-second interval and a generous deadline
are the right shape — the defaults are tuned for a short job, not a long one.

`waitForVideo` exposes **no per-poll hook**: you get the resolved value and never
the intermediate responses. When you need per-call accounting — each poll's own
request id, its observed status, its latency — write the loop yourself over
`videoStatus()`; when you do not, `waitForVideo` is the right call.

## Downloading

`videoContent()` returns a `BinaryResult` for the same reason `speech()` does:
JSON-parsing an MP4 yields an empty object that looks like a successful, empty
result. `bytes` is never empty — a `2xx` with a zero-length body is refused as a
transport error naming the consequence rather than handed back as a success you
would write to a zero-byte file.

The download is bounded at **512 MiB** at the gateway. Write the bytes with the
extension the `contentType` implies rather than one you hoped for.

## `meta.guardrails` splits the same way the money does

The guardrail posture follows the create/collection line exactly. `video()`
publishes `x-nr-guardrails`, so `meta.guardrails` carries the same
`none | monitor | redacted | pass | partial | blocked` token there as on the text wires: the
PRE-CALL chain's posture over the request you sent, upgraded to `blocked` when a
post-call chain withheld the response.

`videoStatus()` and `videoContent()` publish nothing, and `meta.guardrails` is
`null` on both. **That absence is the contract, not a gap.** The two collection
routes resolve no chain at all, so `none` would be a worse answer than silence —
it is an explicit posture asserting a chain was looked for and found empty, which
on those routes was never true. Decide the bucket from the route, exactly as you
already do for cost: the create makes a guardrail claim and the collections make
none.

It is still not a claim about the video. No `Check` in the chain reads bytes, so
neither the render nor the downloaded MP4 is ever inspected. A `pass` on the
create means *your prompt was inspected and allowed*, never *the rendered video
is clean*.

## A runnable one

[`demo/video-agent/`](../demo/video-agent/)
is create → poll → download in one file, with the one call that costs money
accounted for separately from the four that do not. It keeps `freeCalls` and
`unpricedCalls` in different buckets, logs every call including the free ones,
and reports `TOTAL COMPLETE` on a session where four of five calls carry no price
at all. Its mock-gateway suite stamps *no* cost headers on the collection routes
on purpose, and runs with no key and no network.

The general cost rules and the rest of `meta` are in [cost.md](./cost.md).
