# `@nrouter_ai/sdk` — semantics

Written for a coding agent that already has the package installed and needs to
know what a request actually *does*. Each page answers one question the type
signatures cannot: which of two plausible readings is the real one.

| Page | The question it settles |
|---|---|
| [prompts.md](./prompts.md) | Which prompt runs, and why variables without a template id are a first-class request rather than a mistake |
| [guardrails.md](./guardrails.md) | Which guardrails run, why it is specificity and not union, and why there is no per-request override |
| [routing.md](./routing.md) | When a request can fail over to a second provider, and when it provably cannot |
| [cost.md](./cost.md) | Why an absent cost is not a free request, and which calls are genuinely free |
| [errors.md](./errors.md) | Why classifying on the error `code` alone silently loses conditions |
| [memory.md](./memory.md) | Where conversation state lives, and what the gateway does not remember |

## The one shape everything else hangs off

```ts
import { nRouter } from '@nrouter_ai/sdk';

const client = new nRouter();                 // reads NROUTER_API_KEY
const res = await client.nr.chat({
  model: 'anthropic/claude-sonnet-4-5-20250929',
  prompt: 'Hello!',
});

console.log(client.nr.text(res));
console.log(res.meta.cost ?? `unpriced (${res.meta.costStatus})`);
```

`res.meta` is parsed from the `x-nr-*` response headers and every field on it is
nullable. A null there means *the gateway did not say*, never a zero — see
[cost.md](./cost.md).

## Two rules that apply on every page

**Tenancy is never in a request.** The organization, team and user are resolved
from the authenticated key alone. No option in this SDK writes an
`organization_id`, `team_id`, `org_id` or `user_id` into a request body, and a
value you put there through the `extra` escape hatch is not authoritative to the
gateway either — it is forwarded to the provider like any other unknown field.

**The set of nRouter request fields is closed.** The gateway strips the fields it
recognises and forwards everything else to the upstream provider. So a field this
SDK does not model is not rejected with a helpful message: it reaches the
provider, which rejects the call for its own reasons, after you have paid for the
round trip. If an option is not in the types, it does not exist.

## Model names

Model ids are the live catalogue's, not this document's. Fetch them:

```bash
curl https://nrouter.ai/api/public/models
```

or from a key-authenticated client, `await client.models.list()`.
