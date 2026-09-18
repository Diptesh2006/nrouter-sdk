# Sub-skill: Hardening the nRouter SDKs

Skill `nrouter-sdk`, sub-skill `hardening` (merged from the former standalone `nrouter-sdk-hardening` skill,
v1.0.0). Open it when changing error classification, streaming and abort/cancellation, secret
redaction, retry policy, or timeouts in any nRouter SDK — the five cross-language invariants, the
blind spots the conformance gate structurally cannot see, and the drift classes that hide in them.

Ten SDKs, one gateway contract. This sub-skill covers the five behaviours where a per-language
mistake costs a customer money, leaks a credential, or hangs a caller — and where the machine gate
**cannot** catch you.

## Read this first: what `check_conformance.py` structurally cannot see

The blind spots — it cannot bind an error code to its status, it cannot prove a header is used
correctly, any status outside the spec'd errors is invisible to it, and it never touches the
gateway — are stated once in the router (`../SKILL.md`, "Shared facts → What the conformance gate
cannot see"). **Every drift class below lives inside them**, and the third is where the worst
divergence lives (§1).

**So: a green conformance run is necessary and never sufficient.** Behaviour needs a behavioural
test in the SDK's own suite; what the wire answers needs the curl proof harness.

## 1. Error classification — three signals, in order

`error.code` is **OPTIONAL** on the wire (`spec.error_envelope`, `code_optional: true`): the gateway
emits it only where it can name a key under `spec.errors`, and omits it rather than inventing one
elsewhere. Model it as nullable, or a strict decoder breaks on an ordinary 401, 404 or 429. Every SDK
classifies in the same order:

**`code` when present → `type` → HTTP status.** Never on `message` — it is prose written for a
person and it changes. The one exception is the compatibility fallback the spec documents verbatim
under `errors.guardrail_blocked.detection`, for a gateway older than the current spec; use it only
after the first two arms have missed, never as a general rule.

An SDK that classifies on `code` alone silently degrades every ordinary gateway error to a generic
class. That mistake shipped in five SDKs at once; it is why the order above is written down.

⚠️ **The status alone is no longer a discriminator.** Read `spec.errors` and count how many share a
status before you write a dispatch — several codes now land on 400 and several on 402:

```bash
python3 -c "import json,collections;e=json.load(open('spec/nrouter-sdk-spec.json'))['errors'];\
d=collections.defaultdict(list);[d[v['http']].append(k) for k,v in e.items()];\
print(dict(sorted(d.items())))"
```

Four of the newer ones matter to a retry layer because they are **permanent for that body and cost
nothing** — nothing was reserved and nothing was spent, so a retry buys a second identical refusal:
`input_too_large`, `max_output_tokens_too_large`, `fallback_not_allowed` and `guardrail_not_found`.
`max_output_tokens_too_large` is deliberately not clamped for the caller, because silently changing
the ceiling changes what the request costs. The generic `invalid_request` covers a malformed shape.

⚠️ **`service_unavailable` (503) is the inverse case and the one SDKs get backwards.** When it
carries `x-nr-guardrails: unavailable` the request was refused **without being judged** — the
correct client behaviour is to RETRY, not to rewrite the prompt. A client that reports it as a
content block sends callers to change content nothing objected to. That header is the only thing
separating a guardrail-capacity 503 from any other.

⚠️ **The spec'd codes are well aligned. The UNDOCUMENTED statuses are not.** 502 and 504 are
ordinary gateway outcomes — the gateway maps upstream and sandbox failures to 502 — and the spec
documents neither, so the gate cannot see them. Whenever you touch classification, check your SDK's
dispatch for an explicit 502/504 arm and decide deliberately between these three, because all three
exist across the ten today:

- **Service + a "response too large" carve-out** — retryable, *except* when the message says the
  upstream response was too large, which is permanent and must not be retried. This is the correct
  target shape.
- **Service, always** — retries a permanent failure forever.
- **No arm at all** — falls through to a non-retryable generic class, so a genuinely transient
  upstream blip is never retried.

And the worst case: an SDK with no branch at all may return the **raw vendor exception**, so a
caller writing `except nRouterError:` catches nothing. Any SDK wrapping a vendor client must
confirm every status it can emit is wrapped.

**Test it behaviourally.** Assert *this* status maps to *that* class, with a fake returning the
exact envelope. The gate cannot.

## 2. Streaming and abort — cancellation outranks everything

Hard-won, in this order:

1. **Cancellation beats truncation.** A stream that ends without its terminator is truncated — but
   if the caller's cancellation signal is set, report the ABORT. A retry layer that sees
   "unexpected stream drop" resends a call the caller deliberately cancelled.
2. **An aborted request is NEVER retryable.** Force it, ahead of any class-based check. The gateway
   reserves credit once per request; resending a cancelled POST that may already have been billed
   is a double charge.
3. **Never mutate the caller's error or signal object.** Clone before attaching a cause. A caller
   holding a reference to that error must not see it change under them.
4. **The abort signal is rarely at the top of the cause chain.** Transports wrap a real abort as a
   generic fetch failure with the abort as `cause`, and a vendor client wraps that again. **Walk the
   chain with a depth bound and cycle detection; never flatten it** — flattening leaves nothing to
   walk, and the abort check then answers "retryable" for a cancelled, possibly-billed call.
5. **One shared set of abort names**, used by every detection site. Two routines disagreeing about
   what an abort looks like is a real bug that shipped.
6. **Sanitize a structured cancellation reason before attaching it.** A caller may cancel with an
   arbitrary object; if it becomes `.cause` it may carry headers or credentials. Strip
   auth/token/secret/bearer/jwt-shaped keys case-insensitively, drop request and header objects
   whole, and bound depth.
7. **A stream that ends without its terminator is a distinct, NON-retryable error.** Do not let it
   look like a clean finish.

Language-native cancellation is the right primitive: a context, a signal, a token, future-drop.
⚠️ **Never bound a stream with a whole-request timeout** — it severs a healthy long generation. Use
an idle / between-bytes bound.

## 3. Redaction — redact at CONSTRUCTION, not in the formatter

Every SDK masks the branded key prefix and generic provider keys. The trap is *where*.

**Correct:** redact in the error constructor, so the stored message is already safe and every
access path — the field, the exception message, the formatter — is safe.

**The bug:** store the raw gateway text in a **public** error-body field and redact only in a
separate format/display helper. Then `print(e)` is safe and `print(e.body.message)` is not. Several
SDKs are in this shape today; it is the same class as a derived debug printer reflecting a whole
client struct, one layer deeper.

**Rule: if a type crosses a security boundary, the raw string never reaches a public field.** Redact
before storing, or keep the field private behind an accessor that redacts. Also redact the CLIENT
object's own printer — and in languages where a value receiver versus a pointer receiver changes
which printer is chosen, pick the one that cannot fall back to reflection.

## 4. Retries — the client retries NOTHING on a billed path

The invariant itself — every SDK pins automatic client-side retries to zero on billed calls, and the
two vendor-client-wrapping SDKs override a non-zero vendor default that must be re-asserted and
test-proven on any vendor swap, upgrade or reconfiguration — is stated once in the router
(`../SKILL.md`, "Shared facts → The client retries nothing on a billed path").

Retry helpers may be exposed as **advisory** for a caller's own loop. Advisory means the SDK never
runs the loop itself.

Retryable kinds: rate-limit, service, transport, plus 408 and 425 regardless of kind. Never
retryable: anything aborted (§2), and the SDK's own configuration errors.

## 5. Timeouts — idle bounds, not whole-request bounds

The gateway's honest worst case is roughly seven minutes: up to three provider attempts, each with
a connect bound and a long between-bytes bound, plus cumulative backoff. Every SDK derives its
numbers from that figure and uses an **idle / between-bytes** bound so a long generation is not cut.

Two things to hold:

- **Numbers drift between SDKs even while the reasoning agrees.** If you change one, say what the
  new number is derived from. A value no comment explains, and that no other SDK shares, is a
  defect waiting to be discovered by a customer whose long request was cut.
- **A buffered ceiling and a streaming ceiling are different bounds.** Streaming needs a far larger
  one, or none, with the idle bound doing the real work.

## Before you land a change here

- A behavioural test with a fake that actually delays, aborts, or returns the exact envelope.
  Conformance sees none of this.
- If the change touches classification, retry, or abort: state which of the ten SDKs share the
  behaviour and whether they now agree. A fix in one SDK that leaves nine divergent is half a fix.
- If it touches redaction: prove the raw string is unreachable from a public field, not merely
  absent from the formatter.
- Run `python3 conformance/check_conformance.py --self-test` before the gate itself.
