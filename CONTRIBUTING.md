# Contributing

Thanks for helping improve the nRouter SDKs. This repository is public, so do
not commit API keys, provider credentials, customer data, internal hostnames, or
private model/provider names.

## Development

Before opening a pull request:

```bash
# `python3`, not `python` — the script's shebang is python3 and a stock
# Debian/Ubuntu or CI image has no bare `python` on PATH.
python3 conformance/check_conformance.py --self-test
python3 conformance/check_conformance.py
```

The `--self-test` run comes first on purpose: it proves the gate still goes RED
on drift. A conformance check that cannot fail tells you nothing when it passes.

Run the focused tests for any SDK you change. Each line is wrapped in a
subshell so the `cd` does not persist — run the block top to bottom without
them and the second `cd` resolves inside the first SDK's directory and fails.


```bash
# JavaScript / TypeScript — needs Node 22.18.0 or newer, because the test
# launcher hands `node --test` the .ts files and relies on native type
# stripping. On Node 20 the run dies on the first `as`, before a single test
# executes. (This is the TEST floor, not the runtime floor for the published
# package.)
(cd sdks/js && npm ci && npm test)

# Python — `.[dev]` is required, not optional: the suite imports httpx and
# needs pytest-asyncio for `asyncio_mode = auto`. A bare `pip install pytest`
# gives you neither. Use a virtualenv unless you want these in your system
# site-packages.
(cd sdks/python && python3 -m pip install -e ".[dev]" && python3 -m pytest -q)
```

Each remaining SDK under `sdks/` carries its own suite; run the one you touch.

Opening a pull request runs these checks on GitHub for the **JavaScript and
Python** SDKs only (`publish-npm.yml`, `publish-pypi.yml`), and only when the
PR touches `sdks/js/**`, `sdks/python/**`, `spec/**` or `conformance/**`. A
change to any other SDK is verified by you locally and by review — nothing on
GitHub will catch it, so run its suite before you open the PR. The checks that
do run are advisory, not required status checks.

## Pull Requests

- Keep changes scoped to one SDK or one cross-SDK contract update.
- Update `spec/nrouter-sdk-spec.json` first when changing gateway contract
  details such as headers, error codes, endpoints, base URL, or key rules.
- Add or update tests for behavior changes.
- Do not include generated credentials, local `.env` files, registry tokens, or
  machine-specific config.

## 🛑 Do not change a version field in a pull request

`main` is the release branch and merging is the release action. A merge that
changes a version field **publishes immediately**, and a published version is
immutable — it cannot be unpublished, corrected, or reused. There are three
such files, one per registry:

| file | publishes to |
|---|---|
| `sdks/js/package.json` | npm `@nrouter_ai/sdk` |
| `sdks/python/pyproject.toml` | PyPI `nrouter-sdk` |
| `sdks/java/pom.xml` | Maven Central `ai.nrouter:nrouter-sdk` |

Leave every version field exactly as you found it. A maintainer bumps it in a
separate commit when the change is ready to ship. If your change needs a
release, say so in the PR description rather than doing it.
