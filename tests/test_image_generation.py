from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from dgx_moa.config import ImageGenerationConfig
from dgx_moa.image_generation import (
    CodexOAuthImageGenerator,
    ImageGenerationStore,
    capability_status,
    image_prompt_from_tool_calls,
    validate_image_artifact,
)


def png(width: int = 8, height: int = 6) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\rIHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00"
    )


def verified_config(tmp_path: Path, **overrides: object) -> ImageGenerationConfig:
    probe = tmp_path / "probe.json"
    probe.write_text(
        json.dumps(
            {
                "protocol_id": "imagegen-capability-v1",
                "passed": True,
                "provider": "codex_oauth",
                "model": "gpt-image-2",
                "content_free_logging": True,
                "secret_scan_passed": True,
                "artifact_validation_passed": True,
                "profile_lock_passed": True,
            },
            sort_keys=True,
        )
    )
    values = {
        "enabled": True,
        "artifact_root": tmp_path / "artifacts",
        "capability_probe": probe,
        "capability_probe_sha256": hashlib.sha256(probe.read_bytes()).hexdigest(),
    }
    values.update(overrides)
    return ImageGenerationConfig.model_validate(values)


def test_image_generation_is_disabled_without_a_verified_probe(tmp_path: Path) -> None:
    config = ImageGenerationConfig()
    assert capability_status(config)["state"] == "disabled_unverified"
    with pytest.raises(ValueError, match="checksummed physical capability probe"):
        ImageGenerationConfig(enabled=True, capability_probe=tmp_path / "probe.json")


def test_image_tool_parser_rejects_mixed_or_extra_arguments() -> None:
    valid = [
        {
            "id": "call-image",
            "function": {
                "name": "generate_image",
                "arguments": '{"prompt":"blue square"}',
            },
        }
    ]
    assert image_prompt_from_tool_calls(valid) == ("call-image", "blue square")
    with pytest.raises(ValueError, match="mixed"):
        image_prompt_from_tool_calls(
            [*valid, {"id": "other", "function": {"name": "read", "arguments": "{}"}}]
        )
    with pytest.raises(ValueError, match="exactly one prompt"):
        image_prompt_from_tool_calls(
            [
                {
                    "id": "call-image",
                    "function": {
                        "name": "generate_image",
                        "arguments": '{"prompt":"x","path":"/tmp/x"}',
                    },
                }
            ]
        )


def test_image_generation_probe_is_hash_pinned(tmp_path: Path) -> None:
    config = verified_config(tmp_path)
    assert capability_status(config)["state"] == "ready"

    config.capability_probe.write_text("{}")

    assert capability_status(config) == {
        "tool": "generate_image",
        "owner": "executor",
        "provider": "codex_oauth",
        "model": "gpt-image-2",
        "state": "disabled_unverified",
        "reason": "physical_probe_checksum_mismatch",
    }


def test_artifact_validation_rejects_escape_symlink_and_non_image(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    valid = root / "valid.png"
    valid.write_bytes(png())
    assert validate_image_artifact(
        valid, root=root, max_bytes=1_000, max_dimension=64
    ) == ("image/png", 8, 6, len(png()))

    outside = tmp_path / "outside.png"
    outside.write_bytes(png())
    link = root / "link.png"
    link.symlink_to(outside)
    with pytest.raises(ValueError, match="regular file"):
        validate_image_artifact(link, root=root, max_bytes=1_000, max_dimension=64)

    html = root / "not-image.png"
    html.write_text("<!DOCTYPE html>")
    with pytest.raises(ValueError, match="unsupported"):
        validate_image_artifact(html, root=root, max_bytes=1_000, max_dimension=64)


def test_image_usage_quota_and_audit_are_content_free(tmp_path: Path) -> None:
    store = ImageGenerationStore(tmp_path / "state.db", clock=lambda: 100_000.0)
    store.reserve("one", "general", 1)
    store.finish(
        "one",
        status="completed",
        latency_ms=4.2,
        byte_size=123,
        validation_status="passed",
    )
    with pytest.raises(RuntimeError, match="QUOTA_EXCEEDED"):
        store.reserve("two", "general", 1)

    record = store.get("one")
    assert record is not None
    assert set(record) == {
        "generation_id",
        "api_token_id",
        "provider",
        "model",
        "status",
        "started_at",
        "completed_at",
        "latency_ms",
        "byte_size",
        "validation_status",
        "failure_code",
    }
    assert "prompt" not in record
    assert "path" not in record


def test_generator_rejects_credential_shaped_prompt_before_usage(tmp_path: Path) -> None:
    config = verified_config(tmp_path)
    store = ImageGenerationStore(tmp_path / "state.db")
    generator = CodexOAuthImageGenerator(
        config,
        store,
        run_dir=tmp_path / "run",
        project_root=tmp_path,
        profile_root=tmp_path / "profiles",
    )

    with pytest.raises(ValueError, match="credential-shaped"):
        generator.generate("API_KEY=sk-secretsecretsecret", "general")


def test_generator_copies_one_validated_oauth_artifact(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    profiles = tmp_path / "profiles"
    codex_home = profiles / "primary"
    codex_home.mkdir(parents=True)
    (codex_home / "auth.json").write_text("{}")
    config = verified_config(tmp_path)
    store = ImageGenerationStore(tmp_path / "state.db")

    class Process:
        returncode = 0

        def __init__(self, command: list[str], **kwargs: object) -> None:
            assert command[-1] == "-"
            assert "--sandbox" in command and "read-only" in command
            assert kwargs["env"] is not None

        def communicate(
            self, input: str | None = None, timeout: float | None = None
        ) -> tuple[str, str]:
            assert input is not None and "$imagegen" in input
            assert timeout == config.timeout_seconds
            generated = codex_home / "generated_images"
            generated.mkdir()
            (generated / "result.png").write_bytes(png(20, 10))
            return "", ""

        def poll(self) -> int:
            return self.returncode

        def terminate(self) -> None:
            self.returncode = -15

        def kill(self) -> None:
            self.returncode = -9

        def wait(self, timeout: float | None = None) -> int:
            return self.returncode

    def popen(command: list[str], **kwargs: object) -> Process:
        assert command[-1] == "-"
        return Process(command, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", popen)
    generator = CodexOAuthImageGenerator(
        config,
        store,
        run_dir=tmp_path / "run",
        project_root=tmp_path,
        profile_root=profiles,
    )

    artifact = generator.generate("A blue square on a white background.", "general")

    assert artifact.media_type == "image/png"
    assert (artifact.width, artifact.height) == (20, 10)
    assert artifact.path.is_file()
    assert stat_mode(artifact.path) == 0o600
    record = store.get(artifact.artifact_id)
    assert record is not None
    assert record["status"] == "completed"
    assert record["validation_status"] == "passed"


def test_generator_terminates_cancelled_process_and_audits_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    profiles = tmp_path / "profiles"
    codex_home = profiles / "primary"
    codex_home.mkdir(parents=True)
    (codex_home / "auth.json").write_text("{}")
    config = verified_config(tmp_path)
    store = ImageGenerationStore(tmp_path / "state.db")
    started = threading.Event()
    released = threading.Event()

    class Process:
        returncode: int | None = None
        terminated = False

        def communicate(
            self, input: str | None = None, timeout: float | None = None
        ) -> tuple[str, str]:
            started.set()
            released.wait(5)
            return "", ""

        def poll(self) -> int | None:
            return self.returncode

        def terminate(self) -> None:
            self.terminated = True
            self.returncode = -15
            released.set()

        def kill(self) -> None:
            self.returncode = -9
            released.set()

        def wait(self, timeout: float | None = None) -> int:
            assert self.returncode is not None
            return self.returncode

    process = Process()
    monkeypatch.setattr(subprocess, "Popen", lambda *_args, **_kwargs: process)
    generator = CodexOAuthImageGenerator(
        config,
        store,
        run_dir=tmp_path / "run",
        project_root=tmp_path,
        profile_root=profiles,
    )
    generation_id = "a" * 32
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            generator.generate,
            "A blue square.",
            "general",
            generation_id,
        )
        assert started.wait(2)
        generator.cancel(generation_id)
        with pytest.raises(RuntimeError, match="IMAGE_GENERATION_CANCELLED"):
            future.result(timeout=2)

    assert process.terminated is True
    record = store.get(generation_id)
    assert record is not None
    assert record["status"] == "failed"
    assert record["failure_code"] == "IMAGE_GENERATION_CANCELLED"


def test_generator_terminates_timed_out_process_and_audits_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    profiles = tmp_path / "profiles"
    codex_home = profiles / "primary"
    codex_home.mkdir(parents=True)
    (codex_home / "auth.json").write_text("{}")
    config = verified_config(tmp_path, timeout_seconds=1)
    store = ImageGenerationStore(tmp_path / "state.db")

    class Process:
        returncode: int | None = None
        calls = 0
        terminated = False

        def communicate(
            self, input: str | None = None, timeout: float | None = None
        ) -> tuple[str, str]:
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired("codex", timeout or 0)
            return "", ""

        def poll(self) -> int | None:
            return self.returncode

        def terminate(self) -> None:
            self.terminated = True
            self.returncode = -15

        def kill(self) -> None:
            self.returncode = -9

        def wait(self, timeout: float | None = None) -> int:
            assert self.returncode is not None
            return self.returncode

    process = Process()
    monkeypatch.setattr(subprocess, "Popen", lambda *_args, **_kwargs: process)
    generator = CodexOAuthImageGenerator(
        config,
        store,
        run_dir=tmp_path / "run",
        project_root=tmp_path,
        profile_root=profiles,
    )
    generation_id = "b" * 32

    with pytest.raises(RuntimeError, match="IMAGE_GENERATION_TIMEOUT"):
        generator.generate("A blue square.", "general", generation_id)

    assert process.terminated is True
    record = store.get(generation_id)
    assert record is not None
    assert record["failure_code"] == "IMAGE_GENERATION_TIMEOUT"


def stat_mode(path: Path) -> int:
    return os.stat(path).st_mode & 0o777
