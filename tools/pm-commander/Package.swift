// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "SapphireCommand",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "SapphireCommand", targets: ["SapphireCommand"]),
    ],
    targets: [
        .executableTarget(
            name: "SapphireCommand",
            path: "Sources"
        )
    ]
)
