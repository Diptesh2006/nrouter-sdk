# CLAUDE.md — nrouter-sdk

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> 📍 `github.com/nRouterGateway/nrouter-sdk` (**public**).
> **The only PUBLIC repo in the workspace** — everything committed here is world-readable.
> Treat every file as published. Never commit internal keys, project IDs, or internal endpoints.
> `AGENTS.md`/`GEMINI.md` are symlinks to this file.

## What this repo is

1. **Ten client SDKs** under `sdks/` (js, python, java, kotlin, android, go, rust, swift, dart, r), all speaking one gateway wire contract (`api.nrouter.ai/v1/*`). Package names and versions live in each SDK's manifest — read them there, never from prose; the SDKs are not all on the same version.
2. **Agents** under `agents/`. The public zero-DB `@nrouter_ai/support-agent` is no longer one of them: it has its own public repository, `nRouterGateway/customer-support-agent`, and depends on `@nrouter_ai/sdk` from here.

## The One Rule: Canonical Specification (Rule #14)

**`spec/nrouter-sdk-spec.json` is the source of truth, derived from the gateway** — never the other way around: base URL, `NROUTER_API_KEY`, every `x-nr-*` header, the error envelope and error codes. When an SDK and the spec disagree, the SDK is wrong.

## Commands

```bash
python3 scripts/check_sdk_parity.py [--self-test]        # playbooks, manifests, READMEs agree
python3 conformance/check_conformance.py [--self-test]   # all ten agree with the spec
scripts/test-all.sh                                      # every SDK's own tests, one lane each
(cd sdks/js && npm ci && npm test)                       # one SDK; each sdks/<lang>/README.md has its command
```

## Traps & Invariants

- **Error format:** a refusal body is `{"error": {"type": "...", "message": "..."}}` plus an **optional** `"code"`, present only where the gateway can name a spec `errors` key. Model `code` as optional; classify on `code`, then `type`, then status, never on `message`. The exact code list is the spec's `error_envelope`.
- **Pricing:** `x-nr-request-cost` is absent when unpriced; rendering it as `0` falsely reports a free request (violates Rule #28).
- **Credentials:** Never print or serialize API keys in debug/logging output (all SDKs redact).
- **Publishing:** Managed from `nrouter-infra-cicd` (`/deploy-nrouter-sdk`, skill `deploy-nrouter-sdk`). In-repo notes in `PUBLISHING.md`.

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
- `~/nr/nrouter-brain/sdlc/rules/19-soc2-new-feature-checklist.md`
- `~/nr/nrouter-brain/sdlc/rules/20-tdd-and-fleet.md`
- `~/nr/nrouter-brain/nrouter-app/rules/02-multi-tenancy.md`
- `~/nr/nrouter-brain/nrouter-app/rules/03-credit-safety.md`
- `~/nr/nrouter-brain/nrouter-app/rules/05-frontend-standards.md`
- `~/nr/nrouter-brain/nrouter-app/rules/07-stripe-integration.md`
- `~/nr/nrouter-brain/nrouter-app/rules/11-api-routes.md`
- `~/nr/nrouter-brain/nrouter-app/rules/13-enterprise-features.md`
- `~/nr/nrouter-brain/nrouter-app/rules/17-virtual-keys.md`
- `~/nr/nrouter-brain/nrouter-app/rules/30-email-templates.md`
- `~/nr/nrouter-brain/nrouter-cortex/rules/00-cortex-rules.md`
- `~/nr/nrouter-brain/nrouter-frontend-ui/rules/40-image-blog-standards.md`
- `~/nr/nrouter-brain/nrouter-frontend-ui/rules/41-seo-geo-aeo-page-checklist.md`
- `~/nr/nrouter-brain/nrouter-infra-cicd/rules/08-database.md`
- `~/nr/nrouter-brain/nrouter-infra-cicd/rules/15-startup-health.md`
- `~/nr/nrouter-brain/nrouter-infra-cicd/rules/16-infrastructure.md`
- `~/nr/nrouter-brain/nrouter-rust-gateway/rules/00-gateway-rules.md`
- `~/nr/nrouter-brain/nrouter-rust-gateway/rules/01-provider-contract.md`

`00-permanent-rules.md` is the authority: it carries the full prose of all
the rules, the Rule→Skill map, and the enforcement map showing which rules
auto-block versus which rely on discipline. Start there if you only read one.

<!-- END GENERATED: permanent-rules-pointer -->
