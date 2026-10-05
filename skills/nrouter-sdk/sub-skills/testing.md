# Sub-skill: Testing the nRouter SDKs

Skill `nrouter-sdk`, sub-skill `testing` (merged from the former standalone `nrouter-sdk-testing` skill,
v1.0.0). Open it when adding, changing, running, or auditing tests in any of the ten nRouter SDKs —
the per-language runner commands, the offline-by-default contract, the billed live-probe gate, the
in-process fake transport per ecosystem, and what a new wire must be covered by before it ships.

Ten SDKs on one gateway contract (the list, and how to derive it, is in the router `../SKILL.md`).
This sub-skill is how you run them, what you must cover, and the one invariant that makes the suite
usable in automation.

## THE INVARIANT: the default suite is OFFLINE, and stays that way

**Every default test command in this repo runs with no network, no API key, no gateway and no
database.** That is not an accident and it is not a nice-to-have — it is what lets any SDK's suite
run in a sandbox, in parallel, on a fresh checkout, with nothing provisioned.

The mechanism is one convention, applied identically in all ten SDKs: each ships exactly one
billed acceptance probe, always named `Live*` / `test_live.py` / `test-live.R`, and it is gated on
`NROUTER_LIVE=1` **using that language's native skip primitive** — never an early `return`, which
reports a pass for a test that never ran.

| SDK | how the live probe is gated |
|---|---|
| js | a `skip` const read from `process.env.NROUTER_LIVE` |
| python | `pytest.mark.skipif` module-level `pytestmark` |
| java | `@EnabledIfEnvironmentVariable(named="NROUTER_LIVE", matches="1")` |
| go | `t.Skip(...)` on the env check |
| rust | `#[ignore]` on every test; needs `--ignored` to run at all |
| kotlin | `@EnabledIfEnvironmentVariable` |
| android | `assumeTrue(...)` — JUnit reports skipped, never failed |
| swift | `throw XCTSkip(...)` |
| dart | the `test(..., skip: ...)` argument |
| r | `skip_if(...)` |

**Adding a test that needs a key, a socket or a gateway to PASS breaks this property.** If you need
one, it belongs behind the same `NROUTER_LIVE` gate, with the same native skip. Verify your gate by
running the suite with the variable unset and confirming your test reports **skipped**, not passed.

⚠️ **A live probe spends real credit against a real key.** Never wire one into a default command, a
CI job, or a pre-commit path.

## Runner commands — derive from the manifest, these are the entry points

Run from the SDK's own directory unless noted.

| SDK | command | tests live in |
|---|---|---|
| js | `npm test` (builds first, then the smoke + package-entry entrypoints) | `test/*.test.ts` |
| python | `pip install -e ".[dev]"` then `pytest` | `tests/test_*.py` |
| java | `mvn test` | `src/test/java/ai/nrouter/sdk/` |
| go | `go test ./...` | `*_test.go` beside source |
| rust | `cargo test` | `tests/*.rs` + inline `#[cfg(test)]` |
| kotlin | `./gradlew test` | `src/test/kotlin/ai/nrouter/sdk/` |
| android | `./gradlew test` (JVM unit tests, Robolectric-backed) | `src/test/kotlin/ai/nrouter/sdk/android/` |
| swift | `swift test` — **run in BOTH the repo root and `sdks/swift/`**, two manifests ship the same target | `Tests/NRouterTests/` |
| dart | `dart pub get && dart test` | `test/*_test.dart` |
| r | `R CMD build r && R CMD check nrouter_*.tar.gz --as-cran --no-manual`, from `sdks/` | `tests/testthat/` |

⚠️ **R: a green `test_dir()` or `devtools::test()` is NOT the signal.** `R CMD check` installs the
package first and then runs the suite; only that path exercises what a user gets.

⚠️ **JS: `npm test` builds first.** A stale `dist/` is a real source of "passes locally, fails in
CI" — never run the test entrypoints directly and call it green.

## The conformance gate — the only cross-SDK check, and it needs nothing

What the gate enforces, how to run it (`--self-test` first), why it needs only Python 3, and what
it deliberately does NOT catch are stated once in the router (`../SKILL.md`, "Shared facts → The
conformance gate"). The short version for a test author: it proves a spec constant is *referenced*,
never that it is used *correctly*, so it never stands in for a test in the SDK's own suite.

## The curl proof harness — the live oracle, and it is not part of the suite

`scripts/curl_health_checks/` asks the gateway in raw `curl`. How to run it, its flags, where the
key comes from and why `--route` matters are in the router (`../SKILL.md`, "Shared facts → The curl
proof harness"). Two things a test author must hold:

1. **It is NEVER wired into a default test command.** It needs a key and a network, so it lives
   under the same discipline as the `NROUTER_LIVE` probe: run it deliberately, never in CI's default
   path, never in a pre-commit hook. Its `--self-test` is the offline half and needs nothing.
2. **`NOT-CONFIGURED` and `NOT-EVALUATED` are not passes.** A run carrying either is PARTIAL for that
   property. Reading a yellow row as green is the exact failure the four-result vocabulary exists to
   prevent — the same reason a live probe uses a native skip primitive instead of an early `return`.

## Fakes: ecosystem-native and in-process, never a shared library

There is no cross-language fixture layer, on purpose — each SDK uses what its ecosystem already
has, so a contributor reads one familiar idiom instead of a bespoke one.

`js` stubs `globalThis.fetch` · `python` uses `httpx.MockTransport` (plus a threaded local server
for media) · `java` uses `com.sun.net.httpserver.HttpServer`, **not** MockWebServer · `go` uses
`httptest.NewServer` · `kotlin`/`android` use OkHttp `mockwebserver` · `swift` intercepts
`URLProtocol` · `dart` uses `MockClient` · `r` uses `webfakes` · `rust` asserts against source-level
constants.

All of these bind to loopback or intercept in-process. **None reaches the network, and none may
start to.**

⚠️ **R's `webfakes` is a `Suggests`, not an `Imports`.** Every test using it must self-guard with
`skip_if_not_installed("webfakes")` **and** the availability probe — a machine without the package
skips cleanly rather than failing.

## What a change must be covered by

**A new wire or route** — the native helper on every SDK that owns it (or a declared delegation
seam), plus a contract test asserting method, path and headers, plus the conformance route cell.

**An error-mapping change** — a test per affected status code proving the mapped class, in the
SDKs that map it. Conformance sees only that the code exists somewhere.

**A header change** — assert the header is SENT or PARSED into the right field. Conformance only
proves the string appears. For a header with a value enum — `x-nr-guardrails` above all — assert the
tokens are matched EXACTLY and case-sensitively, and that an unrecognised token stays unknown rather
than being rounded to the nearest one.

**A new `nrouter_*` body field** — assert the typed option actually reaches the serialized body under
its spec name (an option that builds nothing is unreachable, and conformance only proves the name
appears in the builder), and assert the refusal it can earn maps to the right class —
`nrouter_fallbacks` and `nrouter_guardrails` are the two most recently added, each with its own 400
(router, "Three wire surfaces").

**A timeout, retry or cancellation change** — a behavioural test with a fake that actually delays,
aborts or fails. **A client-side retry double-bills a customer** (router, "Shared facts → The client
retries nothing on a billed path"), so any change there — above all in the two vendor-client-based
SDKs — needs a test proving the zero-retry pin holds.

**Never** test generated code, a vendor client's internals, or formatting.

## Density beats file count

Four SDKs carry only two test files each — one large `Contract*` suite of 44–49 test functions, plus
the live probe. That is not thin coverage, and "add more files" is not the fix. Judge a suite by
which behaviours it pins, and prove a new test bites by breaking the code on purpose and watching
it go red before you trust it.

## Publishing reality — three of ten

Only `js` (npm, OIDC trusted publishing), `python` (PyPI) and `java` (Maven Central, GPG-signed)
reach an immutable public registry. The rest build, test and verify in CI without uploading: Go and
Swift resolve from git tags, R indexes automatically, and Kotlin, Android, Rust and Dart are
verify-only. **A registry publish is irreversible** — the version gates that refuse an already
published version exist for that reason and are never to be worked around.
