#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec uv run pytest -q tests/test_opencode_synthetic.py
