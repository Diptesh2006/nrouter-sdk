# Contributing

Thanks for helping improve the nRouter SDKs. This repository is public, so do
not commit API keys, provider credentials, customer data, internal hostnames, or
private model/provider names.

## Development

Before opening a pull request:

```bash
python conformance/check_conformance.py --self-test
python conformance/check_conformance.py
```

Run the focused tests for any SDK you change. For the JavaScript SDK:

```bash
cd sdks/js
npm ci
npm test
```

The JavaScript test suite requires Node `22.18.0` or newer.

## Pull Requests

- Keep changes scoped to one SDK or one cross-SDK contract update.
- Update `spec/nrouter-sdk-spec.json` first when changing gateway contract
  details such as headers, error codes, endpoints, base URL, or key rules.
- Add or update tests for behavior changes.
- Do not include generated credentials, local `.env` files, registry tokens, or
  machine-specific config.
