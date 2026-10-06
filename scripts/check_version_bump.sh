#!/usr/bin/env bash
set -euo pipefail

BEFORE_SHA="${1:-}"
EVENT_NAME="${2:-}"

CURRENT_VERSION=$(uv run -q python -c "import tomllib, pathlib; print(tomllib.loads(pathlib.Path('pyproject.toml').read_text())['project']['version'])")

if [ "$EVENT_NAME" = "workflow_dispatch" ]; then
    SHOULD_RELEASE="true"
elif [ -n "$BEFORE_SHA" ] && [ "$BEFORE_SHA" != "0000000000000000000000000000000000000000" ]; then
    PREV_VERSION=$(git show "$BEFORE_SHA:pyproject.toml" 2>/dev/null | uv run -q python -c "import sys, tomllib; print(tomllib.loads(sys.stdin.read())['project']['version'])" 2>/dev/null || echo "")
    if [ -n "$PREV_VERSION" ] && [ "$PREV_VERSION" != "$CURRENT_VERSION" ]; then
        SHOULD_RELEASE="true"
    else
        SHOULD_RELEASE="false"
    fi
else
    SHOULD_RELEASE="false"
fi

echo "Current version: $CURRENT_VERSION"
echo "Should release: $SHOULD_RELEASE"

if [ -n "${GITHUB_OUTPUT:-}" ]; then
    echo "current_version=$CURRENT_VERSION" >> "$GITHUB_OUTPUT"
    echo "should_release=$SHOULD_RELEASE" >> "$GITHUB_OUTPUT"
fi
