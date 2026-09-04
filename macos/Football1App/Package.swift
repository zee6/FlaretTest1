// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "Football1App",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .executable(name: "Football1App", targets: ["Football1App"])
    ],
    targets: [
        .executableTarget(
            name: "Football1App",
            path: "Sources/Football1App"
        )
    ]
)
