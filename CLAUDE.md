# CLAUDE.md — nrouter-sdk

Nine SDKs for the nRouter gateway, and the gate that keeps them speaking one
contract. **The only PUBLIC repo in the workspace** — everything committed here
is world-readable. Treat every file as published.

Independent repo, own remote, nested in `nrouter-brain`, gitignored by it.
**Edit in place; commit and push here.** Rule #20: `git pull --ff-only` → edit →
focused tests → review → push, never force.
**HTTPS git fails — use SSH (`git@github.com:…`).**

Left `nrouter-ent-ai-hub` on 2026-08-26 with its full history intact
(`git subtree split`, 37 commits, identical tree hash). The old public history is
preserved on the `main-legacy-pre-extraction` branch.

This repo owns no `rules/`, but the workspace rules still bind. Claude Code loads
them automatically; Codex, Gemini CLI and Antigravity do not and must open:

- `/Users/gurukallam/nr/nrouter-brain/sdlc/rules/00-permanent-rules.md` —
  especially **#14 the SDK is canonical**, #18 scratch, #20 direct-main,
  #28 never a $0 price, #35 brand.
- `/Users/gurukallam/nr/nrouter-brain/nrouter-rust-gateway/rules/00-gateway-rules.md`
  — the wire contract these SDKs implement. §4f gate 9 is why no provider
  credential or engine name may appear in a customer-visible surface.

## Layout

```
Package.swift        # the SHIPPING Swift manifest — SwiftPM reads the REPO ROOT
spec/                # nrouter-sdk-spec.json — the SoT under Rule #14
conformance/         # the cross-SDK gate; run it before every release
open-issues.csv      # the backlog, each row recording how it was verified
sdks/{python,js,java,kotlin,android,swift,rust,dart,r}/
examples/            # canonical snippets nrouter-app imports (Rule #14)
```

## The one rule that matters here

**`spec/nrouter-sdk-spec.json` is the source of truth, derived from the
gateway** — never the other way round. Base URL, `NROUTER_API_KEY`, the
`sk-nrouter-` prefix, thirteen `x-nr-*` headers and nine error codes. When an
SDK and the spec disagree, the SDK is wrong.

```bash
python3 conformance/check_conformance.py             # all nine agree?
python3 conformance/check_conformance.py --self-test # prove the gate bites
```

Each SDK's own suite proves it is self-consistent; the gate proves they agree
with each other. Neither replaces the other, and `conformance/README.md` states
plainly what the gate cannot catch.

## Traps

- **The gateway's main error path sends NO `code`** — it emits
  `{"error":{"type":"gateway_error","message":…}}`. Classifying on `code` alone
  makes `guardrail_blocked` unreachable. Order: code (when sent) → status →
  message. This shipped broken in five SDKs at once.
- **Unpriced is not free.** `x-nr-request-cost` is ABSENT when unpriced; render
  it as `0` and you report a free request, which no enabled model is (Rule #28).
- **A non-JSON or unparseable 2xx is a BILLED response**, not an empty one.
- **Never print the API key.** Rust's derived `Debug` and any Swift `struct`
  reflect it by default; R's list printer shows it. All five native SDKs redact.
- **Two Swift manifests exist** — the root one ships, `sdks/swift/` is the dev
  loop. Change both; the conformance gate fails if they drift.

## Publishing

Per SDK, in its own `PUBLISHING.md`. Registry status is a fact — check it, do
not trust the README: `open-issues.csv` tracks what is unpublished.

⚠️ **This repo is public.** No credentials, no internal hostnames, no customer
data, no engine name (Rule #29). A secret committed here is a secret disclosed.
