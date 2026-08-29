# Cost and usage

Every response carries `res.meta`, parsed from the `x-nr-*` headers:

```ts
const res = await client.nr.chat({ model, prompt });

res.meta.requestId;    // join key for a spend row or a support ticket
res.meta.cost;         // number | null  — USD
res.meta.costStatus;   // 'exact' | 'unpriced' | null
res.meta.model;        // what actually served it
res.meta.inputTokens;  // number | null
res.meta.outputTokens;
res.meta.totalTokens;
```

## Absent is not zero, and it is not free

`x-nr-request-cost` is **omitted** when the request could not be priced. It is
never sent as `0`. The SDK surfaces that omission as `cost: null` alongside
`costStatus: 'unpriced'`.

```ts
// WRONG — reports a free request, which no billable model is.
const spend = res.meta.cost ?? 0;

// Right.
if (res.meta.cost === null) {
  logUnpriced(res.meta.requestId, res.meta.costStatus);
} else {
  addToSpend(res.meta.cost);
}
```

`unpriced` means *we do not know what this cost*, not *this cost nothing*. It
still consumed credit: an unpriceable request settles at the amount that was
reserved for it rather than being released, because releasing it would make the
call free.

Treat `null` as unknown everywhere — the same rule applies to `inputTokens`,
`limitSource` and every other field on `meta`. The gateway omits a header rather
than sending a placeholder, so a default of `0` invents a measurement nobody
made.

## Streams always report `unpriced`, and that is honest

A streamed response's headers are written before the first body byte is relayed —
before anything has been generated and before anything can be priced. So on a
stream `x-nr-cost-status` is `unpriced` with no amount, permanently, on every
response.

The real figure lands on the spend row afterwards. Join it with
`res.meta.requestId`, which is present on the stream's headers, rather than
waiting for a cost header that will not arrive.

## Calls that are genuinely free

A handful of routes are free to you. They report no cost header, and that
absence means zero rather than unknown:

| Call | Why |
|---|---|
| `POST /v1/messages/count_tokens` | a gateway whose product claim is cost visibility cannot be the thing that makes estimating cost impossible |
| polling a video job, and fetching its content | the render was settled once, when it was created |
| `GET /v1/models`, `GET /v1/models/{id}` | nothing was priced |

Free to you is not free of policy. Those routes still authenticate your key,
still check your rate limits, and still refuse a blocked key — they cost us a
real upstream call even when they cost you nothing.

## The two numbers that are not the same number

What you are **charged** and what the underlying provider **cost** are tracked
separately, through one shared formula. `res.meta.cost` is what you are charged.

## Rate-limit and budget refusals

A `429` carries `res.meta.limitSource` — which limit measured it, when the
gateway can say. A `null` there means it did not say; do not guess, and do not
send a customer to raise the wrong limit.

A `402` means the reservation failed and **nothing was spent**. See
[errors.md](./errors.md) for telling a credit refusal from a budget refusal.
