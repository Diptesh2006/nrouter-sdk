# Publishing the Swift SDK

**Swift Package Manager has no central registry to upload to.** A Swift package
IS a git repository and a release IS a git tag. There is no account, no token
and no signing step — which also means no staging area to catch a mistake, so
the checks below happen before the tag, not after.

## It ships from the SAME repo as every other SDK

`nRouterAI/nrouter-sdk` is the distribution target. No separate Swift repo.

SwiftPM does impose one real constraint: it reads `Package.swift` from the
**repository root** and offers no way to point a dependency at a subdirectory.
That is satisfied by [`Package.swift`](../../Package.swift) at the root of this
public repository. The manifest uses `path:` to reach `sdks/swift/Sources/NRouter`, so the
sources stay beside the other eight SDKs and nothing was relocated.

`sdks/swift/Package.swift` still exists for the local loop (`cd sdks/swift &&
swift test`). Both manifests coexist; the nested one is never what a consumer
resolves. **Any change to targets or platforms must be made in BOTH** — they are
two declarations of one package, and only the root one ships.

## The tag is the release

Bare semver tags on the public repo are Swift's version markers. Every other SDK
resolves through its own registry (PyPI, npm, crates.io, pub.dev, Maven Central,
R-universe) and needs no git tag, so semver tags there mean "the Swift package",
and nothing else competes for them.

The Swift tag points at the same coordinated release commit as every registry
package. SwiftPM only builds the targets this manifest names, while
`sdks/swift/VERSION` and the cross-SDK conformance gate prevent its tag version
from drifting from the shared release train.

## Release

Paths are absolute on purpose: this runbook must work from whatever directory
you happen to be in.

```bash
SDK=~/nr/nrouter-brain/nrouter-sdk

# 1. Prove it green. There is no staging step after this.
cd "$SDK"                      # the SDK root, where the SHIPPING manifest lives
swift build && swift test
swift build -Xswiftc -strict-concurrency=complete    # Swift 6 readiness
python3 conformance/check_conformance.py
```

### 2. Prove public main is the exact tested tree

```bash
git status --short                           # expect empty
git fetch origin main
git rev-list --left-right --count HEAD...origin/main   # expect 0 0
test -f Package.swift
```

### 3. Tag the public repo — the tag IS the release

```bash
git ls-remote --tags origin
git tag 3.0.0                  # bare semver, no `v` — see the trap below
git push origin 3.0.0
```

The `test -f Package.swift` is the guard for exactly the mistake above: it fails
loudly rather than minting an immutable tag nobody can use.

Use SSH URLs throughout. HTTPS git fails from the nRouter workspace.

## Consumers

```swift
.package(url: "https://github.com/nRouterAI/nrouter-sdk.git", from: "3.0.0")
```

Or in Xcode: **File → Add Package Dependencies** and paste that URL.

## Verify a consumer can actually resolve it

Publishing "worked" is not the same as resolvable. Prove it from a clean
directory, which also catches a root manifest that names a path that moved:

```bash
PROBE=~/nr/nrouter-brain/.scratch/sdk-swift-release/probe   # Rule #18, not /tmp
mkdir -p "$PROBE" && cd "$PROBE" && swift package init
# add the dependency to Package.swift, then:
swift package resolve
```

## Traps

- **`from: "3.0.0"` matches the tag `3.0.0`, not `v3.0.0`.** SwiftPM accepts a
  `v` prefix, but mixing the two across releases makes version ranges resolve in
  ways nobody expects. Pick bare semver and keep it.
- **Tag only clean, pushed `main`.** SwiftPM resolves the immutable tag, not
  whatever happens to be in the working tree.
- **A tag is immutable in practice.** SwiftPM caches aggressively and consumers
  pin by tag, so moving one ships different code under a version somebody
  already resolved. Bump instead; never re-tag.
- **The version in `Package.swift` is not a version** — a Swift manifest has no
  version field at all. The git tag is the only place a Swift package version
  exists, which is why tagging is the release and not an afterthought.
- **The two manifests are independently executable.** The conformance gate
  checks target, product and platform parity, and the release workflow builds
  both; keep both declarations aligned.
- **Platform floors are a promise.** Raising `platforms:` in a patch release
  breaks consumers on the old floor; that is a major-version change.
