# Guardrails

Guardrails are configured in the nRouter dashboard and apply automatically to
every call made with your key. You never have to ask for them.

```ts
// Guardrails already apply. Nothing to opt into.
await client.nr.chat({ model, prompt: '…' });
```

If a guardrail blocks the call you get an error, not a quiet edit — see
[errors.md](./errors.md) for how to catch exactly that condition.

## `guardrails` adds; it can never remove

A request may name **up to 8** guardrail ids or names your organization owns,
and they run **in addition to** everything already assigned to your key, team or
organization, and in addition to the platform moderation floor.

```ts
await client.nr.chat({
  model,
  prompt: '…',
  guardrails: ['pii-strict'], // runs ON TOP of what already applies
});
```

Add-only is the point. There is no per-request way to turn a guardrail off,
relax one, or replace the set: if that existed, your organization's safety
controls would be caller-optional, and the caller is the party you are guarding
against. A name your organization does not own is refused with
`guardrail_not_found` rather than ignored — a silently dropped guardrail is a
request you believe was inspected and was not.

An empty array is *no selection* and is omitted rather than sent, so
`guardrails: state.selected` with an empty default keeps working. More than
eight is refused by this SDK before the request leaves your process, so you do
not pay a round trip to learn the ceiling.

### The option this replaces

An earlier `guardrailIds` option was a **fake surface**: nothing on the serving
path read it, so the field went to the upstream provider like any other unknown
argument and the provider rejected the call. It looked like a safety control and
scoped nothing, and it was removed rather than left to look live. `guardrails`
is not that field renamed — the gateway reads it, and add-only is what keeps a
request field out of the safety decision.

## How the gateway decides which guardrails run

Two steps, in this order.

**1. The organization switch.** Your organization has a single guardrails
setting. With it off, no guardrail runs for anyone in the organization, whatever
any assignment says.

**2. The narrowest assignment wins, per guardrail.** A guardrail can be assigned
at three scopes, or be an organization default:

```
key  >  team  >  organization  >  organization default
```

For each guardrail, the assignment at the **narrowest** scope that mentions it is
the one that decides — and that single row decides *whether it runs at all*, not
merely that it does.

## It is specificity, not union — and the difference is the whole feature

The intuitive reading is that any enabled assignment switches a guardrail on.
Under that reading a key-scoped **disable** would be inert, because the broader
organization row still matches. The per-key override would be decoration.

So: a key-level assignment **overrides**, it does not **add**.

Worked example. A guardrail is enabled at the organization scope and disabled for
one key:

| Caller | Result |
|---|---|
| any other key in the org | guardrail runs |
| the key with the disabling assignment | guardrail does **not** run |

Under a union it would run for both, and the dashboard toggle would have done
nothing.

## Reading the result

Everything above is about which guardrails *ran*. This is how you find out what
happened, and it is the part most callers get wrong.

Every response carries a guardrail posture. The SDK exposes it as
`meta.guardrails`, read from the `x-nr-guardrails` response header — the same
token on the text wires, the audio routes, images and video.

```ts
const res = await client.chat.completions.create({ model, messages });
res.meta?.guardrails;
// 'none' | 'monitor' | 'redacted' | 'pass' | 'partial' | 'blocked' | 'unavailable'
```

There are **seven** values, and they do not collapse into "blocked or fine":

| status | what it means | were you protected? |
| --- | --- | --- |
| `none` | no guardrail was resolved for this request at all | **no** |
| `monitor` | a chain ran in observe-only mode — it recorded, and could not have refused | **no** |
| `redacted` | an enforcing chain **rewrote** part of your prompt (PII or keyword redaction) before the provider saw it; the request then served | yes |
| `pass` | an enforcing chain ran and found nothing to act on | yes |
| `partial` | an enforcing chain ran but did not inspect the whole request — some content went uninspected | yes |
| `blocked` | an enforcing chain refused; you get an error, not a completion | yes |
| `unavailable` | an enforcing chain could not run, so the request was refused **without being judged** (HTTP 503) — retry it, do not rewrite the prompt | yes |

`partial` means *only* that something went uninspected. It never means "acted on"
— a rewrite is `redacted`, and the two are not interchangeable.

When more than one of these is true of a single request, the gateway reports the
first that applies, in this order: `none`, `monitor`, `redacted`, `partial`,
`pass`.

**`none` and `monitor` are not protection.** That is the whole reason this
section exists. Both return a normal, successful completion, so code written as
`if (status === 'blocked') { … } else { /* protected */ }` treats them as a
clean pass — and a caller believes a policy is enforcing something it is not.

The two are different failures and are worth distinguishing:

- `none` means nothing was configured, or the winning assignment at the
  resolved scope was a disabling one. That is a legitimate resolved outcome
  (see the previous section), not a broken configuration — but it is also not
  a control.
- `monitor` means a chain **did** run, and could not have refused whatever it
  saw. It is the right setting while you are tuning a rule against real
  traffic, and the wrong thing to ship believing it enforces.

If your application depends on a guardrail actually being able to refuse, assert
that:

```ts
const protectedStatuses = new Set(['redacted', 'pass', 'partial', 'blocked']);
if (!protectedStatuses.has(res.meta?.guardrails ?? 'none')) {
  // Nothing could have refused this response. Decide deliberately.
}
```

Note that this is a property of the *request*, not of your account: the resolved
set is per (organization, team, key, phase), so one key can come back `pass`
while another on the same org comes back `none`.

## Consequences worth knowing before you debug

- **A winner that is disabled at its scope does not run.** "No guardrails ran" is
  a legitimate resolved outcome, not evidence of a broken configuration.
- **Failures refuse; they do not fall through.** A database error, a malformed
  configuration or a rule this build cannot execute all refuse the request. The
  forbidden alternative — returning an empty chain — is indistinguishable from
  "this customer configured none", which is a silent loss of protection.
- **Dashboard changes take a few seconds to reach every replica.** Resolved sets
  are cached briefly per (organization, team, key, phase). If you flip a toggle
  and immediately send a request, you may still be measuring the old policy.
- **Both directions are checked.** Guardrails run before the request leaves for
  the provider and again on the response, including on streams, where output is
  held rather than shipped and retracted.

## Billing

A guardrail block on the *response* still costs money: the provider generated the
tokens and billed us for them, so that request settles rather than being
released. A block *before* the provider call releases the hold and costs nothing.
