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

Run the focused tests for any SDK you change:

```bash
# JavaScript / TypeScript — needs Node 22.18.0 or newer, because the test
# launcher hands `node --test` the .ts files and relies on native type
# stripping. On Node 20 the run dies on the first `as`, before a single test
# executes. (This is the TEST floor, not the runtime floor for the published
# package.)
cd sdks/js && npm ci && npm test

# Python — `.[dev]` is required, not optional: the suite imports httpx and
# needs pytest-asyncio for `asyncio_mode = auto`. A bare `pip install pytest`
# gives you neither.
cd sdks/python && python -m pip install -e ".[dev]" && python -m pytest -q
```

Each remaining SDK under `sdks/` carries its own suite; run the one you touch.

Opening a pull request also runs these same checks on GitHub — see
`.github/workflows/publish-npm.yml`. They are advisory, not required checks.

## Pull Requests

- Keep changes scoped to one SDK or one cross-SDK contract update.
- Update `spec/nrouter-sdk-spec.json` first when changing gateway contract
  details such as headers, error codes, endpoints, base URL, or key rules.
- Add or update tests for behavior changes.
- Do not include generated credentials, local `.env` files, registry tokens, or
  machine-specific config.

## 🛑 Do not change a version field in a pull request

`main` is the release branch and merging is the release action. A merge that
changes `version` in `sdks/js/package.json` or `sdks/python/pyproject.toml`
**publishes that version to npm or PyPI immediately**, and a published version
is immutable — it cannot be unpublished, corrected, or reused.

Leave every version field exactly as you found it. A maintainer bumps it in a
separate commit when the change is ready to ship. If your change needs a
release, say so in the PR description rather than doing it.
