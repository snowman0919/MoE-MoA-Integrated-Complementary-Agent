#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/benchmarks
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
base=${DGX_MOA_BASE_URL:-http://127.0.0.1:9000}
latency=$(curl -o /dev/null -sS -w '%{time_total}' "$base/healthz")
available=$(awk '/MemAvailable:/ {print $2 * 1024}' /proc/meminfo)
free_disk=$(df -B1 --output=avail . | tail -1 | tr -d ' ')
LATENCY=$latency AVAILABLE=$available FREE_DISK=$free_disk uv run python - <<PY
import json, os
from datetime import UTC, datetime
from pathlib import Path
result={
  'timestamp': datetime.now(UTC).isoformat(),
  'gateway_health_latency_seconds': float(os.environ['LATENCY']),
  'available_unified_memory_bytes': int(os.environ['AVAILABLE']),
  'free_disk_bytes': int(os.environ['FREE_DISK']),
}
Path('data/benchmarks/$timestamp.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
PY

