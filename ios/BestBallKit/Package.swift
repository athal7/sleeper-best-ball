// swift-tools-version:5.9
import Foundation
import PackageDescription

// The engine archive is built from source by `core/scripts/build-ios.sh`, not
// published, so the manifest points at that build output. Resolved to an
// absolute path here because the linker would otherwise get a path relative to
// whatever directory it happens to run in.
let engineDirectory = URL(fileURLWithPath: #filePath)
    .deletingLastPathComponent()
    .deletingLastPathComponent()
    .appendingPathComponent(".engine")
    .standardizedFileURL.path

let package = Package(
    name: "BestBallKit",
    platforms: [
        .iOS(.v17),
        .macOS(.v14),
    ],
    products: [
        .library(name: "BestBallKit", targets: ["BestBallKit"]),
    ],
    targets: [
        .target(
            name: "CEngine",
            path: "Sources/CEngine",
            publicHeadersPath: "include"
        ),
        .target(
            name: "BestBallKit",
            dependencies: ["CEngine"],
            // unsafeFlags keeps this package local-only: it is never consumed as
            // a remote dependency, and there is no XCFramework to point at.
            linkerSettings: [
                .unsafeFlags(["-L", engineDirectory, "-lbestball_engine"]),
            ]
        ),
        .testTarget(name: "BestBallKitTests", dependencies: ["BestBallKit"]),
    ]
)
