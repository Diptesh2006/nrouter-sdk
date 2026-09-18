# Images

One call, on `client.nr.media`:

| Call | Endpoint | Returns |
|---|---|---|
| `image(params)` | `POST /v1/images/generations` | `NRouterResponse<JsonObject>` — always JSON |

**Image generation is served by OpenAI only.** This is a provider allowlist in
the gateway, not a catalogue accident: no other provider declares an upstream
image path at a path this gateway mounts, so an image call routed to Anthropic,
AWS Bedrock, Vertex AI, Azure AI Foundry or Alibaba DashScope is refused, and a
fallback chain entry on any of them is skipped rather than tried — there is no
cross-provider failover on this route. The same holds for audio, video and
embeddings. Full table: [`routing.md`](./routing.md).

There is no image-bytes route. `response_format: 'url'` puts links in the JSON
body and `response_format: 'b64_json'` puts base64 in it, so `image()` returns a
parsed body either way and never a `BinaryResult`. That is the difference from
[`speech()` and `videoContent()`](./audio.md), which really do return bytes.

Fewer models serve images than serve chat, and the set is the live catalogue's
rather than this page's. Fetch it — `await client.models.list()`, or
`curl https://nrouter.ai/api/public/models` — because a model your organization
cannot see answers `404 model_not_found` rather than silently substituting one.
There is no image *edit* and no *variations* route; the gateway mounts generation
only.

```ts
const res = await client.nr.media.image({
  model: 'gpt-image-1-mini',
  prompt: 'A flat vector lighthouse at dusk, three colours, no text.',
  n: 1,                      // 1 through 10 — each image is a separate charge
  size: '1024x1024',
  quality: 'low',
  // no `response_format` — gpt-image-* rejects the field and always returns
  // base64. Send it only to a model that takes it, such as a dall-e-class one.
});

res.body.data;         // the images — base64, or `url` if you asked for it
res.meta.cost;         // number | null
res.meta.costStatus;   // 'exact' | 'unpriced' | null
res.meta.requestId;    // the join key for this call's spend row
```

## What is refused before anything is billed

`n`, `size`, `quality` and `response_format` are bounded inside the SDK, before
the request leaves the process — so a typo costs no round trip and no rate-limit
slot. `validateImageParams(params)` is exported, so a form can be checked against
the same bounds it will be sent under rather than a second copy that drifts.

| Field | Accepted |
|---|---|
| `n` | an integer, 1 through 10 |
| `size` | `auto`, `256x256`, `512x512`, `1024x1024`, `1024x1536`, `1536x1024`, `1024x1792`, `1792x1024` |
| `quality` | `auto`, `standard`, `hd`, `low`, `medium`, `high` |
| `response_format` | `url`, `b64_json` |

Each list is the gateway's own, not a stricter house rule: an SDK that refuses a
request the gateway would accept and bill is a false gate, and it makes the SDK
the only refusal in the path. A model outside these families may take a value
that is not listed — pass it through `extra`, which is merged first so a named
field always wins, and let the gateway and the provider decide.

`n` is the one that is worth reading twice. It is the multiplier on the bill,
not a formatting preference.

## Two billing units, and you cannot tell them apart from the parameters

The model decides which quantity nRouter measured, and the two do not look alike
in the response:

| Model family | Billed per | What comes back |
|---|---|---|
| `gpt-image-*` | **image token** | a `usage` block in the body — `input_tokens`, `output_tokens`, and an `input_tokens_details` split of text tokens from image tokens. The price is computed from those. |
| everything else (`dall-e`-class) | **image** | nothing. No `usage` block at all. The price is a function of `n` × size × quality. |

Two readings of that second row cost money:

- **A per-image model reporting no `usage` is not a fault.** Record
  `imageTokens: null`, never `0` — a zero claims the model reported a
  measurement of nothing.
- **The quantity is not recoverable from the response.** There is no
  `x-nr-image-count` and no `x-nr-image-size`; the count, size and quality the
  settlement was computed on live on the spend row, in `metadata.nrouter_units`.
  So a client reconciles — it records what it asked for and what arrived, and
  matches the request id — rather than recomputing a bill it has no inputs for.

`meta.inputTokens` / `meta.outputTokens` come from the response headers and the
body's `usage` block is a separate reading; either can be absent while the other
is present, so record them separately rather than folding one into the other.

## The hold is per image, and it is taken before the provider is called

The gateway places a credit hold sized to the request **before** calling the provider
and settles down to the real price afterwards. Two consequences before you raise `n`:

- if your available balance is below the hold amount, you receive HTTP 402
  `insufficient_credits` before the provider call — never a partial delivery;
- every retry is a fresh reservation and a fresh bill. There is no retry loop
  worth adding above this call that does not double the charge.

## `unpriced` on an image call

`x-nr-request-cost` is **absent** when the gateway could not price the model. It
is never sent as `0`, so `meta.cost` is `null` and `meta.costStatus` is
`'unpriced'`. The request was served, the images were delivered, and the credit
reserved for it was **settled at the reserved amount** rather than released —
releasing it would make the call free, and no enabled model is.

There is no figure to report for such a call, and there is no figure to invent:

```ts
import { isPriced } from '@nrouter_ai/sdk';

if (isPriced(res.meta)) total += res.meta.cost!;   // 'exact' AND a number
else                    incomplete.push(res.meta.requestId);
```

A total computed over a run containing an unpriced call is a lower bound, not the
run's cost. Label it where you print it. The general rule and the rest of `meta`
are in [cost.md](./cost.md).

## `meta.guardrails` on an image response

The guardrail posture **is** published on this route: `meta.guardrails` carries
the same `none | monitor | redacted | pass | partial | blocked` token here as on the text
wires, read from `x-nr-guardrails`. It reports the PRE-CALL chain's posture over
your REQUEST, upgraded to `blocked` when a post-call chain withheld the response.

It is still not a claim about the picture. Pre-call guardrails read the text you
sent — the `prompt` is a text field like any other — and no check in the chain
scans bytes, so the generated image is never inspected. A `pass` therefore means
*your request was inspected and allowed*, never *the rendered image is clean*.
If the picture matters to your policy, that is a decision for your own pipeline.

`null` remains possible and still means **the gateway made no claim** — an auth
refusal that never reached preflight, say. It is not the explicit `none` posture,
and it is never a reassurance.

## A runnable one

[`demo/image-agent/`](../demo/image-agent/)
loops the call over N prompts and prices, counts, logs and joins every one of
them. It writes a JSONL record on the failure path as well as the success path,
excludes unpriced calls from its total and says `TOTAL INCOMPLETE` when it does,
and records the quantity it asked for and the quantity that arrived — because
those two can differ and no header would ever contradict a client that assumed
they could not. It ships a mock-gateway suite that runs with no key and no
network, so the accounting is checkable without spending anything.
