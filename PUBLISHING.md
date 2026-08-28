# Publishing the SDKs

One workflow per published language, all merge-triggered:

| package | workflow | version lives in |
|---|---|---|
| `@nrouter_ai/sdk` (npm) | `.github/workflows/publish-npm.yml` | `sdks/js/package.json` |
| `nrouter-sdk` (PyPI) | `.github/workflows/publish-pypi.yml` | `sdks/python/pyproject.toml` |
| `ai.nrouter:nrouter-sdk` (Maven Central) | `.github/workflows/publish-maven.yml` | `sdks/java/pom.xml` |

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
| `NPM_TOKEN` | npm token with write access to `@nrouter_ai/sdk` — **on the way out**, see below |
| `CENTRAL_USERNAME` | Sonatype Central Portal token username |
| `CENTRAL_PASSWORD` | Sonatype Central Portal token password |
| `GPG_PRIVATE_KEY` | ASCII-armored private signing key |
| `MAVEN_GPG_PASSPHRASE` | signing key passphrase |

### npm: the token is temporary, and it has a hard end date

The npm lane is mid-migration to **trusted publishing (OIDC)**, which uses no
secret at all. Everything on the repository side is done — `publish-npm.yml`
declares `id-token: write` on the publish job and publishes with `--provenance`.

**The one remaining step is a human at npmjs.com**, because npm puts
trusted-publishing configuration behind an interactive 2FA challenge that no
automation can satisfy:

> `@nrouter_ai/sdk` > Settings > Trusted Publisher > GitHub Actions
> organization `nRouterAI`, repository `nrouter-sdk`,
> workflow filename `publish-npm.yml`, environment **empty**

Then delete the two `env:` lines under the Publish step and run
`gh secret delete NPM_TOKEN -R nRouterAI/nrouter-sdk`. **Both halves** — a token
left beside OIDC is a fallback npm prefers silently, so the run goes green
without ever proving OIDC works.

⚠️ **Do not create a granular access token for CI and expect it to publish.**
Measured 2026-08-28: a correctly scoped granular token authenticates, signs a
provenance statement, and then fails `EOTP` — npm requires an interactive 2FA
challenge on writes, and a runner has no authenticator. The deciding field is
`bypass_2fa`, readable per token at
`https://registry.npmjs.org/-/npm/v1/tokens`, and it is stamped at token
CREATION — flipping the account's 2FA mode afterwards does not rescue an
existing token. A Classic **Automation** token carries it true by construction.

The clock: npm withdraws direct publish from bypass-2FA tokens in
[January 2027](https://github.blog/changelog/2026-07-31-restricting-npm-bypass-2fa-granular-access-tokens/),
and the current token expires 2026-11-26.

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
