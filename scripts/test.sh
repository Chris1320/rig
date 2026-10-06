#!/usr/bin/env bash
set -euo pipefail

echo "==> Running pytest with coverage..."
uv run pytest --cov=src --cov-report=xml --cov-report=term-missing "$@"
