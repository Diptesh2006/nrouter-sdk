# Publishing `@nrouter_ai/sdk` to npm

The published name is **`@nrouter_ai/sdk`**, scope `@nrouter_ai`, maintainer
`nrouter_ai <support@nrouter.ai>`. `1.0.0` is live; this work ships `1.1.0`.

Verify that rather than trusting this line — registry status is a fact:

```bash
npm view @nrouter_ai/sdk version       # 1.0.0
npm view @nrouter_ai/sdk maintainers   # nrouter_ai <support@nrouter.ai>
```

## The trigger is a TAG, not a merge

`.github/workflows/publish-js.yml` fires on a `sdk-js-v*` tag. It does **not**
fire on a merge to `main`, and that is deliberate.

**npm versions are immutable.** Once `@nrouter_ai/sdk@1.1.0` exists it can never
be replaced — only superseded by `1.1.1`. There is a 72-hour unpublish window,
but it is a fire-escape, not a release process: using it breaks every consumer
who already installed, and npm blocks re-using the number afterwards.

Publish-on-merge makes every merge a permanent, world-visible release. A
half-finished refactor, a typo in an exported symbol, an unintended dependency
bump — each becomes a version some consumer's lockfile pins forever. So:

| event | what happens | reversible? |
|---|---|---|
| merge to `main` | `ci.yml` runs every gate | yes — push another commit |
| push `sdk-js-v*` | `publish-js.yml` publishes | **no** |

The tag is the maintainer saying "this exact tree is a release". A merge button
cannot express that.

## Release — the whole thing a maintainer types

```bash
# 1. Bump the version. It lives in package.json and nowhere else.
$EDITOR sdks/js/package.json          # "version": "1.1.0"
git commit -m "js sdk 1.1.0" sdks/js/package.json
git push origin main                  # SSH remote; HTTPS git fails here

# 2. Tag that commit and push the tag. This is the release.
git tag -s sdk-js-v1.1.0 -m "js sdk 1.1.0"
git push origin sdk-js-v1.1.0
```

Prereleases are deliberately **not** supported by the tag trigger: the workflow
requires strict `MAJOR.MINOR.PATCH`, so `sdk-js-v1.1.0-rc1` is refused rather
than published to a channel nobody is watching. If a real prerelease need
appears, it needs a `--tag next` dist-tag decision first, not a looser regex.

The tag version and `package.json` must agree. The workflow refuses otherwise,
because a tag reading `1.1.0` over a tree reading `1.0.0` tries to republish
`1.0.0` and npm answers with an `E403` that mentions permissions, not versions —
which sends you to the token instead of to the bump.

## Release manually — required today

**GitHub Actions cannot run in this org.** Measured 2026-08-27:

```bash
gh api /repos/nRouterAI/nrouter-sdk/actions/runners --jq .total_count   # 0
gh api /orgs/nRouterAI/actions/runners              --jq .total_count   # 0
```

and a user-authored workflow run in a sibling org repo reports `steps=0` on
every job — it dies before step 1, the signature of the org-wide Actions billing
hold rather than a YAML bug. Both workflows in `.github/workflows/` are
therefore **authored but never executed**. An unrunnable gate is an absent gate.

Until runners and billing exist, run the same commands in the same order by
hand. This sequence is what the workflow does:

```bash
cd sdks/js

# 0. Authenticate once. Prefer a granular token scoped to write on this ONE
#    package over a classic automation token that can publish anything.
npm login                             # https://www.npmjs.com/settings/.../tokens
npm whoami                            # nrouter_ai

# 1. The version lives in package.json and nowhere else — and it is COMMITTED
#    AND PUSHED BEFORE publishing, not after. npm keeps the version forever;
#    if the bump is still uncommitted when `npm publish` runs, the tag you cut
#    afterwards points at the PREVIOUS manifest and the published artifact can
#    never be reproduced from its own tag.
$EDITOR package.json                  # "version": "1.1.0"
git -C ../.. commit sdks/js/package.json -m "js sdk 1.1.0"
git -C ../.. push origin main
git -C ../.. status --short           # expect empty before going further

# 2. Prove the version is free. npm will not overwrite it, and the rejection
#    does not say so clearly.
npm view @nrouter_ai/sdk@1.1.0 version     # expect: nothing, exit non-zero

# 3. Prove it green. A published version cannot be taken back.
python3 ../../conformance/check_conformance.py --self-test   # gate bites
python3 ../../conformance/check_conformance.py               # all SDKs agree
npm ci                                # locked install; never `npm install`
npm run build                         # tsc, strict, zero errors
npm test

# 4. Look at exactly what will ship. `files: ["dist"]` should keep this to the
#    build output plus README and LICENSE. A source file or a stray .env here
#    is a source file or a stray .env in the permanent tarball.
npm pack --dry-run

# 5. Publish. --access public is not optional; see below.
npm publish --access public

# 6. Tag the released commit so the tree is recoverable.
git tag -s sdk-js-v1.1.0 -m "js sdk 1.1.0"
git push origin sdk-js-v1.1.0

# 7. VERIFY AT THE REGISTRY, not from local state.
npm view @nrouter_ai/sdk version      # 1.1.0
```

Step 7 is the only real check. `npm publish` exiting 0 is npm accepting the
upload; `npm view` is the registry serving it. They are different events, and
the registry is eventually consistent for a few seconds — if it still reads
`1.0.0`, wait and re-run rather than republishing.

## `--access public` is not optional

A **scoped** package (`@nrouter_ai/…`) defaults to `restricted` on its first
publish. Without `--access public` the publish succeeds, prints nothing alarming,
and `npm install @nrouter_ai/sdk` then 404s for every user who is not in the
scope. The install command in the README stops working and nothing says why.

Two belts, deliberately:

- `package.json` carries `publishConfig: { "access": "public" }`
- the command and the workflow both pass `--access public`

Either one alone is a single point of failure. Keep both.

## Traps

- **`npm publish` is permanent.** No staging step, no overwrite. Bump, never
  re-push. The 72-hour unpublish window is not a plan — treat a bad release as
  something you fix forward with a patch version.
- **`npm ci`, never `npm install`.** `ci` installs exactly the lockfile and
  fails on drift between it and `package.json`. `npm install` silently rewrites
  the lock, so you would be testing a dependency set no consumer resolves.
- **Everything not excluded is uploaded.** `files: ["dist"]` is the allowlist,
  and `npm pack --dry-run` is the only way to see the result. `node_modules` is
  skipped automatically; a stray `.env` in `sdks/js/` is not.
- **`dist/` is gitignored and the tarball needs it.** `npm publish` ships the
  working directory, not `HEAD` — so a publish from a tree where `npm run build`
  has not run ships an empty package that installs fine and imports nothing.
  Step 3 exists for that reason; do not skip it because "nothing changed".
- **This repo is public.** Everything committed here is world-readable, and
  everything in the tarball is world-downloadable. No credentials, no internal
  hostnames, no engine name (Rule #29).
- **Never print the token.** `NODE_AUTH_TOKEN` is set on the publish step only
  in the workflow and is never echoed. Do not add `set -x` around it, and do not
  dump `npm config ls -l` into a log.
- **`--provenance` needs a workflow.** The workflow publishes with
  `--provenance`, which signs a public attestation binding the tarball to this
  repo, workflow and commit. It requires `id-token: write` and only works from
  CI — a manual `npm publish` from a laptop cannot produce one, which is why
  step 5 above omits it. If a CI publish ever fails inside provenance
  generation, dropping the flag is the correct first fallback; the release is
  still valid without it.

## Secrets a maintainer must add

| secret | where | what it is |
|---|---|---|
| `NPM_TOKEN` | repo secret, or scoped to the `npm-publish` environment | an npm **automation** or granular token with publish rights on `@nrouter_ai/sdk` |

Prefer a granular access token scoped to write on this one package with an
expiry, over a classic automation token that can publish anything the account
owns. Create it at <https://www.npmjs.com/settings/nrouter_ai/tokens>.

The workflow declares `environment: npm-publish`. Creating that environment and
adding required reviewers puts a human approval between `git push --tags` and
the irreversible upload; a plain repo secret works too, without the approval.

## Related

- Cross-SDK contract gate: `conformance/README.md` — run it before every release.
- Other SDKs' runbooks: `sdks/*/PUBLISHING.md`. Each registry is different;
  Go publishes by tag with a subdirectory prefix, crates.io and npm both refuse
  overwrites, SwiftPM resolves a bare semver tag from the repo root.
