from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "isolated-sglang-topology.sh"
EXECUTOR_MANIFEST = ROOT / "config" / "sglang-executor.sha256"
SPECIALIST_MANIFEST = ROOT / "config" / "sglang-specialist.sha256"


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
    assert "--mem-fraction-static 0.45" in executor
    assert "--quantization modelopt_fp4" in executor
    assert "--tool-call-parser qwen3_coder" in executor
    assert "--disable-overlap-schedule" in executor
    assert "--disable-radix-cache" not in executor
    assert "--language-only" not in executor
    assert "--incremental-streaming-output" in executor
    assert "--restart unless-stopped" in executor
    assert "--rm" not in executor

    assert "127.0.0.1:18102:18102" in specialist
    assert "--context-length 65536" in specialist
    assert "--max-running-requests 1" in specialist
    assert "--max-total-tokens 65536" in specialist
    assert "--swa-full-tokens-ratio 0.06" in specialist
    assert "--mem-fraction-static 0.90" in specialist
    assert "--quantization modelopt_fp4" in specialist
    assert "--kv-cache-dtype" not in specialist
    assert "--reasoning-parser gemma4" in specialist
    assert "--tool-call-parser gemma4" in specialist
    assert "--constrained-json-disable-any-whitespace" in specialist
    assert "--language-only" not in specialist
    assert "--incremental-streaming-output" in specialist
    assert "--restart unless-stopped" in specialist
    assert "--rm" not in specialist

    source = SCRIPT.read_text()
    for required in (
        "SUDO_USER",
        "SUDO_UID",
        "DBUS_SESSION_BUS_ADDRESS",
        "run_as_runtime_user systemctl --user is-active",
        ".State.Running",
        'check_content "$executor_model" "$repository_root/config/sglang-executor.sha256"',
        'check_content "$specialist_model" "$repository_root/config/sglang-specialist.sha256"',
        "sha256sum --strict --status -c",
    ):
        assert required in source
    assert "systemctl --user stop" not in source
    assert "docker rm -f" not in source
    assert 'docker rm "$container"' in source
    start = source.split("  start)", 1)[1].split("  stop)", 1)[0]
    assert start.index('wait_server "$executor_container"') < start.index(
        '"${specialist_command[@]}"'
    )


def test_candidate_manifests_pin_every_weight_shard() -> None:
    pattern = re.compile(r"^[0-9a-f]{64}  (model-[0-9]{5}-of-[0-9]{5}\.safetensors)$")

    executor = [pattern.fullmatch(line) for line in EXECUTOR_MANIFEST.read_text().splitlines()]
    specialist = [pattern.fullmatch(line) for line in SPECIALIST_MANIFEST.read_text().splitlines()]

    assert all(executor) and len(executor) == 10
    assert all(specialist) and len(specialist) == 2
    assert {match.group(1) for match in executor if match} == {
        f"model-{index:05d}-of-00010.safetensors" for index in range(1, 11)
    }
    assert {match.group(1) for match in specialist if match} == {
        f"model-{index:05d}-of-00002.safetensors" for index in range(1, 3)
    }
