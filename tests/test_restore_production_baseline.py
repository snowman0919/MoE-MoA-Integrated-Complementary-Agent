from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "restore-production-baseline.sh"


def test_restore_requires_approval_and_pins_exact_baseline() -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT), "preflight"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "DGX_MOA_RESTORE_ACK=1" in result.stderr

    source = SCRIPT.read_text()
    for required in (
        "SUDO_USER",
        "SUDO_UID",
        "DBUS_SESSION_BUS_ADDRESS",
        "DGX_MOA_EXECUTOR_BACKEND=vllm",
        "27a8f16f463b9a13c91c332c40cf93e09717347e",
        "0893e1606ff3d5f97a441f405d5fc541a6bdf404",
        "1e55f4aa327aba4c0b7a1da0d0f24626d3af5c90",
        "--max-model-len 65536",
        "--max-num-seqs 1",
        "--kv-cache-memory-bytes 1700000000",
        "--gpu-memory-utilization 0.50",
        "--moe-backend MARLIN",
        "sha256:26f620b13e49900cc6ab59ed693f9ce8f9ea4f3531074c1e39a3bf9db06ab8f0",
        "cohere_command4",
        "EXECUTOR_ROLLBACK_READY",
        "PLANNER_ROLLBACK_READY",
        "REVIEWER_ROLLBACK_READY",
    ):
        assert required in source

    restore = source.split("restore() {", 1)[1].split("\n}", 1)[0]
    assert restore.index("start dgx-moa-executor.service") < restore.index(
        "start dgx-moa-planner.service"
    )
    assert restore.index("start dgx-moa-planner.service") < restore.index(
        "start dgx-moa-reviewer.service"
    )
    assert "systemctl --user stop" not in restore
    assert "docker rm" not in source
