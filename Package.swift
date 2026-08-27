// swift-tools-version: 5.9
import PackageDescription

// Swift Package Manager reads `Package.swift` from the REPOSITORY ROOT and
// offers no way to point a dependency at a subdirectory. That is why this
// manifest is here rather than only in `sdks/swift/`: this directory is the
// root of the public `nRouterAI/nrouter-sdk` repo (a subtree split of it), so a
// manifest here is a manifest at that repo's root.
//
// The SOURCES stay where they belong. `path:` moves the targets, so nothing had
// to be relocated and the Swift SDK lives beside the other eight.
//
// `sdks/swift/Package.swift` still exists and still works — `cd sdks/swift &&
// swift test` is the local dev loop. The two manifests coexist; the nested one
// is never what a consumer resolves.
let package = Package(
    name: "NRouter",
    platforms: [
        .macOS(.v12),
        .iOS(.v15),
        .tvOS(.v15),
        .watchOS(.v8),
        .visionOS(.v1),
    ],
    products: [
        .library(name: "NRouter", targets: ["NRouter"]),
    ],
    targets: [
        // No external dependencies on purpose: the gateway speaks the OpenAI
        // wire format over plain HTTP, and URLSession is already everywhere
        // this package can run.
        .target(name: "NRouter", path: "sdks/swift/Sources/NRouter"),
        .testTarget(
            name: "NRouterTests",
            dependencies: ["NRouter"],
            path: "sdks/swift/Tests/NRouterTests"
        ),
    ]
)
