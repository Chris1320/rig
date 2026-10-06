#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR_NUITKA="$SCRIPT_DIR/build-nuitka"
OUTPUT_DIR_WHEEL="$SCRIPT_DIR/dist"

show_help() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

OPTIONS:
  all       Build wheel and Nuitka executable
  wheel     Build wheel package (.whl) via uv build
  nuitka    Compile executable binary using Nuitka
  help      Show this help message
EOF
}

build_wheel() {
    echo "==> Building wheel package via uv build..."
    mkdir -p "$OUTPUT_DIR_WHEEL"
    uv build --wheel --out-dir "$OUTPUT_DIR_WHEEL"
    echo "==> Wheel built in $OUTPUT_DIR_WHEEL"
}

build_nuitka() {
    echo "==> Building executable via Nuitka..."

    if ! command -v patchelf &>/dev/null; then
        echo "Error: patchelf is required to build a standalone one-file executable on Linux." >&2
        echo "Please install patchelf using your package manager (e.g. sudo dnf install patchelf or sudo apt install patchelf)." >&2
        exit 1
    fi

    mkdir -p "$OUTPUT_DIR_NUITKA" "$OUTPUT_DIR_WHEEL"

    VERSION=$(uv run -q python -c "import tomllib, pathlib; print(tomllib.loads(pathlib.Path('pyproject.toml').read_text())['project']['version'])")
    OS_NAME=$(uname -s | tr '[:upper:]' '[:lower:]')
    ARCH_NAME=$(uname -m)
    BINARY_NAME="rig-v${VERSION}-${OS_NAME}-${ARCH_NAME}"

    NUITKA_FLAGS=(
        --mode=onefile
        --include-package=rig
        --assume-yes-for-downloads
        --no-deployment-flag=self-execution
        --output-dir="$OUTPUT_DIR_NUITKA"
        --output-filename="$BINARY_NAME"
    )

    uv run -m nuitka "${NUITKA_FLAGS[@]}" ./src/rig/

    echo "==> Moving single executable to $OUTPUT_DIR_WHEEL/$BINARY_NAME..."
    mv "$OUTPUT_DIR_NUITKA/$BINARY_NAME" "$OUTPUT_DIR_WHEEL/$BINARY_NAME"
    chmod +x "$OUTPUT_DIR_WHEEL/$BINARY_NAME"

    echo "==> Compiled successfully!"
}

TARGET="${1:-all}"

case "$TARGET" in
all)
    build_wheel
    build_nuitka
    ;;
wheel)
    build_wheel
    ;;
nuitka)
    build_nuitka
    ;;
help)
    show_help
    exit 0
    ;;
*)
    echo "Error: Unknown build target or option '$TARGET'" >&2
    echo "" >&2
    show_help >&2
    exit 1
    ;;
esac
