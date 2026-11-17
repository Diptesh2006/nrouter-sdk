# Routing and fallbacks

There is no routing option in this SDK, and adding one would not help: the
decision is made at the gateway from the `model` you send and your
organization's configuration.

## Two ways to ask for a model

```ts
await client.nr.chat({ model: 'claude-sonnet-4-5-20250929', prompt }); // direct
await client.nr.chat({ model: 'nrouter/auto', prompt });                // nRouter chooses
```

- **Direct — you choose the model.** nRouter never swaps it for another. A
  concrete model is never re-routed and inherits no hidden fallback: a
  different model answers only through a fallback **you configured yourself**,
  and only when the provider cannot take the request (below). With no fallback
  configured, one model is called once; if its provider is down, the call
  fails. Most organizations configure no fallbacks at all, and that is a
  supported steady state, not a misconfiguration.
- **`nrouter/auto` — nRouter chooses an eligible model for you.** Your
  organization picks how, in the dashboard's Router Settings (or per request via
  `nrouter_optimize: "quality" | "cost"`):
  both strategies score every eligible model with one formula — task
  suitability from public leaderboard ratings minus a cost weight.
  *Best for the task* (the default) weights task suitability; *Lowest cost*
  first restricts eligible models to the active `nrouter_cost_band` ceiling
  (`"low"` `< $1`, `"mid"` `$1` to `< $7` default, `"high"` `$7+` per million
  tokens on the `(3 * input + 1 * output) / 4` blended list rate) and weights
  cost more heavily. The decision model only assesses the request; it never
  picks. If it is off, abstains or times out, or your organization turned off
  Smart model selection, `nrouter/auto` still selects a model. If the active `nrouter_cost_band` leaves zero eligible models, the
  gateway refuses before hold with `400 cost_band_unsatisfiable` (`$0` spent)
  rather than escalating to a higher band; sending `nrouter_cost_band` on a
  Direct model or under `"quality"` returns `400 invalid_request`.

Either way you pay 0% markup on the served model's exact list price, and
`x-nr-model` (`res.meta.model`) always names the concrete model that served the
request.

Model aliases carrying their own routing strategy are no longer offered: a
former alias name in `model` now returns the unknown-model error
(`model_not_found`). Name a model, or send `nrouter/auto`.

## Fallbacks you configure

A direct request can fall back to another model in two ways, both yours:

- a per-model **fallback list** saved in the dashboard's Router Settings, or
- **`nrouter_fallbacks`** on the request — up to 4 model names, tried in order.
  It **replaces** the saved list for that one request; it is not merged with it.
  `model` stays the primary.

On a request for `nrouter/auto`, `nrouter_fallbacks` replaces the fallbacks
`nrouter/auto` would choose: the model it chooses is tried first, then your
targets in order, and an empty list means no fallback. A target your key cannot
route — or a target outside the active `nrouter_cost_band` ceiling on a
cost-mode `nrouter/auto` request — is refused with `400 fallback_not_allowed`,
before any provider call. One hold covers the whole chain; when the funds
cannot cover it the request is refused before any provider call, and a target
is never dropped to make it fit.

Entries whose circuit breaker is open are skipped. Health state is advanced when
an attempt fails, so a provider having a bad minute drops out of the rotation
without you doing anything.

## Which failures actually fail over — this is narrower than you expect

A fallback is tried only when **the provider cannot take the request**:

| Failure | Behaviour | Why |
|---|---|---|
| `429`, `503`, `529` | try the next model | the provider refused before doing any work; nothing was generated |
| a connection that never opened | try the next model | nothing reached the provider |
| a stalled first byte | try the next model | the provider sent nothing back within the time-to-first-byte limit; the abandoned call is not charged to you |
| a deployment fault such as `401` / `404` from the provider | try the next model | that deployment cannot serve the model; another can |
| `500`, `502`, `504` | fail | the provider may have generated **and billed** a completion we never delivered; a retry buys a second one you never see |
| a read timeout | fail | the connection was established, so we cannot tell whether a completion was generated |
| any other `4xx` | fail | a second provider rejects a malformed request too, and you have then paid twice for nothing |

The last model in the list is never cut short at the first-byte limit. Whatever
answers, **you are charged once, for the model that answered**.

## One request, one reservation, one rate-limit slot

The credit reservation and the rate-limit slot are taken **once per request**,
above the walk — not once per attempt. Three attempts hold one reservation and
consume one slot. So a failover cannot double-charge you, and a chain walk during
an outage cannot drain your own rate limit.

## Where cross-provider failover is available, and where it provably is not

| Wire | Cross-provider failover |
|---|---|
| `/v1/chat/completions`, `/v1/completions`, `/v1/responses`, `/v1/messages` | yes — each attempt is prepared for the deployment it targets |
| images, video, audio | no — the credential is prepared once for the whole walk |

On the media wires the provider credential is minted before the walk begins, so a
chain entry naming a **different provider or a different upstream model** is
*refused* rather than called: sending one provider's key to another is a
credential leak wearing a failover's clothes. Those entries are skipped exactly
as an entry with no credential would be.

The practical consequence: configuring a cross-provider fallback chain for an
image or audio model will not give you failover. Chain entries that stay on the
same provider and the same upstream model still work there.

### On the text wires, an entry whose provider does not serve THAT ROUTE is skipped

The `yes` above is about the mechanism, and read alone it is misleading. Failover
being available on a wire does not mean every chain entry can be tried on it: a
provider serves the routes it declares a path for, and **an entry on a provider
that declares no path for the route you called is skipped, exactly like an entry
with no credential.** Nothing is sent, nothing is billed, and the walk moves on.

That is per-entry, not per-route, so a route-level yes/no cannot express it:

| Route | Providers that serve it |
|---|---|
| `/v1/chat/completions` | OpenAI, Azure OpenAI, Azure AI Foundry, Vertex AI, Alibaba DashScope |
| `/v1/responses` | OpenAI, Azure OpenAI, Azure AI Foundry |
| `/v1/messages` | Anthropic, Vertex AI, AWS Bedrock (Anthropic-family models only) |
| `/v1/completions` | OpenAI |
| `/v1/messages/count_tokens` | **Anthropic only** |
| `/v1/embeddings` | **OpenAI only** |
| `/v1/images/generations` | **OpenAI only** |
| `/v1/audio/speech` | **OpenAI only** |
| `/v1/audio/transcriptions` | **OpenAI only** |
| `/v1/audio/translations` | **OpenAI only** |
| `/v1/videos` | **OpenAI only** |
| `/v1/videos/{id}` · `/v1/videos/{id}/content` | **OpenAI only** (same capability as generation) |
| `/v1/models` · `/v1/models/{model_id}` | listing surface — no provider constraint |

### Nine of the eleven non-text routes are single-provider, and that is an ALLOWLIST

Three of the four text rows above list several providers each, which makes the
table look like a general "most providers serve most routes" story. It is not.
The fourth text row, `/v1/completions`, is OpenAI alone — the legacy completions
wire has no cross-provider failover either, so a chain for it can only hold
other OpenAI deployments. And every non-text route that *calls a provider* is
served by **exactly one** provider family. The two exceptions are the listing
routes `/v1/models` and `/v1/models/{model_id}`, which call no provider at all
and carry no constraint — they return the catalogue your key can see:

* **`count_tokens` — Anthropic alone.** It is Anthropic's own token counter; no
  other upstream exposes an equivalent at a path this gateway mounts.
* **embeddings, images, all three audio routes and all three video routes —
  OpenAI alone** (the `openai` and `codex` provider ids, which are the same
  upstream).

This is an allowlist, not a gap that quietly widens: a newly registered provider
serves none of these routes until its upstream path, request shape, response
shape, usage, pricing and credential handling have each been added and tested.

**What that means for a fallback chain.** The per-entry skip rule above applies
here with far more bite: a chain entry for an image, audio, video or embeddings
call on any provider other than OpenAI is skipped, so a chain built entirely from
Anthropic, Bedrock, Vertex or DashScope entries has every entry skipped and the
request fails while the chain looks configured. There is no cross-provider
failover available on those routes today — a fallback there can only be another
OpenAI deployment.

**The case that bites is `/v1/responses`.** Anthropic, AWS Bedrock, Vertex AI and
Alibaba DashScope declare no Responses path, so a Responses chain whose entries
are all on those providers has every entry skipped and the request fails — the
chain looks configured and failover never happens. Same shape one route over:
Anthropic and Bedrock declare no chat-completions path, so they cannot be
failover targets for `/v1/chat/completions` either.

**AWS Bedrock is narrower than the table row alone reads**, and it is the one
place where the answer is per MODEL rather than per provider. Bedrock declares
`/v1/messages` and serves only the Anthropic family there; every other family
takes a different upstream request schema. So a Bedrock entry for a Nova, Llama,
Titan, Qwen, Mistral or DeepSeek model serves **no** text route at all and can
never be a failover target on any of the four wires. Its `nrouter_endpoints` is
empty, which is the honest answer and the one to build chains from.

**Do not infer a model's route from its name.** Ask the gateway. Every entry in
`GET /v1/models` carries the routes that model actually answers on:

```ts
const models = await client.nrouterModels.list();
const entry = models.data.find((m) => m.id === modelId);
entry.nrouter_endpoints; // e.g. ["/v1/messages", "/v1/messages/count_tokens"]
```

Build a chain out of entries whose `nrouter_endpoints` all contain the route you
intend to call, and the walk has somewhere to go on every hop.

## What the response tells you

`res.meta.model` (`x-nr-model`) is the model that **actually served** the
request, which is not always the model you sent: after a fallback it names the
fallback, and for `nrouter/auto` it names the model nRouter chose. Log it.
`x-nr-routing` says `direct` when the first model answered, or `fallback:<n>`
when a fallback you configured did; it is absent on cache hits and refusals.
