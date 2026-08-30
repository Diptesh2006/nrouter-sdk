# Publishing the SDKs

One workflow per published language, all merge-triggered:

| package / target | registry | workflow | version lives in |
|---|---|---|---|
| `@nrouter_ai/sdk` (TypeScript / JS) | [npmjs.org](https://www.npmjs.com/package/@nrouter_ai/sdk) | `.github/workflows/publish-npm.yml` | `sdks/js/package.json` |
| `nrouter-sdk` (Python) | [pypi.org](https://pypi.org/project/nrouter-sdk/) | `.github/workflows/publish-pypi.yml` | `sdks/python/pyproject.toml` |
| `ai.nrouter:nrouter-sdk` (Java) | [Maven Central](https://central.sonatype.com/) | `.github/workflows/publish-maven.yml` | `sdks/java/pom.xml` |
| `ai.nrouter:nrouter-sdk-kotlin` (Kotlin) | [Maven Central / Sonatype](https://central.sonatype.com/) | `.github/workflows/publish-kotlin.yml` | `sdks/kotlin/build.gradle.kts` |
| `NRouter` (Swift) | [Swift Package Index](https://swiftpackageindex.com/) | `.github/workflows/publish-swift.yml` | `Package.swift` |
| `nrouter` (Rust) | [crates.io](https://crates.io/crates/nrouter) | `.github/workflows/publish-rust.yml` | `sdks/rust/Cargo.toml` |
| `github.com/nRouterAI/nrouter-sdk/sdks/go` (Go) | [proxy.golang.org](https://proxy.golang.org/) | `.github/workflows/publish-go.yml` | `sdks/go/go.mod` (tag `sdks/go/v*`) |
| `nrouter` (Dart) | [pub.dev](https://pub.dev/packages/nrouter) | `.github/workflows/publish-dart.yml` | `sdks/dart/pubspec.yaml` |
| `nrouter` (R) | [CRAN / R-universe](https://nrouterai.r-universe.dev) | `.github/workflows/publish-r.yml` | `sdks/r/DESCRIPTION` |

## To release

Bump the version, merge to `main`. That is the whole procedure.

```bash
$EDITOR sdks/js/package.json          # "version": "1.1.0"
$EDITOR sdks/python/pyproject.toml    # version = "2.1.1"
$EDITOR sdks/java/pom.xml             # <version>1.0.1</version>
# ...open a PR, get it merged...
```

The workflow then runs the tests and the cross-SDK conformance gate, and
publishes only if that version is not already on the registry.

**A merge that does not change the version publishes nothing.** That is what
makes merge-triggered safe: registry versions are immutable, so re-running on
every merge would otherwise fail constantly. The `already published?` step turns
the no-change case into a quiet green no-op instead.

## Secrets

| secret | purpose |
|---|---|
| `PYPI_API_TOKEN` | PyPI project token for `nrouter-sdk` |
| `CENTRAL_USERNAME` | Sonatype Central Portal token username |
| `CENTRAL_PASSWORD` | Sonatype Central Portal token password |
| `GPG_PRIVATE_KEY` | ASCII-armored private signing key |
| `MAVEN_GPG_PASSPHRASE` | signing key passphrase |

### npm needs NO secret — trusted publishing (OIDC)

DONE 2026-08-29. `@nrouter_ai/sdk` publishes with no credential: `publish-npm.yml`
declares `id-token: write` on its publish job, and npm exchanges a short-lived
runner-minted token for publish rights after matching this repository and this
workflow FILENAME against the trusted publisher registered on the package.
`NPM_TOKEN` has been deleted from the repository.

**Renaming `publish-npm.yml` breaks publishing** until the registration is
updated to match. That is the security property.

The registration itself lives at npmjs.com > `@nrouter_ai/sdk` > Settings >
Trusted Publisher > GitHub Actions — organization `nRouterAI`, repository
`nrouter-sdk`, workflow filename `publish-npm.yml`, environment **empty** (the
job declares none, and a name here would never match). Editing it requires an
interactive 2FA challenge, so no automation can do it.

Proof a release used this path: a provenance attestation on the published
version naming the workflow. Only an Actions run can produce one —
`npm audit signatures` verifies it, and 1.2.1 is the first version with it.

⚠️ **Do not re-create an NPM_TOKEN secret.** A token sitting beside OIDC is a
fallback npm prefers silently, so the pipeline would go green while proving
nothing — and npm withdraws direct publish from bypass-2FA granular tokens in
[January 2027](https://github.blog/changelog/2026-07-31-restricting-npm-bypass-2fa-granular-access-tokens/).
A granular token cannot publish from CI anyway without `bypass_2fa`, and one
WITH it can no longer perform account or package management: measured on
2026-08-28, such a token authenticated, signed provenance, then failed `EOTP`.

Maven token: central.sonatype.com -> account settings -> generate user token.
Use the generated token username and password, not your login password.

GPG key export for GitHub Actions:

```bash
gpg --armor --export-secret-keys <KEY_ID>
```

Add the full exported block as `GPG_PRIVATE_KEY`. Add the key passphrase as
`MAVEN_GPG_PASSPHRASE`. The public key must be uploaded to a supported keyserver
before Central can validate signatures.

## Things that bite

- **`--access public` is not optional** on a scoped npm package. Without it npm
  makes the package private and every install fails for everyone.
- **A publish command exiting 0 is registry acceptance, not proof that the
  registry is serving the artifact.** Workflows poll the registry afterwards; a
  green publish step alone is not proof.
- **Never publish a version older than the current latest.** Without an explicit
  dist-tag on npm, it moves the default pointer backwards and silently
  downgrades every fresh install. A deliberate npm backport goes out as
  `npm publish --access public --tag backport`.
- **A version cannot be taken back.** Registry versions are effectively
  immutable. Bump forward; never re-push the same version.
- **Maven Central may validate before it serves.** If the confirmation step
  times out, check Central before rerunning; the version may already be taken.

## Manual fallback

Only if Actions is unavailable. Same order the workflow uses: test, check,
publish, verify at the registry.

🛑 **npm has no manual fallback any more. Wait for Actions.**

A local `npm publish` cannot produce a provenance attestation — provenance is
minted from the GitHub OIDC token of the run that built the tarball, so there
is no flag that adds it from a laptop. Using this path would put an unattested
version into a line that SECURITY.md and the README both promise is attested
from 1.1.1 onward, and nothing about the published package would announce it:
the release looks identical until someone runs `npm audit signatures` and gets
a failure they will blame on the registry.

1.0.0 and 1.1.0 are the versions that went out this way, before CI held a
working credential. They cannot be fixed — provenance is not addable after the
fact. Keeping the count at two is the whole point of removing this step.

An npm release is never urgent enough to spend the guarantee. If Actions is
genuinely down for long enough to matter, say so to the operator and wait.

```bash
cd sdks/python && python -m pytest -q
python3 ../../conformance/check_conformance.py
python -m build && python -m twine check dist/*
python -m twine upload dist/*
curl -s -o /dev/null -w '%{http_code}\n' https://pypi.org/pypi/nrouter-sdk/2.2.0/json
```

```bash
cd sdks/java && mvn -B clean verify
python3 ../../conformance/check_conformance.py
mvn -B clean deploy -P release
curl -s -o /dev/null -w '%{http_code}\n' https://repo1.maven.org/maven2/ai/nrouter/nrouter-sdk/1.0.1/nrouter-sdk-1.0.1.pom
```
