# Security Policy

## Reporting a Vulnerability

Please report security issues privately by emailing `security@nrouter.ai`.

Do not open a public GitHub issue for vulnerabilities, leaked credentials, or
anything that could expose customer data.

Include:

- The affected SDK or workflow.
- Steps to reproduce.
- Impact and any known workaround.
- Whether any credential, token, or request data may have been exposed.

We aim to acknowledge a report within **3 business days** and to agree a
disclosure timeline with you before anything is published. If you do not hear
back in that window, assume the mail did not arrive and follow up.

## Supported Versions

All ten SDKs use one coordinated version derived from
`spec/nrouter-sdk-spec.json`. The conformance gate fails before publication if
any distribution manifest, lockfile, source-tag marker, or major-versioned Go
module path differs.

| SDK | Registry | Package | Supported |
|---|---|---|---|
| Python | PyPI | `nrouter-sdk` | 2.2.x |
| JavaScript / TypeScript | npm | `@nrouter_ai/sdk` | 2.2.x |
| Java | Maven Central | `ai.nrouter:nrouter-sdk` | 2.2.x |

Only the latest minor line of each package receives fixes. There is no
long-term-support branch: because every SDK is pinned to one shared gateway
contract (`spec/nrouter-sdk-spec.json`), backporting a fix to an older line
would mean maintaining a second contract, and a stale client against the live
gateway is itself the failure mode we would be preserving. Upgrade rather than
request a backport.

The remaining SDKs are public previews or source-tag distributions. They build
and receive security checks from this repository but do not carry a support
commitment.

## Retired package

`nemoroutersdk` on PyPI (0.1.0, 2026-03-31) predates a rebrand, is **not**
maintained, and is not this project. Use `nrouter-sdk`.

## Release integrity

npm versions **1.1.1 and later** carry [npm provenance][prov] attestations
linking the tarball to the exact commit and workflow that built it. Verify with:

```bash
npm audit signatures
```

⚠️ **1.0.0 and 1.1.0 have NO attestation** — verified against the registry, not
assumed. Both were uploaded by hand before CI held a working credential, and
provenance is minted from the OIDC token of the run that built the tarball, so
it cannot be added to a version after the fact. Treat those two as unattested;
1.1.1 onward is the verifiable line.

"1.1.1 onward" is a forward promise, so the way to keep it is structural rather
than editorial: `PUBLISHING.md` no longer documents a manual `npm publish`
fallback at all. CI is the only path that can publish this package, an Actions
outage means waiting rather than reaching for a laptop, and the count of
unattested versions therefore stays at two.

[prov]: https://docs.npmjs.com/generating-provenance-statements
