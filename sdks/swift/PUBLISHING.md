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
SDK tree — which is the public repo's root, since that repo is a subtree split
of it. The manifest uses `path:` to reach `sdks/swift/Sources/NRouter`, so the
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

The consequence is worth knowing: a Swift release tags the whole monorepo, so a
tag's tree contains the other SDKs at whatever state they were in. That is
harmless — SwiftPM only ever builds the targets this manifest names — but it
does mean the Swift version number moves independently of, say, the crate
version, and they will drift.

## Release

Paths are absolute on purpose: this runbook must work from whatever directory
you happen to be in.

```bash
SDK=~/nr/nrouter-brain/nrouter-ent-ai-hub/nrouter-sdk

# 1. Prove it green. There is no staging step after this.
cd "$SDK"                      # the SDK root, where the SHIPPING manifest lives
swift build && swift test
swift build -Xswiftc -strict-concurrency=complete    # Swift 6 readiness
python3 conformance/check_conformance.py
```

### 2. Get the code onto the PUBLIC repo — two steps, not one

`scripts/publish-sdk-subtree.sh` splits `nrouter-sdk/` onto a `sdk-only` branch
and pushes it to **this repository's** origin (`nrouter-ent-ai-hub`). Read its
last line: `git push -f origin "$BRANCH"`. It does **not** touch
`nRouterAI/nrouter-sdk`. Tagging the public repo without doing that second step
tags whatever was there before — for Swift that means a tag with no root
`Package.swift`, so `from: "2.1.0"` resolves a package SwiftPM cannot see, and a
tag is immutable in practice.

```bash
cd ~/nr/nrouter-brain/nrouter-ent-ai-hub
bash scripts/publish-sdk-subtree.sh          # -> sdk-only on ent-ai-hub's origin

# Then, separately, onto the public repo:
git push git@github.com:nRouterAI/nrouter-sdk.git origin/sdk-only:main
```

> ⚠️ **That second push rewrites the public repo's `main` and needs a human
> decision, every time.** The split branch has NO shared ancestry with the
> public history (`git merge-base` between them is empty), so the push is a
> force push in effect, and the public repo carries merged outside
> contributions. Before running it: confirm every commit on public `main` is
> represented in the split — the outside PRs merged there were brought into this
> repo by hand, and anything newer would be destroyed. Check first:
>
> ```bash
> git fetch git@github.com:nRouterAI/nrouter-sdk.git main:refs/tmp/pub
> git log --oneline refs/tmp/pub | head -20     # anything not in our tree?
> ```

### 3. Tag the public repo — the tag IS the release

```bash
git ls-remote --tags git@github.com:nRouterAI/nrouter-sdk.git   # what exists
SCRATCH=~/nr/nrouter-brain/.scratch/sdk-swift-release            # Rule #18
mkdir -p "$SCRATCH" && git clone git@github.com:nRouterAI/nrouter-sdk.git "$SCRATCH/repo"
cd "$SCRATCH/repo"
test -f Package.swift || { echo "no root manifest on public main — step 2 did not land"; exit 1; }
git tag 2.1.0                  # bare semver, no `v` — see the trap below
git push origin 2.1.0
```

The `test -f Package.swift` is the guard for exactly the mistake above: it fails
loudly rather than minting an immutable tag nobody can use.

Use SSH URLs throughout. HTTPS git fails from the nRouter workspace.

## Consumers

```swift
.package(url: "https://github.com/nRouterAI/nrouter-sdk.git", from: "2.1.0")
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

- **`from: "2.1.0"` matches the tag `2.1.0`, not `v2.1.0`.** SwiftPM accepts a
  `v` prefix, but mixing the two across releases makes version ranges resolve in
  ways nobody expects. Pick bare semver and keep it.
- **The publish script does not publish to the public repo.** Its name says
  publish and its final line pushes to `origin`, which is the AUTHORING repo.
  The public repo is a second, deliberate push.
- **A tag is immutable in practice.** SwiftPM caches aggressively and consumers
  pin by tag, so moving one ships different code under a version somebody
  already resolved. Bump instead; never re-tag.
- **The version in `Package.swift` is not a version** — a Swift manifest has no
  version field at all. The git tag is the only place a Swift package version
  exists, which is why tagging is the release and not an afterthought.
- **The two manifests drift silently.** Nothing checks that the root and nested
  manifests agree; a target added to one and not the other builds locally and
  fails for consumers, or vice versa.
- **Platform floors are a promise.** Raising `platforms:` in a patch release
  breaks consumers on the old floor; that is a major-version change.
