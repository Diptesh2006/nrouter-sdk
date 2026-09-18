# Prompt: 100% Full-Coverage Use Case Specification Generator for nRouter App
# Target: Claude Code / Antigravity (agy) / ChatGPT
# Purpose: Produce a comprehensive, 100% full-coverage Use Case Specification Document to hand directly to a 3rd-Party QA & Test Automation vendor.
# Note: This prompt ONLY generates business use cases and user scenarios (flows, actors, happy paths, edge cases, invariants). It does NOT write low-level test cases, selectors, or automation scripts.

You are acting as the **Lead Product Architect & Principal Business Analyst** for nRouter (`https://nrouter.ai` / `https://app.nrouter.ai`).

Your mission is to analyze the entire `nrouter-app` codebase and generate an **exhaustive, production-grade Use Case Specification Document** covering 100% of all user flows across all 102 routes.

This document will be handed directly to an external **3rd-party QA & Test Automation agency**. The QA team will use these use cases as the authoritative specification from which they will design their manual test cases, test data, and automated Playwright / Selenium test suites.

---

## 0. Output Destination & Format

Write the completed document to:
`tests/scenarios/nrouter-app/USE-CASES-SPECIFICATION.md`  
*(Relative to `nrouter-sdk/`, or absolute path `/Users/gurukallam/nr/nrouter-brain/nrouter-sdk/tests/scenarios/nrouter-app/USE-CASES-SPECIFICATION.md`)*

The output must be pure markdown, cleanly organized into the 16 functional modules below, using professional UML / Cockburn Use Case standards.

---

## 1. Discovery Phase (Deriving Truth from Code)

Do NOT invent or assume features. Verify the real application surface by inspecting:

```bash
# 1. Inspect all 102 routes in the Next.js App Router
find nrouter-app/src/app -name "page.tsx" | sort

# 2. Inspect all user dialogs and modal forms
grep -rn "DialogContent\|Modal" nrouter-app/src/components/ --include="*.tsx" | cut -d: -f1 | sort -u

# 3. Inspect input validation schemas (Zod)
grep -rn "z\.object" nrouter-app/src/ --include="*.ts" --include="*.tsx" | cut -d: -f1 | sort -u

# 4. Inspect role authorization and permission checks
grep -rn "role\|permission\|owner\|admin\|viewer" nrouter-app/src/lib/auth/ --include="*.ts"
```

Every route discovered must be mapped to at least one primary use case.

---

## 2. Standard Use Case Schema

Every use case in the specification must follow this standard schema:

```markdown
### UC-[MODULE]-[NUMBER]: [Use Case Title]

- **Primary Actor**: [Owner | Org Admin | Member | Viewer | Unauthenticated User]
- **Secondary Actors / Systems**: [Supabase DB | Rust Gateway | Stripe | Cortex Sidecar | Model Provider]
- **User Goal / Objective**: [Brief description of what the user wants to accomplish]
- **Preconditions**: [System or user state required before the scenario begins]
- **Trigger**: [The user action or navigation event that starts the flow]

#### Main Success Scenario (Happy Path):
1. User performs [Action 1].
2. System responds with [System Response 1].
3. User enters [Input Data] and clicks [Action Button].
4. System validates inputs against business rules.
5. System commits changes to the database and updates active context.
6. System displays [Confirmation / UI State Change].

#### Extensions & Alternative Flows (Edge Cases & Negative Scenarios):
- **3a. [Invalid Input / Validation Error]**:
  1. System highlights invalid field with inline error message [Message].
  2. Action button remains disabled; state is preserved.
- **3b. [RBAC Permission Denial]**:
  1. If user is [Restricted Role], UI hides action controls or system returns HTTP 403 Forbidden.
- **4a. [System / Network / Gateway Exception]**:
  1. If backend service returns 4xx/5xx or timeout, system displays graceful error toast without crashing.

#### Business Rules & Invariants:
- [Rule Reference, e.g. Rule #5: Plaintext key displayed once only; Rule #3: Credit balance formula; Multi-tenancy isolation]

#### Post-conditions:
- [Expected state of the database, session, or UI upon successful completion]
```

---

## 3. Scope: 16 Functional Modules (100% Coverage of All 102 Routes)

You must generate detailed use cases across all 16 functional modules:

### Module 1: Authentication & Onboarding
- **Routes**: `/(auth)/login`, `signup`, `forgot-password`, `update-password`, `accept-invite`, `auth/email-challenge/confirm`, `consent`, `/account/verify-phone`, `/on-hold`.
- **Key Use Cases**:
  - Progressive password sign-in (magic link disclosure vs password view).
  - Cloudflare Turnstile bot verification challenge.
  - New organization and workspace setup during signup.
  - Password recovery workflow with signed tokens.
  - Organization invitation acceptance and role assignment.
  - Session resumption and cross-tab session synchronization.

### Module 2: Global App Shell & Navigation
- **Routes**: Shared chrome across all `/[org]/**` pages.
- **Key Use Cases**:
  - Multi-tenant organization switching with complete context reload and zero data leakage.
  - Command palette (`Cmd+K` / `Ctrl+K`) search and instant navigation.
  - Keyboard shortcuts modal (`?`).
  - Light mode / Dark mode toggling with contrast preservation.
  - Mobile viewport hamburger drawer navigation (390px).

### Module 3: Model Playground (`/[org]/playground`)
- **Key Use Cases**:
  - Running multi-provider inference with streaming Server-Sent Events (SSE).
  - Aborting an in-progress stream via the Stop button.
  - Multimodal image attachment and visual question answering.
  - Temperature, Top-P, and Max Output Tokens slider adjustments.
  - Custom Pasted Key mode (stored strictly in `sessionStorage`) vs Managed Org Key mode.
  - Generating and copying SDK code snippets (cURL, Python, Node.js).
  - Credit exhaustion warning banner display.

### Module 4: Virtual API Keys (`/[org]/keys`)
- **Key Use Cases**:
  - Generating a new virtual API key with model whitelisting, team scoping, and rate limits (RPM/TPM).
  - Viewing the plaintext key in the single-reveal modal (Rule #5: shown once, never again).
  - Viewing virtual keys in the management table (renders `sk-...last4` only).
  - Revoking an active virtual key with confirmation.
  - Rotating an active virtual key (creates new hash, archives old key).
  - Viewer role RBAC restriction (Generate and Revoke buttons hidden; API returns 403).

### Module 5: Model Catalog & Pricing (`/[org]/models`)
- **Key Use Cases**:
  - Browsing supported models across OpenAI, Anthropic, Bedrock, Mistral, Google, etc.
  - Filtering models by modality (Chat, Vision, Audio, Embeddings).
  - Reviewing flat list pricing per 1M prompt/completion tokens (zero markup - Rule #28).
  - Toggling model availability on/off for the organization.
  - Inspecting model context window sizes and technical specs in the details drawer.

### Module 6: Router Settings & Fallback Chains (`/[org]/router-settings`)
- **Key Use Cases**:
  - Configuring automatic provider fallback chains (Primary -> Secondary -> Tertiary).
  - Selecting intelligent routing strategies (Lowest Latency vs Lowest Cost vs Round Robin).
  - Customizing client timeout thresholds and retry budgets.

### Module 7: Guardrails & Cortex Moderation Suite (`/[org]/guardrails/**`)
- **Routes**: `guardrails`, `key-assignments`, `keys`, `logs`, `teams`.
- **Key Use Cases**:
  - Configuring content moderation thresholds (toxicity, hate speech, NSFW, PII masking).
  - Enabling prompt injection defense scoring.
  - Testing prompts in the live guardrail sandbox.
  - Binding specific guardrail policies to individual virtual keys or teams.
  - Inspecting guardrail violation logs and redaction reports.

### Module 8: Budgets & Alerting Suite (`/[org]/budgets`, `/[org]/alerts/**`)
- **Routes**: `budgets`, `alerts`, `alerts/channels`.
- **Key Use Cases**:
  - Setting monthly organization budget ceilings ($ amount).
  - Setting granular team-level and key-level spending limits.
  - Configuring alert notification thresholds (50%, 80%, 100%).
  - Adding notification channels (Email recipients and Slack/Discord Webhooks).
  - Enforcing hard inference stops (HTTP 402) vs soft email alerts.

### Module 9: Observability, Logs & Callbacks (`/[org]/logs`, `/[org]/log-settings/**`)
- **Routes**: `logs`, `log-settings`, `log-settings/callbacks`, `performance`, `usage`.
- **Key Use Cases**:
  - Inspecting live inference spend logs with real-time token and cost attribution.
  - Filtering logs by model, virtual key, date range, and HTTP status code.
  - Opening the Request Debug & Trace Canvas waterfall (WAF -> Cortex -> Reserve -> Provider -> Settle).
  - Verifying privacy mode (zero prompt/completion payload leak in logs).
  - Configuring log delivery webhooks.
  - Exporting filtered log records to CSV.

### Module 10: FinOps & Billing (`/[org]/billing`, `/[org]/plan-usage`)
- **Key Use Cases**:
  - Inspecting real-time Credit Balance (`Available = Total - Reserved Holds`).
  - Initiating credit top-ups via Stripe Checkout modal.
  - Canceling Stripe Checkout safely without charging card.
  - Configuring auto-recharge settings upon low balance.
  - Downloading PDF invoices and VAT receipts.
  - Reviewing localized FX quotes (USD, EUR, GBP, INR).
  - Monitoring subscription tier allowance usage.

### Module 11: Team Management & RBAC (`/[org]/people/**`)
- **Routes**: `people`, `members`, `teams`, `teams/[teamId]`.
- **Key Use Cases**:
  - Inviting new members via email with role selection (Owner, Org Admin, Member, Viewer).
  - Resending or canceling pending invitations.
  - Modifying existing member roles.
  - Removing a member from the organization.
  - Creating functional teams and assigning members and team-scoped virtual keys.
  - Enforcing the complete 4-tier RBAC matrix across all actions.

### Module 12: Prompts Library & A/B Testing (`/[org]/prompts/**`)
- **Routes**: `prompts`, `[promptId]`, `[promptId]/diff`, `ab-tests`, `history`, `keys`, `logs`, `recommendations`, `teams`.
- **Key Use Cases**:
  - Creating and saving reusable prompt templates with variable placeholders (`{{variable}}`).
  - Versioning prompts and comparing revisions in the side-by-side visual diff viewer.
  - Forking a prompt template directly into the Playground for testing.
  - Creating an A/B testing experiment to split inference traffic between two prompt variants.
  - Reviewing AI prompt optimization recommendations.

### Module 13: Advanced Analytics Suite (`/[org]/advanced/**`)
- **Routes**: `advanced`, `agents`, `api-consumers`, `benchmark`, `budgets`, `compare`, `cost-vs-usage`, `cost`, `errors`, `explore`, `keys`, `usage`.
- **Key Use Cases**:
  - Analyzing cost vs token usage trends over time with dual-axis charts.
  - Comparing model performance benchmarks (time-to-first-token, latency, throughput).
  - Analyzing error distributions (4xx client errors, 5xx provider outages, 429 rate limits).
  - Tracking API client user-agents, SDK versions, and consumer fingerprints.

### Module 14: Organization Settings & Security (`/[org]/settings/**`)
- **Routes**: `settings/(general)`, `branding`, `danger-zone`, `localization`, `privacy`, `security`, `audit`.
- **Key Use Cases**:
  - Updating organization profile information (verifying slug immutability).
  - Reviewing brand assets and logo preview (Rule #17 frozen branding).
  - Configuring IP allowlists and session timeouts.
  - Danger Zone: deleting an organization (verifying slug confirmation barrier).
  - Reviewing the immutable organization audit log.

### Module 15: Built-in AI Productivity Tools (`/[org]/tools/**`)
- **Routes**: `customer-support`, `image-prompt`, `social-media`, `video-prompt`.
- **Key Use Cases**:
  - Interacting with the Customer Support AI assistant simulator.
  - Generating optimized image prompts, social media copy, and video scripts.

### Module 16: Account Security & Super Admin Isolation
- **Routes**: `/account`, `/account/security/2fa`, `/account/verify-phone`, `/super-admin/**`.
- **Key Use Cases**:
  - Configuring two-factor authentication (TOTP QR code, validation token, backup codes).
  - Phone number verification workflow.
  - Verifying that regular customer accounts navigating to `/super-admin` are strictly blocked (HTTP 403 / redirect).

---

## 4. Execution Instructions

When executing this prompt:
1. Conduct the code discovery scan on `nrouter-app`.
2. Generate `tests/scenarios/nrouter-app/USE-CASES-SPECIFICATION.md` containing at least **75 to 100+ complete, detailed use cases** covering all 16 modules.
3. Strictly adhere to the standard use case schema (Actors, Preconditions, Trigger, Main Scenario, Extensions/Edge Cases, Business Rules, Post-conditions).
4. Do NOT include test scripts, code, or Playwright/Selenium selectors. Keep the document focused 100% on business and user workflows for the 3rd-party QA vendor.
