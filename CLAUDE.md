# CLAUDE.md — nrouter-sdk

Ten SDKs for the nRouter gateway, and the gate that keeps them speaking one
contract. **The only PUBLIC repo in the workspace** — everything committed here
is world-readable. Treat every file as published.

## ⛔ SUPPORT SCOPE: npm, PyPI and Maven — owner decision 2026-08-29, reviewed monthly

**Ten SDKs exist here; THREE are supported.** Work that ships as a supported
package goes to `sdks/{js,python,java}`. Kotlin, Android, Rust, Dart and R are
registry-distributed public previews; Swift and Go use immutable source tags.
Distribution does not add a support commitment. All ten use one coordinated
release version and remain subject to the same conformance gate.

| supported | registry | package |
|---|---|---|
| `sdks/js` | npm | `@nrouter_ai/sdk` |
| `sdks/python` | PyPI | `nrouter-sdk` |
| `sdks/java` | Maven Central | `ai.nrouter:nrouter-sdk` |

Public preview distribution: `sdks/r` is available from
`https://nrouterai.r-universe.dev/nrouter` as package `nrouter`. Preview publication is
not a support commitment.

Derive the live versions; never quote one from prose:

```bash
curl -s https://registry.npmjs.org/@nrouter_ai%2Fsdk | python3 -c "import sys,json;print(json.load(sys.stdin)['dist-tags']['latest'])"
curl -s https://pypi.org/pypi/nrouter-sdk/json  | python3 -c "import sys,json;print(json.load(sys.stdin)['info']['version'])"
curl -s https://repo1.maven.org/maven2/ai/nrouter/nrouter-sdk/maven-metadata.xml | grep -oE '<release>[^<]+</release>'
```

**This narrows what is supported, NOT what must stay correct.** All ten SDKs
still run in `conformance/check_conformance.py`, and a contract change still has
to land in all ten — a spec edit that leaves seven behind turns a green gate
into a lie the day one of them is supported. Source tags do not broaden the
support commitment.

⚠️ Every registry remains immutable, but the ten SDKs use ONE release version.
`spec/nrouter-sdk-spec.json` is canonical and the conformance gate checks every
manifest, lockfile and Swift/Go version marker. A breaking change in any SDK
therefore advances the coordinated major version for all ten.

Independent repo, own remote, nested in `nrouter-brain`, gitignored by it.
**Edit in place; commit and push here.** Rule #20: `git pull --ff-only` → edit →
focused tests → review → push, never force.
**HTTPS git fails — use SSH (`git@github.com:…`).**

Left `nrouter-ent-ai-hub` on 2026-08-26 with its full history intact
(`git subtree split`, 37 commits, identical tree hash). The old public history is
preserved on the `main-legacy-pre-extraction` branch.

This repo owns no `rules/`, but the workspace rules still bind. Claude Code loads
them automatically; Codex, Gemini CLI and Antigravity do not and must open:

- `~/nr/nrouter-brain/sdlc/rules/00-permanent-rules.md` —
  especially **#14 the SDK is canonical**, #18 scratch, #20 direct-main,
  #28 never a $0 price, #35 brand.
- `~/nr/nrouter-brain/nrouter-rust-gateway/rules/00-gateway-rules.md`
  — the wire contract these SDKs implement. §4f gate 9 is why no provider
  credential or engine name may appear in a customer-visible surface.

## Layout

```
Package.swift        # the SHIPPING Swift manifest — SwiftPM reads the REPO ROOT
spec/                # nrouter-sdk-spec.json — the SoT under Rule #14
conformance/         # the cross-SDK gate; run it before every release
sdks/{python,js,java,kotlin,android,swift,rust,dart,r,go}/
examples/            # canonical snippets nrouter-app imports (Rule #14)
```

## The one rule that matters here

**`spec/nrouter-sdk-spec.json` is the source of truth, derived from the
gateway** — never the other way round. Base URL, `NROUTER_API_KEY`, the
`sk-nrouter-` prefix, every `x-nr-*` header and nine error codes. When an
SDK and the spec disagree, the SDK is wrong.

```bash
python3 conformance/check_conformance.py             # all ten agree?
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

Per SDK, in its own `PUBLISHING.md`. Registry status is a fact — query the
registry immediately before a release rather than trusting prose.

⚠️ **This repo is public.** No credentials, no internal hostnames, no customer
data, no engine name (Rule #29). A secret committed here is a secret disclosed.

<!-- BEGIN GENERATED: permanent-rules-pointer (bootstrap.sh) -->

## The Permanent Rules — for Codex, Gemini CLI and Antigravity

You are reading this through `AGENTS.md` or `GEMINI.md`, which symlink to this file.
Claude Code receives the rules below automatically via `@import`; **your harness does
not**. They are mandatory all the same. Read the ones relevant to what you are about to
touch BEFORE editing — each path resolves from your home directory (`~/`).

**They are listed in READING ORDER, not alphabetically.** The first two are the
authority and apply to everything; the rest are path-scoped detail that matters only
when you touch that area. If you read nothing else, read the first one.

- `~/nr/nrouter-brain/sdlc/rules/00-permanent-rules.md`
- `~/nr/nrouter-brain/sdlc/rules/00-workspace-repos.md`
- `~/nr/nrouter-brain/sdlc/rules/10-testing.md`
- `~/nr/nrouter-brain/sdlc/rules/20-tdd-and-fleet.md`
- `~/nr/nrouter-brain/nrouter-app/rules/02-multi-tenancy.md`
- `~/nr/nrouter-brain/nrouter-app/rules/03-credit-safety.md`
- `~/nr/nrouter-brain/nrouter-app/rules/05-frontend-standards.md`
- `~/nr/nrouter-brain/nrouter-app/rules/07-stripe-integration.md`
- `~/nr/nrouter-brain/nrouter-app/rules/11-api-routes.md`
- `~/nr/nrouter-brain/nrouter-app/rules/13-enterprise-features.md`
- `~/nr/nrouter-brain/nrouter-app/rules/17-virtual-keys.md`
- `~/nr/nrouter-brain/nrouter-app/rules/30-email-templates.md`
- `~/nr/nrouter-brain/nrouter-brand-marketing/rules/40-image-blog-standards.md`
- `~/nr/nrouter-brain/nrouter-infra-cicd/rules/08-database.md`
- `~/nr/nrouter-brain/nrouter-infra-cicd/rules/15-startup-health.md`
- `~/nr/nrouter-brain/nrouter-infra-cicd/rules/16-infrastructure.md`
- `~/nr/nrouter-brain/nrouter-manage-company/rules/19-soc2-new-feature-checklist.md`
- `~/nr/nrouter-brain/nrouter-rust-gateway/rules/00-gateway-rules.md`
- `~/nr/nrouter-brain/nrouter-rust-gateway/rules/01-provider-contract.md`

`00-permanent-rules.md` is the authority: it carries the full prose of all
the rules, the Rule→Skill map, and the enforcement map showing which rules
auto-block versus which rely on discipline. Start there if you only read one.

<!-- END GENERATED: permanent-rules-pointer -->
