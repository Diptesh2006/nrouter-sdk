# Publishing the SDKs

All ten SDKs use one coordinated release version. The canonical value is
`spec/nrouter-sdk-spec.json`; `conformance/check_conformance.py` refuses any
manifest, lockfile, Swift/Go release marker, Android Kotlin dependency, or Go
major module path that differs from it.

Three supported registry packages publish from merge-triggered workflows:

| package / target | registry | workflow | version lives in |
|---|---|---|---|
| `@nrouter_ai/sdk` (TypeScript / JS) | [npmjs.org](https://www.npmjs.com/package/@nrouter_ai/sdk) | `.github/workflows/publish-npm.yml` | `sdks/js/package.json` |
| `nrouter-sdk` (Python) | [pypi.org](https://pypi.org/project/nrouter-sdk/) | `.github/workflows/publish-pypi.yml` | `sdks/python/pyproject.toml` |
| `ai.nrouter:nrouter-sdk` (Java) | [Maven Central](https://central.sonatype.com/) | `.github/workflows/publish-maven.yml` | `sdks/java/pom.xml` |

The other seven are **public previews, not supported packages**. Six of them
are nevertheless reachable from a real registry — a preview is a support scope,
not a distribution method, and calling these "source checkout" sends a reader
looking for a git URL when `cargo add` already works.

Versions below were read FROM each registry on 2026-09-03. Re-derive them with
the block under [To verify what a registry serves](#to-verify-what-a-registry-serves)
rather than trusting this table; the README carries the same values for the
install snippets.

| target | distribution | serves today | can this pipeline advance it? |
|---|---|---|---|
| Kotlin | Maven Central `ai.nrouter:nrouter-sdk-kotlin` ([central.sonatype.com](https://central.sonatype.com/artifact/ai.nrouter/nrouter-sdk-kotlin)) | `2.1.0` | **No — frozen.** `publish-kotlin.yml` builds and `publishToMavenLocal` only |
| Android | Maven Central `ai.nrouter:nrouter-sdk-android` ([central.sonatype.com](https://central.sonatype.com/artifact/ai.nrouter/nrouter-sdk-android)) | `2.1.0` | **No — frozen.** `publish-android.yml` builds and `publishToMavenLocal` only |
| Rust | crates.io `nrouter` ([crates.io/crates/nrouter](https://crates.io/crates/nrouter)) | `2.1.0` | **No — frozen.** `Cargo.toml` declares `publish = false` |
| Dart / Flutter | pub.dev `nrouter` ([pub.dev/packages/nrouter](https://pub.dev/packages/nrouter)) | `2.1.1` | **No — frozen.** `pubspec.yaml` declares `publish_to: none` |
| R | [R-universe](https://nrouterai.r-universe.dev/nrouter) | `3.0.0` | Yes — R-universe rebuilds from `main` |
| Swift | bare SemVer git tag, resolved by SwiftPM | `3.0.0` | Yes — tag the release commit |
| Go | `sdks/go/v*` git tag, resolved by `proxy.golang.org` | `v3.0.0` | Yes — tag the release commit |

🛑 **The four frozen rows are a DELIBERATE decision, not a broken pipeline, and
the freeze is test-enforced.** `tests/test_release_versions.py::test_sdk_version_3_source_only_workflows_cannot_publish`
asserts that neither Maven workflow reads a `secrets.` value, that neither Gradle
build carries a `signing {}` block, that Rust keeps `publish = false` and that
Dart keeps `publish_to: none`. Re-arming any of those four turns that test RED,
which is the point: a preview must not acquire release credentials by accident.

The consequence to state plainly to a user: **those four registry artifacts are
stuck at the version above and will not follow the source version.** That is why
the README pins its install snippets to what each registry actually serves
instead of to `3.0.0`. Advancing one is a scoped decision that moves the SDK out
of preview — bump the support scope, the test, and the workflow together, or not
at all.

## To release

Bump the canonical version and every manifest together, then merge to `main`.
The shared gate makes a partial bump impossible. After all hosted workflows are
green, create the Swift and Go tags from that exact commit.

```bash
$EDITOR spec/nrouter-sdk-spec.json    # "version": "3.0.0"
$EDITOR sdks/js/package.json          # "version": "3.0.0"
$EDITOR sdks/python/pyproject.toml    # version = "3.0.0"
$EDITOR sdks/java/pom.xml             # <version>3.0.0</version>
# ...open a PR, get it merged...
```

The supported-package workflows run tests and conformance, then publish only if
that version is not already on their registry. Preview workflows stop after
build, package, and conformance verification.

**A merge that does not change the version publishes nothing.** That is what
makes merge-triggered safe: registry versions are immutable, so re-running on
every merge would otherwise fail constantly. The `already published?` step turns
the no-change case into a quiet green no-op instead.

## To verify what a registry serves

Ask each registry what it SERVES, not whether a page exists. A 200 on a project
page proves the name is taken, not that the version you expect is downloadable.

```bash
curl -s https://pypi.org/pypi/nrouter-sdk/json | python3 -c 'import sys,json;print("pypi",json.load(sys.stdin)["info"]["version"])'
curl -s https://registry.npmjs.org/@nrouter_ai%2Fsdk | python3 -c 'import sys,json;print("npm",json.load(sys.stdin)["dist-tags"]["latest"])'

# Maven Central: use repo1 metadata, NOT search.maven.org — its solr index lags.
for a in nrouter-sdk nrouter-sdk-kotlin nrouter-sdk-android; do
  echo -n "maven $a "
  curl -s "https://repo1.maven.org/maven2/ai/nrouter/$a/maven-metadata.xml" | grep -o '<release>[^<]*'
done

curl -s -H 'User-Agent: nrouter-check' https://crates.io/api/v1/crates/nrouter | python3 -c 'import sys,json;print("crates.io",json.load(sys.stdin)["crate"]["max_version"])'
curl -s https://pub.dev/api/packages/nrouter | python3 -c 'import sys,json;print("pub.dev",json.load(sys.stdin)["latest"]["version"])'
curl -s https://proxy.golang.org/github.com/n!router!a!i/nrouter-sdk/sdks/go/v2/@latest
curl -s https://nrouterai.r-universe.dev/src/contrib/PACKAGES | grep -A1 '^Package: nrouter$'
```

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
curl -s -o /dev/null -w '%{http_code}\n' https://pypi.org/pypi/nrouter-sdk/3.0.0/json
```

```bash
cd sdks/java && mvn -B clean verify
python3 ../../conformance/check_conformance.py
mvn -B clean deploy -P release
curl -s -o /dev/null -w '%{http_code}\n' https://repo1.maven.org/maven2/ai/nrouter/nrouter-sdk/3.0.0/nrouter-sdk-3.0.0.pom
```
