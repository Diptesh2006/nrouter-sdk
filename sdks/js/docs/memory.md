# Memory and conversation state

**The gateway remembers nothing between requests.** There is no session id, no
thread id, no server-side conversation. Every call is complete in itself.

So "memory" in this SDK is entirely client-side: it is the bookkeeping that
decides which earlier turns you resend with the next request. This package ships
a helper for that bookkeeping (`memory.ts`); what it manages is a local list of
turns, and what it sends is an ordinary `messages` array.

```ts
// This is what memory *is*, underneath any helper.
const messages = [
  { role: 'user', content: 'What is our refund window?' },
  { role: 'assistant', content: '30 days.' },
  { role: 'user', content: 'And for annual plans?' },   // needs the two above to make sense
];

await client.nr.chat({ model, messages });
```

Drop the earlier turns and the model has not "forgotten" — it was never told.

## The three consequences that actually bite

**1. History is re-billed on every turn.** The full message list is input tokens,
every time. A twenty-turn conversation sends turns 1–19 again on turn 20. Cost
grows quadratically with conversation length unless you bound it, and
`res.meta.inputTokens` is where you watch that happen.

**2. You own the context window.** Nothing trims for you. Exceeding the model's
input limit is a refusal, not a silent truncation. Bound the history yourself —
keep the last N turns, summarise older ones into a single turn, or both.

**3. Nothing is shared between processes.** State lives wherever you put it. Two
replicas of your service do not see each other's conversations, and a restart
loses whatever was only in memory. Persist it if it matters.

## Three things that look like memory and are not

**The response cache** returns an identical answer to an identical request within
your own organization. It is keyed on the request, not on a conversation, and it
is tenant-isolated. It makes a repeated question cheap; it does not make the
model aware of an earlier one. Set `cache: false` to force provider egress.

**A managed prompt** injects a system prompt your operator wrote. It is per
request and carries no history — see [prompts.md](./prompts.md).

**The spend and request records** kept for accounting hold metadata: request id,
model, tokens, cost, the authenticated identity. Prompt and completion **bodies
are not stored**. Nothing there could be replayed as conversation state, and
nothing there is readable back through this API.

## System turns

A system prompt is part of the message list you send, so it is subject to the
same rule: if you trim it out, it stops applying. Keep it pinned at the head of
whatever window you send. If a managed prompt is resolved for the request, the
gateway injects it as the system prompt itself, and you do not send one.

## A practical shape

```ts
const MAX_TURNS = 20;

function window(history) {
  const system = history.filter((m) => m.role === 'system').slice(0, 1);
  const rest = history.filter((m) => m.role !== 'system');
  return [...system, ...rest.slice(-MAX_TURNS)];
}

const res = await client.nr.chat({ model, messages: window(history) });
history.push({ role: 'assistant', content: client.nr.text(res) });
```

The number is yours to choose, and `res.meta.inputTokens` is the measurement that
tells you whether you chose well.
