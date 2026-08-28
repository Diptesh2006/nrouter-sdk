<!-- Thanks for contributing. CONTRIBUTING.md has the full detail; this is the
     short form. Delete any section that does not apply. -->

## What this changes


## Why


## Checklist

- [ ] **I have not changed any `version` field.** Merging `main` publishes, and
      a published version is immutable. See CONTRIBUTING.md.
- [ ] Ran `python3 conformance/check_conformance.py --self-test` and then
      `python3 conformance/check_conformance.py` — both pass.
- [ ] Ran the focused test suite for every SDK I touched.
- [ ] If this changes the gateway contract (headers, error codes, endpoints,
      base URL, key rules), I updated `spec/nrouter-sdk-spec.json` **first** and
      every SDK follows it.
- [ ] Added or updated tests for the behaviour I changed.
- [ ] No credentials, `.env` files, registry tokens, real API keys, customer
      data, internal hostnames, or private provider names in the diff.

## Scope

<!-- Which SDK(s)? A cross-SDK contract change touches all ten and needs its
     own PR — please do not mix one with an ordinary fix. -->
