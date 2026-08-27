# Publishing the Swift SDK

**Swift Package Manager has no central registry to upload to.** A Swift package
IS a git repository, and a release IS a git tag. There is no account, no token
and no signing step — which means there is also no staging area to catch a
mistake, so the checks below happen before the tag, not after.

## The one structural requirement

SwiftPM resolves a package from the **repository root**: it looks for
`Package.swift` there and nowhere else. This SDK lives at `sdks/swift/` inside a
multi-language monorepo, so `github.com/nRouterAI/nrouter-sdk` cannot be added
as a Swift package directly — SwiftPM finds no manifest at the root and reports
the URL as not a package.

The Swift SDK therefore publishes to its own repository,
**`nRouterAI/nrouter-sdk-swift`**, whose root is a copy of `sdks/swift/`. This
repo stays the authoring home; that one is the distribution target, the same
split-and-publish shape the resources subtree uses.

## Release

```bash
# 1. Prove it green. There is no staging step after this.
cd sdks/swift
swift build && swift test
swift build -Xswiftc -strict-concurrency=complete    # Swift 6 readiness
python3 ../../conformance/check_conformance.py

# 2. Mirror sdks/swift/ into the distribution repo's root.
git subtree split --prefix=nrouter-sdk/sdks/swift -b swift-only
git push git@github.com:nRouterAI/nrouter-sdk-swift.git swift-only:main

# 3. Tag THERE — the tag is the release, and SwiftPM reads semver tags only.
# Rule #18: scratch lives under the workspace, never /tmp.
SCRATCH=~/nr/nrouter-brain/.scratch/sdk-swift-release
mkdir -p "$SCRATCH" && git clone git@github.com:nRouterAI/nrouter-sdk-swift.git "$SCRATCH/repo"
cd "$SCRATCH/repo"
git tag 2.1.0            # bare semver, no `v` — see the trap below
git push origin 2.1.0
```

Use SSH URLs throughout. HTTPS git fails from the nRouter workspace.

## Verify a consumer can actually resolve it

Publishing "worked" is not the same as resolvable. Prove it from a clean
directory:

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
- **A tag is immutable in practice.** SwiftPM caches aggressively and consumers
  pin by tag, so moving one ships different code under a version somebody
  already resolved. Bump instead; never re-tag.
- **The version in `Package.swift` is not a version** — there is no version field
  in a Swift manifest at all. The git tag is the only place a Swift package
  version exists, which is why step 3 is the release and not an afterthought.
- **`git subtree split --squash` would break this.** The split branch needs real
  history for the distribution repo to accept subsequent pushes as fast-forwards.
- **Platform floors are a promise.** Raising `platforms:` in a patch release
  breaks consumers on the old floor; that is a major-version change.
