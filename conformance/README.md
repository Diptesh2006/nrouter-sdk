# Cross-SDK conformance

Ten SDKs, one gateway. Each SDK has its own test suite proving it is
self-consistent. **None of those prove the SDKs agree with each other**, and a
gateway serving ten clients is only as correct as the one that drifted.

This gate closes that gap. It reads `spec/nrouter-sdk-spec.json` — the source of
truth under Rule #14 — and asserts every SDK's source encodes the same base URL,
environment variable, key prefix, every `x-nr-*` header and nine error codes.
It reports and enforces all **150 route-ownership cells** (15 routes × 10 SDKs):
seven first-party transports must carry a native helper with the spec's exact
path and HTTP verb; Android must prove its endpoint-specific Kotlin delegation;
and the JS/Python hybrid clients must prove each route's native helper or their
bounded vendor-client inheritance seam. Python's native cells require the sync
and async helpers. The seven native transports also require incremental
streaming helpers for chat completions, legacy completions, Messages, and
Responses.

The same gate also enforces the coordinated release version across all ten
distribution manifests, JavaScript/Rust lockfiles, Python's imported version,
Android's Kotlin dependency, Swift/Go version markers, and Go's SemVer major
module suffix. Every publish workflow invokes it before credentials are used.

```bash
python3 conformance/check_conformance.py             # check
python3 conformance/check_conformance.py --self-test # prove the gate bites
```

No toolchains needed — it reads source text, so it runs anywhere.

## Why source text and not imports

Importing each SDK would need nine toolchains installed, and the ones that were
missing would be **skipped**. A skipped check reads as a pass, which is the
exact failure mode this gate exists to prevent. A missing source file is
therefore an error here, not a skip — the self-test asserts that.

## What it will not catch

Two things, stated because a gate whose limits are unwritten gets read as
covering more than it does.

**It cannot bind each code to ITS status.** It requires every spec status to
appear in a dispatch, but moving `invalid_request` from 400 to 503 leaves that
set unchanged and passes. A per-code binding is not expressible here: these SDKs
dispatch on the code first and the status second, in separate blocks — the
correct architecture — so a code and its status are legitimately far apart in
the source. A proximity heuristic was tried and flagged six false positives on a
conformant tree; widening the window until they vanished would have measured
nothing, so it was removed rather than tuned.

**It proves a constant is used, not used CORRECTLY.** The declared-and-used rule
catches a deleted parser lookup, but an SDK could still read a header into the
wrong field.

Both gaps are covered per SDK by that SDK's own suite — `each gateway code maps
to its type`, the codeless-status tests, and the metadata parsing tests, every
one mutation-checked. This gate covers what those cannot: that all nine agree
with each other. Neither replaces the other.

## Delegation, stated rather than silent

- **`java`** — the vendor-compatible factory remains, while the additive Java
  11 HTTP surface now owns and is checked for all fourteen metadata headers and
  all nine gateway error codes.
- **`android`** — delegates every wire concern to the shared `sdks/kotlin`
  artifact. It must *prove* the delegation by referencing
  `NRouter.DEFAULT_BASE_URL`, and it **fails if it hardcodes the base URL**,
  because a second copy of that constant is the drift this gate is looking for.
- **`javascript` and `python`** — inherit established resources from their
  bounded OpenAI dependency and own the nRouter-only/native additions. The gate
  partitions every route between those two owners and requires a route-specific
  typed declaration for each delegated resource. This tool verifies that source
  evidence; the complete local gate runs TypeScript and mypy so dead or invalid
  declarations fail. It does **not** claim to parse or prove the vendor
  package's internal path/verb implementation; the package suites exercise the
  locked dependency through HTTP fakes. Mutation tests cover native JS, native
  Python, and vendor-inheritance loss.

## When it goes red

Either the spec changed and an SDK has not caught up, or an SDK dropped
something. Fix the SDK — the spec is derived from the gateway and is the
authority, not the other way round.

## The default-model half — `conformance/source_defaults.py`

An SDK's DEFAULT model fell between every gate here. The spec fixes headers,
endpoints and error codes and carries no default model at all, and the
documentation gate reads prose rather than SDK source. So a default naming a
wire the gateway refuses **for that model** was invisible — while being the very
first call a new user makes.

Two of the ten SDKs ship one (Python's `DEFAULT_MODEL`, R's
`nrouter_chat(model = ...)`), and both convenience wrappers post to
`/v1/chat/completions` with no per-model wire switch. The gateway resolves a
provider endpoint PER WIRE and answers 404 `model_unavailable_on_route` when the
provider declares none, so an Anthropic-family default returned a not-found
error out of the box.

```bash
python3 conformance/source_defaults.py             # check
python3 conformance/source_defaults.py --self-test # prove the gate bites
```

It runs as part of `check_conformance.py`, and has two halves. The first holds
each declared default to the wire its own call path reaches. The second asserts
the eight SDKs registered as default-free genuinely declare none — without it, a
default added to Go tomorrow is invisible, which is the hole a registry-only
check always has.

**What it will not catch:** it works from a REFUSAL list of model families
(`anthropic/`, `claude-`), not an allowlist of servable ids. An allowlist would
have to enumerate every published model and would go stale the moment Super
Admin publishes one, so it would be loosened until it meant nothing. The refusal
list therefore only grows when a provider narrows its endpoint layout — derive
it from `src/sdk/providers/*/transformation.rs::endpoints`, never from memory.

And its second half recognises two declaration shapes — a name containing
`default` and `model`, and a `model = "…"` parameter default (the form R
shipped). A default hidden behind some third spelling, say a bare `MODEL`
constant, would pass. Both shapes are deliberately narrow so that the
`"model": "claude-sonnet-4-5"` map literal every SDK carries in its package doc
comment does not trip it; widening them until doc comments matched would produce
a gate nobody could keep green, which is the same as no gate.

## The client-behaviour half — `conformance/client_timeouts.py`

Two properties the spec cannot express, because neither is on the wire: how long
an SDK WAITS, and whether it RE-SENDS.

Every transport already has an opinion about waiting, and usually the wrong one.
`URLSession.shared` waited 60 s — below what the gateway may honestly take, so it
aborted requests the gateway went on to finish and BILL — and seven days for the
resource, which is not a bound. `package:http` applies no timeout at all, and
`httr` passes none to libcurl, whose own default means "wait forever": one silent
gateway then hangs the calling process, and in a Flutter app that is a spinner
nobody can cancel. The gateway's worst HONEST case before a first byte is roughly
410 s (three provider attempts, each 10 s to connect and 120 s between bytes,
plus up to 20 s of backoff), so every bound sits above that and below infinity —
and a streaming or binary response is bounded by when the bytes STOP, never by a
whole-request ceiling, because severing one of those truncates a response the
customer already paid for.

Re-sending is the money half. A retry is a second call and a SECOND BILL: the
gateway reserves credit once per customer request and owns retry and failover, so
a client retrying on top of it pays twice for one answer with nothing to dedupe
against (gateway gate 8). The two SDKs built on a vendor client inherit automatic
retries unless they say otherwise, which is why Python pins `DEFAULT_MAX_RETRIES
= 0` and JS forces `maxRetries: 0` on every non-GET. Those pins are a required
property here, not an observation somebody once made.

```bash
python3 conformance/client_timeouts.py             # check
python3 conformance/client_timeouts.py --self-test # prove the gate bites
```

It runs as part of `check_conformance.py`, and each property has two halves. An
SDK registered as declaring its own deadline must carry the construct AND a site
that applies it; an SDK registered as inheriting a transport's default must still
declare none, so one added tomorrow is promoted into the checked registry rather
than going unlooked-at. Same shape for retries: the two pinned SDKs must keep
their pin, the eight retry-free ones must contain no retry construct at all. An
inherited bound of `None` — a transport that imposes none — is a failure, not a
note: inheriting decides WHICH bound applies, never that there is none.

**What it will not catch.** Most entries assert the construct's PRESENCE, not its
value, and that is deliberate: Go's 600 s is time-to-headers, Rust's is
between-bytes, Swift's is a whole-request ceiling, Kotlin's `120_000` an OkHttp
socket read in millis. Pinning them to one literal would compare unlike things
and would move numbers that belong in each SDK's own suite — with their semantics
attached — into this file. Only Swift, Dart and R pin values here, and each is
also asserted by that SDK's own tests, so the two cannot drift apart quietly.
The retry scan is likewise narrow on purpose: `isRetryable`, `retry_after` and a
pin of zero are the OPPOSITE of retrying, every SDK ships them, and a scan wide
enough to flag them would be a gate nobody could keep green.
