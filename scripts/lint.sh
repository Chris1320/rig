#!/usr/bin/env bash
set -euo pipefail

TARGET_DIRS="${*:-src tests}"

echo "==> Running pylint on $TARGET_DIRS..."
uv run pylint --fail-under=9 $TARGET_DIRS

echo "==> Running black check on $TARGET_DIRS..."
uv run black --check --verbose $TARGET_DIRS

echo "==> Running isort check on $TARGET_DIRS..."
uv run isort --check-only --diff --profile black $TARGET_DIRS

echo "==> All lint and style checks passed!"
