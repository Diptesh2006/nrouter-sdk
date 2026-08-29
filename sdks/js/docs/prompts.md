# Managed prompts

A managed prompt is a template your operator writes and versions in the nRouter
dashboard. The gateway resolves one per request, renders it, and injects it as
the system prompt before the provider sees anything.

Two request fields control it, and this SDK exposes them through
`promptTemplateId` / `promptVariables` on any call, or through the helpers in
`prompts.ts`.

```ts
import { nRouter, promptTemplate, promptVariables, applyPrompt } from '@nrouter_ai/sdk';

const client = new nRouter();

// Run ONE named template.
await client.nr.chat(
  applyPrompt({ model, prompt: 'summarise this' }, promptTemplate(TEMPLATE_ID, { tone: 'terse' }))
);

// Run whatever template the dashboard has ASSIGNED to this key/team/org.
await client.nr.chat(
  applyPrompt({ model, prompt: 'summarise this' }, promptVariables({ tone: 'terse' }))
);
```

## The two fields are independent, which gives three meaningful requests

The gateway takes the template id and the variables off the body separately.
That is not an implementation detail — it is the reason the second call above
works:

| You send | What runs |
|---|---|
| template id **and** variables | that template, rendered with your values |
| **variables only** | the template assigned to this key, team or organization, rendered with your values |
| template id only | that template, rendered with the assignment's own variables plus the system ones |
| neither | whatever the assignment says, or nothing |

**Variables without a template id are a first-class request, not a mistake.** It
is the common shape in production: the application sends values, and the operator
swaps the prompt itself from the dashboard without a deploy. Any "simplification"
that drops variables when no template id is present silently deletes that whole
mode — the call still succeeds, it just renders the wrong prompt.

## An empty template id is the one thing this SDK refuses

An empty string is not an error at the gateway. It is dropped from the request,
and a request carrying variables and no template id is valid — so an
uninitialised id does not fail loudly, it quietly runs a *different* prompt and
bills you for it.

`promptTemplate('')` therefore throws a configuration error. That is the only
client-side refusal in the module; a UUID shape check or an existence check would
be a guess about server state, and a wrong guess refuses requests that work.

## Merge order: your variables win over the assignment's, and lose to four names

The gateway merges the assignment's own variables first, then yours over the top,
then writes four values of its own **last**:

```
org_name    model    timestamp    user_id
```

Because they are written last, a variable you supply under one of those names
never reaches the template. There is no error, no header and no log line you can
see. That ordering is a security property — it is what stops a request body from
spoofing the authenticated organization, user or model inside a prompt your
operator wrote — but it is invisible, so check for it:

```ts
import { systemVariableConflicts, SYSTEM_VARIABLE_NAMES } from '@nrouter_ai/sdk';

systemVariableConflicts({ model: 'mine', tone: 'terse' });  // => ['model']
```

`{{model}}` in a template renders the model that actually served the request, not
your string. Use a different variable name if you meant something else.

## Selections are values; treat them as immutable

`withVariables` returns a new selection and copies the map you hand it. The
helpers copy on construction too, so a mutable per-request context object you
reuse cannot change a selection you built earlier.

```ts
const base = promptTemplate(TEMPLATE_ID, { tone: 'terse' });
const warm = withVariables(base, { tone: 'warm' });   // base is untouched
```

This matters in a shared server process, where a mutating merge would carry one
request's variables into the next one — including into another tenant's call.

## Failure modes, and what each one means

| Response | Cause |
|---|---|
| `400` "managed prompts are disabled for this organization" | Your organization's managed-prompts switch is off **and** you sent a template id or variables. With the switch off and neither field sent, the call proceeds normally with no prompt injected. |
| `400` "nrouter_prompt_template_id must be a UUID string" | The field was sent as something other than a JSON string. |
| `400` "nrouter_prompt_variables must be an object" | Same, for the variables field. |
| `404` "managed prompt template not found" | The id is well-formed but names no template visible to your organization. |

A rendered prompt has a size ceiling. Substitution is an amplifier — a template
repeating one token many times, filled with a large value, expands far beyond
what you sent — so an oversized render is refused rather than executed.

## What is logged

Execution is recorded as metadata: which prompt, which version, the request id.
Prompt text and completion text are not part of that record.
