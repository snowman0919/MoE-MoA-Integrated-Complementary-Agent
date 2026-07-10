set dotenv-load := true

sync:
    uv sync

check:
    uv run ruff format --check .
    uv run ruff check .
    uv run mypy
    uv run pytest

run:
    uv run dgx-moa

smoke:
    scripts/smoke-test.sh

resident:
    scripts/switch-profile.sh resident

judge:
    scripts/switch-profile.sh judge

