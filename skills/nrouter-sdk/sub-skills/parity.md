# Sub-skill: Cross-SDK Parity & Open-Source Standards

Skill `nrouter-sdk`, sub-skill `parity` (merged from the former standalone `nrouter-sdk-parity` skill, v1.1.0).
Open it when ANY SDK wire, endpoint, demo, example, validation playbook, error code, header, or
README is modified or added. The SDK list, the spec-is-canonical rule and the conformance gate are
stated once in the router (`../SKILL.md`, "Shared facts").

This sub-skill enforces that all ten nRouter SDKs adhere to one synchronized contract, unified versioning, and open-source documentation excellence.

**When one technology changes, the entire ecosystem stays aligned.**

---

## ⛔ The Invariants

1. **Rule #14 — The Spec is Canonical**:
   `spec/nrouter-sdk-spec.json` is the sole source of truth derived from the gateway. When an SDK and the spec disagree, the SDK is wrong. A new endpoint, header, error mapping **or request-body option** is never single-language.
   ⚠️ **`spec.extra_body_fields` is a propagation surface too**, and the one that was missed: it is the CLOSED set of `nrouter_*` keys the gateway lifts off a body, and an unknown `nrouter_*` key is refused 400 rather than forwarded. A field an SDK does not model is unreachable for its callers, not merely unsugared. Shape and refusal codes are in the router (`../SKILL.md`, "Three wire surfaces").
2. **One Coordinated Release Version**:
   All ten SDKs share a single coordinated version. It lives in `spec.version` — read it, never retype it (`python3 -c "import json;print(json.load(open('spec/nrouter-sdk-spec.json'))['version'])"`). A breaking change in any SDK advances the coordinated version for all ten. Manifests (`package.json`, `pyproject.toml`, `pom.xml`, `Cargo.toml`, `VERSION`, `pubspec.yaml`, `DESCRIPTION`, etc.) must never drift.
3. **Demo & Example Parity (`sdks/<tech>/demo/`)**:
   Every SDK owns a `demo/` directory containing runnable examples and an instructional `README.md`. When a new usage pattern (such as token streaming, prompt templates, tool calling, media handling, or spend tracking) is added or modified in one SDK, equivalent runnable demonstrations must be updated across all SDK demo folders.
4. **Validation Playbook Parity (`sdks/<tech>/docs/validation-playbook.md`)**:
   Every SDK maintains an authoritative 18-step validation playbook in `sdks/<tech>/docs/validation-playbook.md` (or `doc/` for Dart) aligned with `docs/validation-playbook-template.md`. Any update to validation steps, error matrices, cache sequences, or dashboard reconciliation procedures must be applied across all ten playbooks.
5. **README & Open-Source Documentation Standards (`sdks/<tech>/README.md`)**:
   Every SDK README must adhere to open-source standards:
   - Clear package title, registry status, and badges.
   - Installation instructions showing the active release version from `spec.version`.
   - Quickstart showing client initialization and chat completion.
   - Named endpoint / feature list.
   - Direct link to the SDK's [`demo/`](demo/) directory.
   - Direct link to the SDK's [`validation-playbook.md`](docs/validation-playbook.md).
   - The required gateway routing invariant (`## How guardrails, budgets and routing work`).
   - License (MIT) and Contributing / Issue tracker links.

---

## The Synchronization Matrix

| Area | Master Source of Truth | Target Locations | Verification Command |
|---|---|---|---|
| **Wire & Contract** | `spec/nrouter-sdk-spec.json` | `sdks/*/` source implementations | `python3 conformance/check_conformance.py` |
| **Request-body options** | `spec.extra_body_fields` | every SDK's typed option builder, or its recorded `NO_OPTION_BUILDER` reason | `python3 conformance/check_conformance.py` (`check_option_builders`) |
| **The live wire itself** | the running gateway | nothing in this repo — it is the oracle | `python3 scripts/curl_health_checks/run_all.py --route <route> --model <model>` |
| **Feature Surface** | `conformance/feature_manifest.json` | Public client methods across all SDKs | `python3 conformance/check_features.py` |
| **Demo Implementations** | `sdks/<tech>/demo/` | All 10 `sdks/<tech>/demo/` folders | `python3 scripts/check_sdk_parity.py` |
| **Validation Playbooks** | `docs/validation-playbook-template.md` | All 10 `sdks/*/docs/validation-playbook.md` | `python3 scripts/check_sdk_parity.py` |
| **Version Alignment** | `spec/nrouter-sdk-spec.json` (`version`) | All 10 SDK manifests, lockfiles, and docs | `python3 scripts/check_sdk_parity.py` |
| **README & Open-Source Standards** | Open-source standard structure | All 10 `sdks/*/README.md` and root `README.md` | `python3 scripts/check_sdk_parity.py` |

---

## Cross-Technology Propagation Protocol (When One SDK Changes)

Whenever a feature, wire, helper, or test pattern is added or updated in ONE technology:

1. **Spec & Feature Manifest**:
   - If introducing a new route, error code, header, header value, or `nrouter_*` body field, update `spec/nrouter-sdk-spec.json` first — it is what every gate reads.
   - If adding a shared capability (e.g. video job polling, response cache header parsing, cancellation), add its hint to `conformance/feature_manifest.json`.
   - A new `nrouter_*` body field must land in every typed option builder (`OPTION_BUILDERS`) in the same slice, or the SDKs it skipped must be moved into `NO_OPTION_BUILDER` with a reason naming the closest file. **The reason is re-validated**: the gate fails an entry the moment that SDK grows a complete builder, so the excuse cannot outlive the follow-up that closes it.
2. **Implement Across All Ten SDKs**:
   - Implement the feature natively in each SDK following idiomatic conventions (e.g., coroutines in Kotlin, async/await in Swift/Rust/JS/Python, goroutines/channels in Go).
   - If an SDK delegates (e.g. Android delegates to Kotlin core, Java delegates to `openai-java`), verify and document the delegation seam.
3. **Synchronize Demos**:
   - Add/update runnable examples in `sdks/<tech>/demo/`.
   - Ensure demo `README.md` contains exact compilation and execution commands.
4. **Synchronize Validation Playbooks**:
   - Update `docs/validation-playbook-template.md` if the verification procedure evolved.
   - Update the 18-step playbook in each of the 10 SDKs.
5. **Synchronize READMEs & Documentation**:
   - Ensure `sdks/<tech>/README.md` references the new capability, links to `demo/`, links to `validation-playbook.md`, and shows the correct version.
6. **Run Full Verification Gate**:
   ```bash
   # 1. Parity checker (manifests, demos, playbooks, READMEs, features, conformance)
   python3 scripts/check_sdk_parity.py --self-test
   python3 scripts/check_sdk_parity.py

   # 2. Conformance and subgates
   python3 conformance/check_conformance.py --self-test
   python3 conformance/check_conformance.py

   # 3. Unit and release version tests
   python3 -m pytest tests/test_release_versions.py tests/test_sdk_contract.py
   ```

---

## ⛔ Refuses

The `parity` sub-skill strictly refuses:
- Adding a feature, route, header, or `nrouter_*` body option to one SDK without updating the remaining nine SDKs and `spec/nrouter-sdk-spec.json`.
- Recording an SDK in `NO_OPTION_BUILDER` without naming the closest file and the reason, or leaving a stale entry in place once that SDK maps every spec field.
- Creating or editing an SDK demo without maintaining `sdks/<tech>/demo/` and its `README.md`.
- Modifying a validation step in one playbook without updating `docs/validation-playbook-template.md` and all sibling playbooks.
- Bumping the version of one SDK manifest independently of the other nine.
- Leaving any SDK README without links to its `demo/` and `validation-playbook.md`.
- Stating obsolete publishing states (e.g., claiming `publish = false` or `publish_to: none` for published crates/packages).
- Committing API keys, credentials, or `.env` files into any demo or playbook (Rule #18).
