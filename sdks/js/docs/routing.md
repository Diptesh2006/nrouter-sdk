# Routing and fallbacks

Routing is **opt-in through the `model` you send**, and nothing else. There is no
routing option in this SDK, and adding one would not help: the decision is made
from your organization's configuration, keyed on the model name in the request.

```ts
await client.nr.chat({ model: 'anthropic/claude-sonnet-4-5-20250929', prompt });  // concrete
await client.nr.chat({ model: 'summariser', prompt });                            // an alias you configured
```

- **A concrete model id is never re-routed.** It resolves to one deployment, it
  is called, and it inherits no hidden fallback. If that provider is down, the
  call fails.
- **An alias you configured** resolves to an ordered chain of deployments plus a
  strategy. The gateway walks the chain.

A model name that matches no configured alias simply has an empty chain, which is
the concrete-model case again: one deployment, one attempt. Most organizations
configure no chains at all, and that is a supported steady state, not a
misconfiguration.

## What the chain gives you

Each chain entry names a provider and an upstream model. The strategy decides the
order the entries are tried in:

| Strategy | Order |
|---|---|
| `priority` | the configured order; the default, and what the gateway falls back to |
| `cost` | cheapest first |
| `latency` | fastest observed first |
| `weighted` | proportional split |
| `pinned` | an exact deployment was named; no selection happens |

Entries whose circuit breaker is open are skipped. Health state is advanced when
an attempt fails, so a provider having a bad minute drops out of the rotation
without you doing anything.

If the health data cannot be read, routing degrades to "walk the chain in order"
rather than failing your request.

## Which failures actually fail over — this is narrower than you expect

Only **429 and 503** (and the Anthropic-family `529`) advance to the next chain
entry. They are the two statuses that mean *the provider refused before doing any
work*.

Everything else is fatal to the walk:

| Status | Behaviour | Why |
|---|---|---|
| `429`, `503`, `529` | try the next entry | nothing was generated and nothing was billed |
| `500`, `502`, `504` | fail | the provider may have generated **and billed** a completion we never delivered; a retry buys a second one you never see |
| `4xx` other than 429 | fail | a second provider rejects a malformed request too, and you have then paid twice for nothing |

Transport failures are narrower still: only a failure during **connect** is
retried. Once the connection was established we cannot tell whether a completion
was generated, and an "unbillable-looking" retry is how one request becomes two
bills.

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
image or audio alias will not give you failover. Chain entries that stay on the
same provider and the same upstream model still work there.

## What the response tells you

`res.meta.model` is the model that **actually served** the request, which is not
always the alias you sent. Log it. On a chain walk it is the only thing in the
response that says which deployment answered.
