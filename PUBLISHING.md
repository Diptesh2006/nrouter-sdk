# Publishing the SDKs

One workflow per language, both merge-triggered:

| package | workflow | version lives in |
|---|---|---|
| `@nrouter_ai/sdk` (npm) | `.github/workflows/publish-npm.yml` | `sdks/js/package.json` |
| `nrouter-sdk` (PyPI) | `.github/workflows/publish-pypi.yml` | `sdks/python/pyproject.toml` |

## To release

Bump the version, merge to `main`. That is the whole procedure.

```bash
$EDITOR sdks/js/package.json          # "version": "1.1.0"
# ...open a PR, get it merged...
```

The workflow then runs the tests and the cross-SDK conformance gate, and
publishes only if that version is not already on the registry.

**A merge that does not change the version publishes nothing.** That is what
makes merge-triggered safe: npm and PyPI versions are immutable, so re-running
on every merge would otherwise fail constantly. The `already published?` step
turns the no-change case into a quiet green no-op instead.

## Secrets

| secret | status |
|---|---|
| `PYPI_API_TOKEN` | ✅ **set** (2026-08-27), from `~/.nrouter_admin_keys/pypi/pypi.txt` |
| `NPM_TOKEN` | ❌ not set — `gh secret set NPM_TOKEN --repo nRouterAI/nrouter-sdk` |

npm token: npmjs.com → Access Tokens → Granular, write on `@nrouter_ai/sdk`.

**To re-verify a PyPI token without publishing anything:** build a version that
is ALREADY on PyPI and attempt the upload. `400 File already exists` means the
token authenticated AND was authorized; `403` means it was not. That probe is
what proved this repo's own credential doc wrong — it claimed the token was
scoped to the retired brand's project and could not publish here.

## Things that bite

- **`--access public` is not optional** on a scoped package. Without it npm
  makes the package private and every install fails for everyone.
- **`npm publish` exiting 0 is npm accepting the upload, not the registry
  serving it.** Both workflows poll the registry afterwards; a green publish
  step alone is not proof.
- **Never publish a version older than the current `latest`.** Without an
  explicit dist-tag it moves npm's default pointer backwards and silently
  downgrades every fresh install. A deliberate backport goes out as
  `npm publish --access public --tag backport`.
- **A version cannot be taken back.** The 72h unpublish window is a fire
  escape, not a process. Bump forward; never re-push.

## Manual fallback

Only if Actions is unavailable. Same order the workflow uses — test, check,
publish, verify at the registry:

```bash
cd sdks/js && npm ci && npm test
python3 ../../conformance/check_conformance.py
npm view @nrouter_ai/sdk@1.1.0 version    # expect nothing
npm publish --access public
npm view @nrouter_ai/sdk version          # expect 1.1.0
```

```bash
cd sdks/python && python -m pytest -q
python3 ../../conformance/check_conformance.py
python -m build && python -m twine check dist/*
python -m twine upload dist/*
curl -s -o /dev/null -w '%{http_code}\n' https://pypi.org/pypi/nrouter-sdk/2.2.0/json   # expect 200
```
