#!/usr/bin/env bash
set -euo pipefail

uv run -m nuitka \
    --no-deployment-flag=self-execution \
    --output-dir=./build-nuitka \
    ./src/rig/
