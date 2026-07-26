from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import struct
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .config import ImageGenerationConfig
from .database import connect_sqlite
from .frontier import CodexOAuthProvider, profile_home, profile_lock, profile_status
from .security import TOKEN_ID, redact

IMAGEGEN_PROTOCOL = "imagegen-capability-v1"
ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


@dataclass(frozen=True)
class ImageArtifact:
    artifact_id: str
    path: Path
    media_type: str
    width: int
    height: int
    byte_size: int


class ImageGenerationStore:
    def __init__(self, path: str | Path, *, clock: Any = time.time) -> None:
        self.path = Path(path)
        self.clock = clock
        with connect_sqlite(self.path, secure=True) as database:
            database.execute(
                "CREATE TABLE IF NOT EXISTS image_generation_usage ("
                "generation_id TEXT PRIMARY KEY, api_token_id TEXT NOT NULL, "
                "provider TEXT NOT NULL, model TEXT NOT NULL, status TEXT NOT NULL, "
                "started_at REAL NOT NULL, completed_at REAL, latency_ms REAL, "
                "byte_size INTEGER, validation_status TEXT, failure_code TEXT)"
            )
            database.execute(
                "CREATE INDEX IF NOT EXISTS image_generation_usage_key_time "
                "ON image_generation_usage(api_token_id, started_at)"
            )

    def reserve(self, generation_id: str, api_token_id: str, daily_limit: int) -> None:
        if not TOKEN_ID.fullmatch(api_token_id):
            raise ValueError("invalid API token ID")
        now = float(self.clock())
        with connect_sqlite(self.path, secure=True) as database:
            database.execute("BEGIN IMMEDIATE")
            used = database.execute(
                "SELECT COUNT(*) FROM image_generation_usage "
                "WHERE api_token_id = ? AND started_at >= ? AND status != 'rejected'",
                (api_token_id, now - 86_400),
            ).fetchone()[0]
            if used >= daily_limit:
                raise RuntimeError("IMAGE_GENERATION_QUOTA_EXCEEDED")
            database.execute(
                "INSERT INTO image_generation_usage VALUES "
                "(?, ?, 'codex_oauth', 'gpt-image-2', 'started', ?, NULL, NULL, NULL, NULL, NULL)",
                (generation_id, api_token_id, now),
            )

    def finish(
        self,
        generation_id: str,
        *,
        status: Literal["completed", "failed"],
        latency_ms: float,
        byte_size: int | None = None,
        validation_status: str | None = None,
        failure_code: str | None = None,
    ) -> None:
        with connect_sqlite(self.path, secure=True) as database:
            database.execute(
                "UPDATE image_generation_usage SET status = ?, completed_at = ?, "
                "latency_ms = ?, byte_size = ?, validation_status = ?, failure_code = ? "
                "WHERE generation_id = ?",
                (
                    status,
                    float(self.clock()),
                    round(latency_ms, 3),
                    byte_size,
                    validation_status,
                    failure_code,
                    generation_id,
                ),
            )

    def get(self, generation_id: str) -> dict[str, Any] | None:
        with connect_sqlite(self.path, rows=True, secure=True) as database:
            row = database.execute(
                "SELECT * FROM image_generation_usage WHERE generation_id = ?",
                (generation_id,),
            ).fetchone()
        return dict(row) if row is not None else None


def _probe_status(config: ImageGenerationConfig) -> tuple[str, str]:
    if not config.enabled:
        return "disabled_unverified", "configuration_disabled"
    if config.capability_probe is None or config.capability_probe_sha256 is None:
        return "disabled_unverified", "physical_probe_missing"
    try:
        raw = config.capability_probe.read_bytes()
        probe = json.loads(raw)
    except (OSError, ValueError, TypeError):
        return "disabled_unverified", "physical_probe_invalid"
    if hashlib.sha256(raw).hexdigest() != config.capability_probe_sha256:
        return "disabled_unverified", "physical_probe_checksum_mismatch"
    required = {
        "protocol_id": IMAGEGEN_PROTOCOL,
        "passed": True,
        "provider": "codex_oauth",
        "model": "gpt-image-2",
        "content_free_logging": True,
        "secret_scan_passed": True,
        "artifact_validation_passed": True,
        "profile_lock_passed": True,
    }
    if not isinstance(probe, dict) or any(
        probe.get(key) != value for key, value in required.items()
    ):
        return "disabled_unverified", "physical_probe_failed"
    return "ready", "verified"


def capability_status(config: ImageGenerationConfig) -> dict[str, str]:
    state, reason = _probe_status(config)
    return {
        "tool": "generate_image",
        "owner": "executor",
        "provider": config.provider,
        "model": config.model,
        "state": state,
        "reason": reason,
    }


def image_prompt_from_tool_calls(tool_calls: list[dict[str, Any]]) -> tuple[str, str] | None:
    image_calls = [
        call
        for call in tool_calls
        if isinstance(call, dict)
        and isinstance(call.get("function"), dict)
        and call["function"].get("name") == "generate_image"
    ]
    if not image_calls:
        return None
    if len(image_calls) != 1 or len(tool_calls) != 1:
        raise ValueError("generate_image cannot be mixed with other tool calls")
    call = image_calls[0]
    call_id = call.get("id")
    arguments = call["function"].get("arguments")
    if not isinstance(call_id, str) or not call_id or not isinstance(arguments, str):
        raise ValueError("invalid generate_image tool call")
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError as error:
        raise ValueError("invalid generate_image arguments") from error
    if (
        not isinstance(parsed, dict)
        or set(parsed) != {"prompt"}
        or not isinstance(parsed["prompt"], str)
    ):
        raise ValueError("generate_image requires exactly one prompt")
    return call_id, parsed["prompt"]


def _png_dimensions(header: bytes) -> tuple[int, int] | None:
    if len(header) >= 24 and header.startswith(b"\x89PNG\r\n\x1a\n"):
        return struct.unpack(">II", header[16:24])
    return None


def _webp_dimensions(header: bytes) -> tuple[int, int] | None:
    if len(header) < 30 or header[:4] != b"RIFF" or header[8:12] != b"WEBP":
        return None
    kind = header[12:16]
    if kind == b"VP8X":
        return (
            1 + int.from_bytes(header[24:27], "little"),
            1 + int.from_bytes(header[27:30], "little"),
        )
    if kind == b"VP8 " and header[23:26] == b"\x9d\x01\x2a":
        return (
            int.from_bytes(header[26:28], "little") & 0x3FFF,
            int.from_bytes(header[28:30], "little") & 0x3FFF,
        )
    if kind == b"VP8L" and header[20] == 0x2F:
        bits = int.from_bytes(header[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    return None


def _jpeg_dimensions(path: Path) -> tuple[int, int] | None:
    with path.open("rb") as stream:
        if stream.read(2) != b"\xff\xd8":
            return None
        while marker := stream.read(1):
            if marker != b"\xff":
                continue
            while (code := stream.read(1)) == b"\xff":
                pass
            if not code or code in {b"\xd8", b"\xd9"}:
                continue
            length_raw = stream.read(2)
            if len(length_raw) != 2:
                return None
            length = int.from_bytes(length_raw, "big")
            if length < 2:
                return None
            if code[0] in {
                0xC0,
                0xC1,
                0xC2,
                0xC3,
                0xC5,
                0xC6,
                0xC7,
                0xC9,
                0xCA,
                0xCB,
                0xCD,
                0xCE,
                0xCF,
            }:
                payload = stream.read(5)
                if len(payload) != 5:
                    return None
                return int.from_bytes(payload[3:5], "big"), int.from_bytes(
                    payload[1:3], "big"
                )
            stream.seek(length - 2, os.SEEK_CUR)
    return None


def validate_image_artifact(
    path: str | Path,
    *,
    root: str | Path,
    max_bytes: int,
    max_dimension: int,
    require_owner_only: bool = False,
) -> tuple[str, int, int, int]:
    candidate = Path(path)
    root_path = Path(root)
    root_metadata = root_path.lstat()
    if not stat.S_ISDIR(root_metadata.st_mode) or root_metadata.st_uid != os.getuid():
        raise ValueError("image artifact root must be an owner-controlled directory")
    allowed_root = root_path.resolve(strict=True)
    metadata = candidate.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_uid != os.getuid()
    ):
        raise ValueError("image artifact must be an unlinked regular file")
    if require_owner_only and stat.S_IMODE(metadata.st_mode) != 0o600:
        raise ValueError("image artifact must be owner-only")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(allowed_root):
        raise ValueError("image artifact escaped its allowed root")
    size = metadata.st_size
    if not 0 < size <= max_bytes:
        raise ValueError("image artifact size is outside the configured limit")
    with candidate.open("rb") as stream:
        header = stream.read(64)
    dimensions = _png_dimensions(header)
    media_type = "image/png"
    if dimensions is None:
        dimensions = _webp_dimensions(header)
        media_type = "image/webp"
    if dimensions is None:
        dimensions = _jpeg_dimensions(candidate)
        media_type = "image/jpeg"
    if dimensions is None:
        raise ValueError("unsupported image artifact")
    width, height = dimensions
    if min(width, height) < 1 or max(width, height) > max_dimension:
        raise ValueError("image dimensions exceed the configured limit")
    return media_type, width, height, size


class CodexOAuthImageGenerator:
    def __init__(
        self,
        config: ImageGenerationConfig,
        store: ImageGenerationStore,
        *,
        run_dir: str | Path,
        project_root: str | Path,
        profile_root: str | Path | None = None,
        clock: Any = time.monotonic,
    ) -> None:
        self.config = config
        self.store = store
        self.run_dir = Path(run_dir)
        self.project_root = Path(project_root).resolve()
        self.profile_root = Path(profile_root) if profile_root is not None else None
        self.clock = clock
        self._process_lock = threading.Lock()
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._cancelled: set[str] = set()

    def status(self) -> dict[str, str]:
        return capability_status(self.config)

    def tool_definition(self) -> dict[str, Any] | None:
        if self.status()["state"] != "ready":
            return None
        return {
            "type": "function",
            "function": {
                "name": "generate_image",
                "description": "Generate one validated image artifact through Codex OAuth.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": self.config.max_prompt_characters,
                        }
                    },
                    "required": ["prompt"],
                    "additionalProperties": False,
                },
            },
        }

    def artifact_for(self, artifact_id: str, api_token_id: str) -> ImageArtifact:
        if not TOKEN_ID.fullmatch(api_token_id) or not (
            len(artifact_id) == 32
            and all(character in "0123456789abcdef" for character in artifact_id)
        ):
            raise KeyError(artifact_id)
        record = self.store.get(artifact_id)
        if (
            record is None
            or record["api_token_id"] != api_token_id
            or record["status"] != "completed"
        ):
            raise KeyError(artifact_id)
        generation_root = self.config.artifact_root / artifact_id
        try:
            candidates = [
                path
                for path in generation_root.iterdir()
                if path.is_file() and path.name.startswith("artifact.")
            ]
        except OSError as error:
            raise KeyError(artifact_id) from error
        if len(candidates) != 1:
            raise KeyError(artifact_id)
        media_type, width, height, size = validate_image_artifact(
            candidates[0],
            root=self.config.artifact_root,
            max_bytes=self.config.max_artifact_bytes,
            max_dimension=self.config.max_dimension,
            require_owner_only=True,
        )
        return ImageArtifact(
            artifact_id=artifact_id,
            path=candidates[0],
            media_type=media_type,
            width=width,
            height=height,
            byte_size=size,
        )

    def cancel(self, generation_id: str) -> None:
        with self._process_lock:
            self._cancelled.add(generation_id)
            process = self._processes.get(generation_id)
        if process is not None:
            self._stop_process(process)

    def generate(
        self,
        prompt: str,
        api_token_id: str,
        generation_id: str | None = None,
    ) -> ImageArtifact:
        if self.status()["state"] != "ready":
            raise RuntimeError("IMAGE_GENERATION_DISABLED_UNVERIFIED")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("image prompt must be nonempty")
        if len(prompt) > self.config.max_prompt_characters:
            raise ValueError("image prompt exceeds the configured limit")
        if redact(prompt) != prompt:
            raise ValueError("image prompt contains credential-shaped content")
        root = self.config.artifact_root
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root_metadata = root.lstat()
        if not stat.S_ISDIR(root_metadata.st_mode) or root_metadata.st_uid != os.getuid():
            raise ValueError("image artifact root must be an owner-controlled directory")
        os.chmod(root, 0o700)
        generation_id = generation_id or uuid.uuid4().hex
        if not (
            len(generation_id) == 32
            and all(character in "0123456789abcdef" for character in generation_id)
        ):
            raise ValueError("invalid image generation ID")
        started = self.clock()
        self.store.reserve(
            generation_id, api_token_id, self.config.max_calls_per_key_per_day
        )
        try:
            self._raise_if_cancelled(generation_id)
            artifact = self._generate_locked(prompt, generation_id)
        except Exception as error:
            failure_code = (
                str(error)
                if str(error).startswith("IMAGE_GENERATION_")
                else type(error).__name__
            )
            self.store.finish(
                generation_id,
                status="failed",
                latency_ms=(self.clock() - started) * 1_000,
                validation_status="failed",
                failure_code=failure_code,
            )
            raise
        finally:
            with self._process_lock:
                self._processes.pop(generation_id, None)
                self._cancelled.discard(generation_id)
        self.store.finish(
            generation_id,
            status="completed",
            latency_ms=(self.clock() - started) * 1_000,
            byte_size=artifact.byte_size,
            validation_status="passed",
        )
        return artifact

    def _generate_locked(self, prompt: str, generation_id: str) -> ImageArtifact:
        provider = CodexOAuthProvider(self.config.profile, self.profile_root)
        root = (
            profile_home(self.config.profile, self.profile_root)
            if self.profile_root is not None
            else profile_home(self.config.profile)
        )
        status = (
            profile_status(self.config.profile, self.profile_root)
            if self.profile_root is not None
            else profile_status(self.config.profile)
        )
        if status["authenticated"] != "yes":
            raise RuntimeError("IMAGE_GENERATION_OAUTH_UNAVAILABLE")
        generated_root = root / "generated_images"
        before = self._snapshot(generated_root)
        command = [
            "codex",
            "exec",
            "--json",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--model",
            "gpt-5.6-sol",
            "--cd",
            str(self.project_root),
            "-",
        ]
        task = (
            "$imagegen\nGenerate exactly one image for the following user request. "
            "Do not inspect the repository and do not emit or copy credentials.\n"
            + prompt
        )
        with profile_lock(self.config.profile, self.run_dir):
            self._raise_if_cancelled(generation_id)
            process = subprocess.Popen(
                command,
                cwd=self.project_root,
                env=provider.environment(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            with self._process_lock:
                self._processes[generation_id] = process
                cancelled = generation_id in self._cancelled
            if cancelled:
                self._stop_process(process)
            try:
                process.communicate(input=task, timeout=self.config.timeout_seconds)
            except subprocess.TimeoutExpired as error:
                self._stop_process(process)
                process.communicate()
                raise RuntimeError("IMAGE_GENERATION_TIMEOUT") from error
            self._raise_if_cancelled(generation_id)
            if process.returncode != 0:
                raise RuntimeError("IMAGE_GENERATION_PROVIDER_FAILURE")
            after = self._snapshot(generated_root)
            changed = [name for name in before if name in after and before[name] != after[name]]
            candidates = [generated_root / name for name in after.keys() - before.keys()]
            if changed or len(candidates) != 1:
                raise RuntimeError("IMAGE_GENERATION_ARTIFACT_COUNT_INVALID")
            source = candidates[0]
            if source.suffix.lower() not in ALLOWED_SUFFIXES:
                raise ValueError("unsupported image artifact suffix")
            media_type, width, height, _ = validate_image_artifact(
                source,
                root=generated_root,
                max_bytes=self.config.max_artifact_bytes,
                max_dimension=self.config.max_dimension,
            )
            generation_root = self.config.artifact_root / generation_id
            generation_root.mkdir(mode=0o700)
            destination = generation_root / ("artifact" + source.suffix.lower())
            try:
                self._copy_exclusive(source, destination)
                media_type, width, height, size = validate_image_artifact(
                    destination,
                    root=self.config.artifact_root,
                    max_bytes=self.config.max_artifact_bytes,
                    max_dimension=self.config.max_dimension,
                    require_owner_only=True,
                )
            except Exception:
                shutil.rmtree(generation_root)
                raise
        return ImageArtifact(
            artifact_id=generation_id,
            path=destination,
            media_type=media_type,
            width=width,
            height=height,
            byte_size=size,
        )

    def _raise_if_cancelled(self, generation_id: str) -> None:
        with self._process_lock:
            cancelled = generation_id in self._cancelled
        if cancelled:
            raise RuntimeError("IMAGE_GENERATION_CANCELLED")

    @staticmethod
    def _stop_process(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    @staticmethod
    def _snapshot(root: Path) -> dict[Path, tuple[int, int, int]]:
        if not root.is_dir():
            return {}
        snapshot: dict[Path, tuple[int, int, int]] = {}
        for path in root.rglob("*"):
            metadata = path.lstat()
            if stat.S_ISREG(metadata.st_mode):
                snapshot[path.relative_to(root)] = (
                    metadata.st_ino,
                    metadata.st_size,
                    metadata.st_mtime_ns,
                )
        return snapshot

    @staticmethod
    def _copy_exclusive(source: Path, destination: Path) -> None:
        source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            metadata = os.fstat(source_fd)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise ValueError("image source changed during validation")
            destination_fd = os.open(
                destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
            try:
                with (
                    os.fdopen(source_fd, "rb", closefd=False) as reader,
                    os.fdopen(destination_fd, "wb", closefd=False) as writer,
                ):
                    shutil.copyfileobj(reader, writer)
                    writer.flush()
                    os.fsync(writer.fileno())
            finally:
                os.close(destination_fd)
        finally:
            os.close(source_fd)
