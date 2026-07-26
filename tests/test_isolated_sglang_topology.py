from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "isolated-sglang-topology.sh"


def test_candidate_commands_pin_safe_two_model_topology() -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT), "print"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    executor, specialist = result.stdout.splitlines()

    assert "127.0.0.1:18101:18101" in executor
    assert "--context-length 65536" in executor
    assert "--max-running-requests 1" in executor
    assert "--max-total-tokens 65536" in executor
    assert "--max-mamba-cache-size 5" in executor
    assert "--mem-fraction-static 0.54" in executor
    assert "--tool-call-parser qwen3_coder" in executor
    assert "--disable-radix-cache" not in executor
    assert "--language-only" not in executor
    assert "--incremental-streaming-output" in executor
    assert "--rm" not in executor

    assert "127.0.0.1:18102:18102" in specialist
    assert "--context-length 65536" in specialist
    assert "--max-running-requests 1" in specialist
    assert "--max-total-tokens 65536" in specialist
    assert "--mem-fraction-static 0.75" in specialist
    assert "--quantization modelopt_fp4" in specialist
    assert "--kv-cache-dtype" not in specialist
    assert "--reasoning-parser gemma4" in specialist
    assert "--tool-call-parser gemma4" in specialist
    assert "--language-only" not in specialist
    assert "--incremental-streaming-output" in specialist
    assert "--rm" not in specialist

    source = SCRIPT.read_text()
    for required in (
        "SUDO_USER",
        "SUDO_UID",
        "DBUS_SESSION_BUS_ADDRESS",
        "run_as_runtime_user systemctl --user is-active",
        ".State.Running",
    ):
        assert required in source
    assert "systemctl --user stop" not in source
    assert "docker rm -f" not in source
    start = source.split("  start)", 1)[1].split("  stop)", 1)[0]
    assert start.index('wait_server "$executor_container"') < start.index(
        '"${specialist_command[@]}"'
    )
