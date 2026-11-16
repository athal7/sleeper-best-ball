// swift-tools-version:5.9
import PackageDescription

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
        .target(name: "BestBallKit"),
        .testTarget(name: "BestBallKitTests", dependencies: ["BestBallKit"]),
    ]
)
