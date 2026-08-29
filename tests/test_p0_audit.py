from __future__ import annotations

import importlib.util
from pathlib import Path


def test_p0_audit_parses_concatenated_healthcheck_documents(tmp_path: Path) -> None:
    path = Path(__file__).parents[1] / "scripts/audit-current-executor-p0.py"
    spec = importlib.util.spec_from_file_location("audit_current_executor_p0", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.json_stream(' \n{"status":"ok"}\n{"data":[]}\n{"status":"ready"}\n') == [
        {"status": "ok"},
        {"data": []},
        {"status": "ready"},
    ]

    command = module.executor_probe_command(
        module.EXECUTOR_BASE_IMAGE,
        Path("/runtime/venv/bin/python"),
        Path("/runtime/python"),
    )
    assert "--gpus" in command and "--read-only" in command and "no-new-privileges" in command
    assert "@sha256:" in command[command.index("/runtime/python:/runtime/python:ro") + 1]

    artifact = tmp_path / "artifact"
    artifact.mkdir()
    (artifact / "weights").write_bytes(b"weights")
    first = module.artifact_digest(artifact)
    (artifact / "weights").write_bytes(b"changed")
    assert first == {"sha256": first["sha256"], "files": 1, "bytes": 7}
    assert module.artifact_digest(artifact)["sha256"] != first["sha256"]
    assert module.option_value(["server", "--host", "127.0.0.1"], "--host") == "127.0.0.1"
    assert (
        module.select_reasoner_model(
            {"models": [{"name": "other"}, {"name": "reasoner", "digest": "a" * 64}]},
            "reasoner",
        )["digest"]
        == "a" * 64
    )
    assert module.digest_pinned("repo/name@sha256:" + "a" * 64)
    assert module.digest_pinned("sha256:" + "b" * 64)
    assert not module.digest_pinned("repo/name:latest")
    assert module.REQUIRED_P0_SERVICES == ("gateway", "executor", "reasoner", "harness")

    dockerfile = (Path(__file__).parents[1] / "Dockerfile").read_text()
    assert all("@sha256:" in line for line in dockerfile.splitlines() if line.startswith("FROM "))
    assert "uv sync --frozen --no-dev --no-editable" in dockerfile
    assert "pip install" not in dockerfile
