// swift-tools-version: 5.9
import PackageDescription

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
        // this package can run. A dependency here would be a supply-chain
        // surface bought for nothing.
        .target(name: "NRouter"),
        .testTarget(name: "NRouterTests", dependencies: ["NRouter"]),
    ]
)
