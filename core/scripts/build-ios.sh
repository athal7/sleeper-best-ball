#!/usr/bin/env bash
# Builds the shared engine into `ios/.engine/libbestball_engine.a`, the archive
# BestBallKit links. Source-only on purpose: no published binary artifact, so
# the app can never be stale relative to `core/`.
#
#   core/scripts/build-ios.sh host     # macOS, for `swift test` on BestBallKit
#   core/scripts/build-ios.sh xcode    # whichever SDK/arch Xcode is building
#   core/scripts/build-ios.sh device   # aarch64-apple-ios (-sim for simulator)
#
# Xcode calls the `xcode` mode from a run script phase; see AGENTS.md.
set -euo pipefail

# rustc only passes `-isysroot` when it can find the platform SDK, so SDKROOT
# has to be a real path. Xcode exports it as an SDK *name* ("iphonesimulator"),
# which clang then resolves relative to the working directory.
use_sdk() {
    export SDKROOT="$(xcrun --sdk "$1" --show-sdk-path)"
}

root="$(cd "$(dirname "$0")/../.." && pwd)"
out="$root/ios/.engine"
mkdir -p "$out"

cargo_build() {
    cargo build --manifest-path "$root/core/Cargo.toml" --release --target "$1"
}

# Copy a target's archive into place, lipo-ing with any extra slices so one
# archive can serve simulator arm64 + x86_64.
install_archive() {
    local first="$1"
    shift
    local inputs=("$root/core/target/$first/release/libbestball_engine.a")
    for target in "$@"; do
        inputs+=("$root/core/target/$target/release/libbestball_engine.a")
    done
    if [ "${#inputs[@]}" -eq 1 ]; then
        cp "${inputs[0]}" "$out/libbestball_engine.a"
    else
        lipo -create "${inputs[@]}" -output "$out/libbestball_engine.a"
    fi
    echo "engine: $out/libbestball_engine.a"
}

case "${1:-host}" in
    host)
        cargo build --manifest-path "$root/core/Cargo.toml" --release
        cp "$root/core/target/release/libbestball_engine.a" "$out/libbestball_engine.a"
        echo "engine: $out/libbestball_engine.a (host)"
        ;;
    device)
        use_sdk iphoneos
        cargo_build aarch64-apple-ios
        install_archive aarch64-apple-ios
        ;;
    simulator|sim)
        # One archive for both simulator slices: Xcode builds arm64 and x86_64
        # for "generic/platform=iOS Simulator".
        use_sdk iphonesimulator
        cargo_build aarch64-apple-ios-sim
        cargo_build x86_64-apple-ios
        install_archive aarch64-apple-ios-sim x86_64-apple-ios
        ;;
    xcode)
        # Xcode builds simulator and device from the same project; the archive
        # has to match the SDK currently being built or the link fails.
        case "${SDK_NAME:-}" in
            iphoneos*)
                use_sdk iphoneos
                cargo_build aarch64-apple-ios
                install_archive aarch64-apple-ios
                ;;
            iphonesimulator*)
                use_sdk iphonesimulator
                cargo_build aarch64-apple-ios-sim
                cargo_build x86_64-apple-ios
                install_archive aarch64-apple-ios-sim x86_64-apple-ios
                ;;
            macosx*)
                use_sdk macosx
                cargo build --manifest-path "$root/core/Cargo.toml" --release
                cp "$root/core/target/release/libbestball_engine.a" \
                   "$out/libbestball_engine.a"
                echo "engine: $out/libbestball_engine.a (macOS)"
                ;;
            *)
                echo "engine: unsupported SDK '${SDK_NAME:-unset}'" >&2
                exit 1
                ;;
        esac
        ;;
    *)
        echo "usage: $0 [host|device|simulator|xcode]" >&2
        exit 2
        ;;
esac
