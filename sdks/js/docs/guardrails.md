# Guardrails

Guardrails are configured in the nRouter dashboard and apply automatically to
every call made with your key. **There is no per-request guardrail option**, and
you do not need one.

```ts
// This is the whole API surface. Guardrails already apply.
await client.nr.chat({ model, prompt: '…' });
```

If a guardrail blocks the call you get an error, not a quiet edit — see
[errors.md](./errors.md) for how to catch exactly that condition.

## `guardrailIds` is refused, on purpose

Earlier versions of this SDK accepted a `guardrailIds` option. Nothing on the
serving path ever read it: the gateway runs no per-request guardrail override, so
the field was forwarded to the upstream provider like any other unknown argument
and the provider rejected the call. The option was a fake surface — it looked
like a safety control and scoped nothing.

Passing a non-empty `guardrailIds` now **throws a configuration error** rather
than being quietly dropped. Quietly dropping it would be the worse failure: you
would ask for a safety control and get a normal-looking answer without it.

An empty array is accepted and does nothing, because an empty selection asks for
nothing that could go unserved.

Remove the option. Your organization's guardrails were already running.

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
