# CLAUDE.md — nrouter-sdk

Public repo (`github.com/nRouterGateway/nrouter-sdk`). Never commit secrets or internal endpoints.
Skills: `nrouter-sdk`, `deploy` (`references/sdk.md`; `/deploy <plane> sdk`).

## Architecture & Contract (Rule #14)
- **Ten client SDKs (`sdks/`):** speak one wire contract (`api.nrouter.ai/v1/*`).
- **Dev testing:** `https://api.dev.nrouter.ai/v1/*` with `Authorization: Bearer sk-nrouter-...` (`auth_basic` off).
- **Canonical spec:** `spec/nrouter-sdk-spec.json` is authoritative for routes, `x-nr-*` headers, and errors.
- **Invariants:** `x-nr-request-cost` absent when unpriced (Rule #28) or when funded by customer key (`x-nr-funding-source: byok`); keys redacted in logs; coordinated version releases (truth: `spec/nrouter-sdk-spec.json`).
- **Branching (Rule #20):** develop on `development`; `main` only via PR.
- **Commands:** `python3 conformance/check_conformance.py` · `python3 scripts/check_sdk_parity.py` · `scripts/test-all.sh`

<!-- BEGIN GENERATED: permanent-rules-pointer (bootstrap.sh) -->
## The Permanent Rules — for Codex, Gemini CLI and Antigravity
Read in order before editing (`00-permanent-rules.md` is authority for all the rules):
- `~/nr/nrouter-brain/sdlc/rules/00-permanent-rules.md`
- `~/nr/nrouter-brain/sdlc/rules/00-workspace-repos.md`
- `~/nr/nrouter-brain/sdlc/rules/10-testing.md`
- `~/nr/nrouter-brain/sdlc/rules/19-soc2-new-feature-checklist.md`
- `~/nr/nrouter-brain/sdlc/rules/20-tdd-and-fleet.md`
- `~/nr/nrouter-brain/sdlc/rules/21-owner-feature-review.md`
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
- `~/nr/nrouter-brain/nrouter-frontend-ui/rules/42-homepage-design.md`
- `~/nr/nrouter-brain/nrouter-infra-cicd/rules/08-database.md`
- `~/nr/nrouter-brain/nrouter-infra-cicd/rules/15-startup-health.md`
- `~/nr/nrouter-brain/nrouter-infra-cicd/rules/16-infrastructure.md`
- `~/nr/nrouter-brain/nrouter-rust-gateway/rules/00-gateway-rules.md`
- `~/nr/nrouter-brain/nrouter-rust-gateway/rules/01-provider-contract.md`
<!-- END GENERATED: permanent-rules-pointer -->
