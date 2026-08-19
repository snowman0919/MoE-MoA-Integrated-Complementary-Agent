from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import suppress
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml
from huggingface_hub import HfApi, snapshot_download
from huggingface_hub.errors import LocalEntryNotFoundError

from .config import ModelConfig
from .model_download import verify_model
from .serve import _sglang_command

SGLANG_REVISION = "0111b290312aa224962397db86c04fe112539fb2"
MODELOPT_REVISION = "fbcdc16c2d67ca6db3f33b2848e923600f7012c7"
DEFAULT_DRAFT_ID = "RadixArk/Qwen3.8-27B-DSpark"
DEFAULT_DRAFT_REVISION = "85ef153be924f17ce4bf62726954eeaa4a73e854"
RUNTIME_ENVIRONMENT_BYTES = 25_000_000_000
DEFAULT_CALIBRATION_DATASET = "cnn_dailymail"
DEFAULT_CALIBRATION_SIZE = 128
PLAIN_CONTEXT_STAGES = (1_024, 32_768, 131_072, 256_000)


def atomic_write(path: Path, content: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "w") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def fingerprint(values: dict[str, Any]) -> str:
    encoded = json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate_hf_files(names: set[str], *, require_tokenizer: bool = True) -> None:
    missing = []
    if "config.json" not in names:
        missing.append("config.json")
    if require_tokenizer and not ({"tokenizer.json", "tokenizer_config.json"} & names):
        missing.append("tokenizer configuration")
    if not any(name.endswith(".safetensors") for name in names):
        missing.append("safetensors weights")
    if missing:
        raise ValueError("model repository is not a complete checkpoint: " + ", ".join(missing))


def resolve_model(
    repo_id: str, revision: str | None, *, require_tokenizer: bool = True
) -> dict[str, Any]:
    info = HfApi(token=os.getenv("HF_TOKEN")).model_info(
        repo_id, revision=revision, files_metadata=True
    )
    siblings = info.siblings or []
    names = {sibling.rfilename for sibling in siblings}
    validate_hf_files(names, require_tokenizer=require_tokenizer)
    return {
        "repo_id": repo_id,
        "revision": info.sha,
        "bytes": sum(int(sibling.size or 0) for sibling in siblings),
        "files": len(names),
    }


def run(command: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def ensure_venv(path: Path, requirements: list[str], marker: str) -> Path:
    python = path / "bin/python"
    stamp = path / ".dgx-moa-revision"
    if python.is_file() and stamp.is_file() and stamp.read_text().strip() == marker:
        return python
    if not python.is_file():
        run([sys.executable, "-m", "venv", str(path)])
    run([str(python), "-m", "pip", "install", "--upgrade", "pip"])
    run([str(python), "-m", "pip", "install", "--no-cache-dir", *requirements])
    atomic_write(stamp, marker + "\n")
    return python


def ensure_checkout(path: Path, repository: str, revision: str) -> None:
    if (path / ".git").is_dir():
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=path, check=True, text=True, capture_output=True
        ).stdout.strip()
        if head != revision:
            raise RuntimeError(f"managed checkout has unexpected revision: {path}")
        return
    path.mkdir(parents=True, exist_ok=True)
    run(["git", "init", "-q"], cwd=path)
    run(["git", "remote", "add", "origin", repository], cwd=path)
    run(["git", "fetch", "--depth=1", "origin", revision], cwd=path)
    run(["git", "checkout", "--detach", "FETCH_HEAD"], cwd=path)


def gpu_users() -> list[dict[str, str]]:
    completed = subprocess.run(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,process_name,used_memory",
            "--format=csv,noheader,nounits",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError("nvidia-smi compute-process query failed")
    users = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        pid, process, memory = (part.strip() for part in line.split(",", 2))
        users.append({"pid": pid, "process": process, "memory_mib": memory})
    return users


def verify_snapshot(destination: Path, *, draft: bool) -> dict[str, Any]:
    names = {path.name for path in destination.iterdir()} if destination.is_dir() else set()
    try:
        validate_hf_files(names, require_tokenizer=not draft)
    except ValueError as error:
        return {"status": "invalid", "errors": [str(error)]}
    return {"status": "verified", "errors": []}


def download_checkpoint(
    repo_id: str, revision: str, destination: Path, *, draft: bool = False
) -> Path:
    snapshot = Path(
        snapshot_download(
            repo_id=repo_id,
            revision=revision,
            token=os.getenv("HF_TOKEN"),
        )
    )
    verified = verify_snapshot(snapshot, draft=draft)
    if verified["status"] != "verified":
        raise RuntimeError(f"downloaded checkpoint is invalid: {verified['errors']}")
    if destination.is_symlink() and destination.resolve() == snapshot.resolve():
        return snapshot
    if destination.exists() or destination.is_symlink():
        raise RuntimeError(f"checkpoint link points to an unexpected snapshot: {destination}")
    destination.symlink_to(snapshot, target_is_directory=True)
    return snapshot


def cached_checkpoint(repo_id: str, revision: str) -> bool:
    try:
        snapshot_download(repo_id=repo_id, revision=revision, local_files_only=True)
    except LocalEntryNotFoundError:
        return False
    return True


def required_free_bytes(
    source: dict[str, Any],
    draft: dict[str, Any],
    *,
    runtime_environment_ready: bool = False,
    nvfp4_ready: bool = False,
) -> int:
    downloads = sum(
        int(model["bytes"])
        for model in (source, draft)
        if not cached_checkpoint(model["repo_id"], model["revision"])
    )
    environment = 0 if runtime_environment_ready else RUNTIME_ENVIRONMENT_BYTES
    output = 0 if nvfp4_ready else int(source["bytes"] * 0.65)
    return downloads + output + environment


def conversion_command(
    python: Path,
    checkout: Path,
    source: Path,
    destination: Path,
    *,
    calibration_dataset: str,
    calibration_size: int,
) -> list[str]:
    return [
        str(python),
        str(checkout / "examples/hf_ptq/hf_ptq.py"),
        "--pyt_ckpt_path",
        str(source),
        "--recipe",
        "general/ptq/nvfp4_default-kv_fp8_cast",
        "--export_path",
        str(destination),
        "--dataset",
        calibration_dataset,
        "--calib_size",
        str(calibration_size),
        "--trust_remote_code",
    ]


def convert_nvfp4(
    python: Path,
    checkout: Path,
    source: Path,
    destination: Path,
    provenance: dict[str, Any],
) -> dict[str, Any]:
    verified = verify_model(destination) if destination.exists() else {}
    manifest = destination / "dgx-moa-provenance.json"
    if (
        verified.get("status") == "verified"
        and manifest.is_file()
        and json.loads(manifest.read_text()) == provenance
    ):
        return verified
    partial = destination.with_name(destination.name + ".partial")
    if partial.exists():
        partial.rename(partial.with_name(partial.name + f".failed-{int(time.time())}"))
    run(
        conversion_command(
            python,
            checkout,
            source,
            partial,
            calibration_dataset=str(provenance["calibration_dataset"]),
            calibration_size=int(provenance["calibration_size"]),
        )
    )
    atomic_write(partial / ".revision", provenance["source_revision"] + "\n")
    atomic_write(partial / ".source-revision", provenance["source_revision"] + "\n")
    atomic_write(partial / "dgx-moa-provenance.json", json.dumps(provenance, indent=2) + "\n")
    verified = verify_model(partial)
    if verified["status"] != "verified":
        raise RuntimeError(f"NVFP4 export is invalid: {verified['errors']}")
    if destination.exists():
        raise RuntimeError(f"unverified destination already exists: {destination}")
    partial.rename(destination)
    return verify_model(destination)


def request_json(
    url: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    token: str | None = None,
    timeout: float = 30,
) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    with urlopen(
        Request(url, data=data, headers=headers, method=method), timeout=timeout
    ) as response:
        value = json.loads(response.read())
    if not isinstance(value, dict):
        raise RuntimeError(f"unexpected JSON response from {url}")
    return value


def wait_ready(base_url: str, model: str, process: subprocess.Popen[bytes], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"SGLang exited before readiness: {process.returncode}")
        try:
            result = request_json(base_url + "/v1/models")
            if any(item.get("id") == model for item in result.get("data", [])):
                return
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
            pass
        time.sleep(5)
    raise TimeoutError("SGLang readiness timeout")


def runtime_sglang_command(runtime_python: Path, model: ModelConfig) -> list[str]:
    command = _sglang_command("executor", model)
    command[0] = str(runtime_python)
    return command


def memory_snapshot(process_group: int) -> dict[str, int]:
    memory = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        memory[key] = int(value.split()[0]) * 1024
    rss = high_water = 0
    for stat in Path("/proc").glob("[0-9]*/stat"):
        try:
            fields = stat.read_text().rsplit(")", 1)[1].split()
            if int(fields[2]) != process_group:
                continue
            status = stat.with_name("status").read_text().splitlines()
            values = {line.split(":", 1)[0]: line.split()[1] for line in status if ":" in line}
            rss += int(values.get("VmRSS", 0)) * 1024
            high_water += int(values.get("VmHWM", 0)) * 1024
        except (FileNotFoundError, PermissionError, ProcessLookupError, ValueError):
            continue
    return {
        "system_total_bytes": memory["MemTotal"],
        "system_available_bytes": memory["MemAvailable"],
        "system_used_bytes": memory["MemTotal"] - memory["MemAvailable"],
        "system_cached_bytes": memory.get("Cached", 0),
        "system_sreclaimable_bytes": memory.get("SReclaimable", 0),
        "system_shmem_bytes": memory.get("Shmem", 0),
        "system_active_file_bytes": memory.get("Active(file)", 0),
        "system_inactive_file_bytes": memory.get("Inactive(file)", 0),
        "process_group_rss_bytes": rss,
        "process_group_high_water_bytes": high_water,
    }


def parse_sglang_memory(log_path: Path, start: int = 0) -> dict[str, float | int]:
    import re

    with log_path.open("rb") as source:
        source.seek(start)
        text = source.read().decode(errors="replace")
    result: dict[str, float | int] = {}
    matches = list(re.finditer(r"Load weight end\..*?mem usage=([0-9.]+) GB", text))
    if matches:
        weights = [float(match.group(1)) for match in matches]
        result.update(
            {
                "weight_memory_gb": weights[0],
                "target_weight_memory_gb": weights[0],
                "total_weight_memory_gb": round(sum(weights), 3),
            }
        )
        if len(weights) > 1:
            result["draft_weight_memory_gb"] = weights[1]
    matches = list(
        re.finditer(
            r"Mamba Cache is allocated\. max_mamba_cache_size: (\d+), "
            r"conv_state size: ([0-9.]+)GB, ssm_state size: ([0-9.]+)GB"
            r"(?: intermediate_ssm_state_cache size: ([0-9.]+)GB"
            r" intermediate_conv_window_cache size: ([0-9.]+)GB)?",
            text,
        )
    )
    if matches:
        match = matches[-1]
        values = [float(match.group(index) or 0) for index in range(2, 6)]
        result.update(
            {
                "mamba_slots": int(match.group(1)),
                "mamba_conv_gb": values[0],
                "mamba_ssm_gb": values[1],
                "mamba_intermediate_ssm_gb": values[2],
                "mamba_intermediate_conv_gb": values[3],
                "mamba_total_gb": round(sum(values), 3),
            }
        )
    matches = list(
        re.finditer(
            r"KV Cache is allocated\..*?#tokens: (\d+), K size: ([0-9.]+) GB, "
            r"V size: ([0-9.]+) GB",
            text,
        )
    )
    if matches:
        caches = [
            (int(match.group(1)), float(match.group(2)), float(match.group(3))) for match in matches
        ]
        target = caches[0]
        result.update(
            {
                "kv_token_capacity": target[0],
                "kv_k_gb": target[1],
                "kv_v_gb": target[2],
                "target_kv_token_capacity": target[0],
                "target_kv_k_gb": target[1],
                "target_kv_v_gb": target[2],
                "kv_total_gb": round(sum(k + v for _, k, v in caches), 3),
            }
        )
        if len(caches) > 1:
            draft = caches[1]
            result.update(
                {
                    "draft_kv_token_capacity": draft[0],
                    "draft_kv_k_gb": draft[1],
                    "draft_kv_v_gb": draft[2],
                }
            )
    return result


def reusable_smoke(
    path: Path,
    model: ModelConfig,
    context_stages: tuple[int, ...],
    minimum_headroom_bytes: int,
    *,
    log_path: Path | None = None,
) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        evidence: dict[str, Any] = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    try:
        actual_profile = ModelConfig.model_validate(evidence.get("profile", {})).model_dump(
            mode="json"
        )
    except ValueError:
        return None
    expected_profile = model.model_dump(mode="json")
    actual_profile["capabilities"] = sorted(actual_profile.get("capabilities", []))
    expected_profile["capabilities"] = sorted(expected_profile.get("capabilities", []))
    targets = [item.get("target_tokens") for item in evidence.get("context_stages", [])]
    headroom = evidence.get("memory", {}).get("minimum_system_available_bytes", 0)
    if (
        evidence.get("status") == "verified"
        and evidence.get("jit_compile_workers") == 1
        and actual_profile == expected_profile
        and targets == list(context_stages)
        and headroom >= minimum_headroom_bytes
    ):
        if log_path is not None and log_path.is_file():
            allocations = parse_sglang_memory(log_path, int(evidence.get("log_offset", 0)))
            if allocations != evidence.get("sglang_allocations"):
                evidence["sglang_allocations"] = allocations
                atomic_write(path, json.dumps(evidence, indent=2) + "\n")
        return evidence
    return None


def smoke_server(
    runtime_python: Path,
    model: ModelConfig,
    *,
    port: int,
    log_path: Path,
    evidence_path: Path,
    timeout: float,
    context_stages: tuple[int, ...],
    minimum_headroom_bytes: int,
) -> dict[str, Any]:
    candidate = model.model_copy(
        update={"base_url": f"http://127.0.0.1:{port}", "runtime_validated": True}
    )
    started = time.monotonic()
    evidence: dict[str, Any] = {
        "status": "running",
        "profile": model.model_dump(mode="json"),
        "jit_compile_workers": 1,
        "context_stages": [],
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_offset = log_path.stat().st_size if log_path.exists() else 0
    evidence["log_offset"] = log_offset
    samples = [memory_snapshot(-1)]
    with log_path.open("ab") as log:
        process = subprocess.Popen(
            runtime_sglang_command(runtime_python, candidate),
            env={
                **os.environ,
                "MAX_JOBS": "1",
                "FLASHINFER_MM_FP4_CUTE_DSL_COMPILE_WORKERS": "1",
            },
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        stop_sampling = threading.Event()
        headroom_breached = threading.Event()

        def sample_memory() -> None:
            while not stop_sampling.wait(0.5):
                snapshot = memory_snapshot(process.pid)
                samples.append(snapshot)
                if (
                    snapshot["system_available_bytes"] < minimum_headroom_bytes
                    and not headroom_breached.is_set()
                ):
                    headroom_breached.set()
                    evidence["headroom_violation"] = snapshot
                    with suppress(ProcessLookupError):
                        os.killpg(process.pid, signal.SIGTERM)

        sampler = threading.Thread(target=sample_memory, daemon=True)
        sampler.start()
        try:
            wait_ready(candidate.base_url, candidate.served_name, process, timeout)
            small = request_json(
                candidate.base_url + "/v1/chat/completions",
                method="POST",
                body={
                    "model": candidate.served_name,
                    "messages": [{"role": "user", "content": "Reply with READY."}],
                    "max_tokens": 1,
                },
                timeout=min(timeout, 600),
            )
            if not small.get("choices"):
                raise RuntimeError("minimal inference returned no choice")
            for target_tokens in context_stages:
                stage_started = time.monotonic()
                result = request_json(
                    candidate.base_url + "/v1/chat/completions",
                    method="POST",
                    body={
                        "model": candidate.served_name,
                        "messages": [{"role": "user", "content": "x " * target_tokens}],
                        "max_tokens": 1,
                    },
                    timeout=timeout,
                )
                if not result.get("choices"):
                    raise RuntimeError(f"{target_tokens}-token inference returned no choice")
                evidence["context_stages"].append(
                    {
                        "target_tokens": target_tokens,
                        "prompt_tokens": int(result.get("usage", {}).get("prompt_tokens", 0)),
                        "elapsed_seconds": round(time.monotonic() - stage_started, 3),
                    }
                )
            benchmark_started = time.monotonic()
            benchmark = request_json(
                candidate.base_url + "/v1/chat/completions",
                method="POST",
                body={
                    "model": candidate.served_name,
                    "messages": [{"role": "user", "content": "Count from one upward."}],
                    "max_tokens": 64,
                },
                timeout=min(timeout, 600),
            )
            benchmark_elapsed = time.monotonic() - benchmark_started
            completion_tokens = int(benchmark.get("usage", {}).get("completion_tokens", 0))
            if not benchmark.get("choices") or not completion_tokens:
                raise RuntimeError("decode benchmark returned no tokens")
            evidence["decode_benchmark"] = {
                "elapsed_seconds": round(benchmark_elapsed, 3),
                "completion_tokens": completion_tokens,
                "tokens_per_second": round(completion_tokens / benchmark_elapsed, 3),
            }
            evidence["status"] = "verified"
        except BaseException as error:
            evidence.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
            raise
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=120)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=30)
            stop_sampling.set()
            sampler.join(timeout=5)
            samples.append(memory_snapshot(process.pid))
            if samples:
                evidence["memory"] = {
                    "baseline": samples[0],
                    "peak_system_used_bytes": max(item["system_used_bytes"] for item in samples),
                    "minimum_system_available_bytes": min(
                        item["system_available_bytes"] for item in samples
                    ),
                    "peak_process_group_rss_bytes": max(
                        item["process_group_rss_bytes"] for item in samples
                    ),
                    "peak_process_group_high_water_bytes": max(
                        item["process_group_high_water_bytes"] for item in samples
                    ),
                    "final": samples[-1],
                }
            evidence["sglang_allocations"] = parse_sglang_memory(log_path, log_offset)
            evidence["elapsed_seconds"] = round(time.monotonic() - started, 3)
            atomic_write(evidence_path, json.dumps(evidence, indent=2) + "\n")
    minimum_available = int(evidence["memory"]["minimum_system_available_bytes"])
    if minimum_available < minimum_headroom_bytes:
        evidence.update(
            {
                "status": "failed",
                "error": f"minimum headroom {minimum_available} < {minimum_headroom_bytes}",
            }
        )
        atomic_write(evidence_path, json.dumps(evidence, indent=2) + "\n")
        raise RuntimeError(str(evidence["error"]))
    return evidence


def build_overlay(
    base: dict[str, Any],
    *,
    alias: str,
    source: dict[str, Any],
    destination: Path,
    draft_revision: str,
    draft_destination: Path,
    speculative_enabled: bool,
    decode_cuda_graph: bool = False,
    torch_compile: bool = False,
) -> dict[str, Any]:
    overlay = deepcopy(base)
    model = overlay["local_models"][alias]
    model.update(
        {
            "repository": source["repo_id"],
            "revision": source["revision"],
            "artifact_repository": None,
            "artifact_revision": None,
            "artifact_source_revision": None,
            "classification": "local-generated",
            "destination": str(destination),
            "quantization": "modelopt_fp4",
            "runtime_validated": True,
            "engine": "sglang",
            "gpu_memory_utilization": 0.35,
            "max_total_tokens": 270_000,
            "max_mamba_cache_size": 5,
            "chunked_prefill_size": 4_096,
            "disable_flashinfer_autotune": True,
            "disable_prefill_cuda_graph": True,
            "disable_decode_cuda_graph": not decode_cuda_graph,
            "enable_torch_compile": torch_compile,
            "torch_compile_max_bs": 4 if torch_compile else None,
            "skip_server_warmup": True,
            "watchdog_timeout": 1_800,
            "speculative": {
                "enabled": speculative_enabled,
                "method": "dspark",
                "model": str(draft_destination),
                "revision": draft_revision,
                "num_speculative_tokens": 8,
                "draft_attention_backend": "flashinfer",
            }
            | (
                {"draft_quantization": "unquant", "num_continuous_decode_steps": 2}
                if speculative_enabled
                else {}
            ),
        }
    )
    return overlay


def update_environment(content: str, values: dict[str, str]) -> str:
    lines = content.splitlines()
    replaced: set[str] = set()
    for index, line in enumerate(lines):
        key = line.split("=", 1)[0] if "=" in line and not line.lstrip().startswith("#") else ""
        if key in values:
            lines[index] = f"{key}={values[key]}"
            replaced.add(key)
    lines.extend(f"{key}={value}" for key, value in values.items() if key not in replaced)
    return "\n".join(lines) + "\n"


def wait_lifecycle(admin_url: str, token: str, role: str, phase: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = request_json(admin_url + "/v1/admin/local-models", token=token)
        record = next((item for item in result.get("data", []) if item.get("role") == role), None)
        if record and record.get("runtime_state") == phase:
            return
        if record and record.get("runtime_state") == "FAILED":
            raise RuntimeError(f"{role} lifecycle entered FAILED")
        time.sleep(5)
    raise TimeoutError(f"{role} lifecycle did not reach {phase}")


def lifecycle_phase(admin_url: str, token: str, role: str) -> str | None:
    result = request_json(admin_url + "/v1/admin/local-models", token=token)
    record = next((item for item in result.get("data", []) if item.get("role") == role), None)
    return str(record.get("runtime_state")) if record else None


def apply_runtime(
    env_file: Path,
    overlay_path: Path,
    runtime_python: Path,
    *,
    admin_url: str,
    role: str,
    timeout: float,
) -> None:
    token = os.getenv("DGX_MOA_ADMIN_API_KEY")
    if not token:
        raise RuntimeError("DGX_MOA_ADMIN_API_KEY is required for --apply and is never persisted")
    previous = env_file.read_text() if env_file.exists() else ""
    desired = update_environment(
        previous,
        {
            "DGX_MOA_CONFIG": str(overlay_path),
            "SGLANG_PYTHON": str(runtime_python),
            "MAX_JOBS": "1",
            "FLASHINFER_MM_FP4_CUTE_DSL_COMPILE_WORKERS": "1",
        },
    )
    if previous == desired and lifecycle_phase(admin_url, token, role) == "READY":
        return
    request_json(f"{admin_url}/v1/admin/local-models/{role}/off", method="POST", token=token)
    wait_lifecycle(admin_url, token, role, "DISABLED", timeout)
    try:
        atomic_write(
            env_file,
            desired,
        )
        request_json(f"{admin_url}/v1/admin/local-models/{role}/on", method="POST", token=token)
        wait_lifecycle(admin_url, token, role, "READY", timeout)
    except BaseException as apply_error:
        atomic_write(env_file, previous)
        request_json(f"{admin_url}/v1/admin/local-models/{role}/on", method="POST", token=token)
        try:
            wait_lifecycle(admin_url, token, role, "READY", timeout)
        except BaseException as rollback_error:
            raise RuntimeError(
                "runtime apply failed and the previous runtime did not return to READY"
            ) from rollback_error
        raise apply_error


def save_state(path: Path, state: dict[str, Any]) -> None:
    atomic_write(path, json.dumps(state, indent=2, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Idempotently prepare an HF checkpoint as NVFP4 + SGLang + DSpark"
    )
    parser.add_argument("model_id")
    parser.add_argument("--revision")
    parser.add_argument("--base-config", type=Path, default=Path("config/models.yaml"))
    parser.add_argument(
        "--root", type=Path, default=Path("/home/kotori9/models/dgx-moa/qwen-executor-builds")
    )
    parser.add_argument("--alias", default="qwen3.8-27b")
    parser.add_argument("--draft-id", default=DEFAULT_DRAFT_ID)
    parser.add_argument("--draft-revision", default=DEFAULT_DRAFT_REVISION)
    parser.add_argument("--calibration-dataset", default=DEFAULT_CALIBRATION_DATASET)
    parser.add_argument("--calibration-size", type=int, default=DEFAULT_CALIBRATION_SIZE)
    parser.add_argument(
        "--minimum-free-bytes",
        type=int,
        default=0,
        help="optional floor; default derives from uncached downloads, NVFP4 output, and one venv",
    )
    parser.add_argument("--timeout", type=float, default=7200)
    parser.add_argument("--minimum-headroom-bytes", type=int, default=20 * 1024**3)
    parser.add_argument("--through", choices=("plain", "graph", "dspark"), default="plain")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--admin-url", default="http://127.0.0.1:9000")
    parser.add_argument("--allow-busy-gpu", action="store_true")
    arguments = parser.parse_args()
    if arguments.apply and not arguments.env_file:
        parser.error("--apply requires an explicit --env-file")
    if arguments.apply and arguments.through != "dspark":
        parser.error("--apply requires --through dspark")
    if arguments.calibration_size < 1:
        parser.error("--calibration-size must be positive")

    try:
        source: dict[str, Any] = resolve_model(arguments.model_id, arguments.revision)
        draft: dict[str, Any] = resolve_model(
            arguments.draft_id, arguments.draft_revision, require_tokenizer=False
        )
    except ValueError as error:
        parser.error(str(error))
    identity = {
        "source": source,
        "draft": draft,
        "sglang_revision": SGLANG_REVISION,
        "modelopt_revision": MODELOPT_REVISION,
        "recipe": "general/ptq/nvfp4_default-kv_fp8_cast",
        "calibration_dataset": arguments.calibration_dataset,
        "calibration_size": arguments.calibration_size,
    }
    build_id = fingerprint(identity)[:16]
    build = arguments.root.expanduser() / build_id
    provenance = {
        "source_repository": source["repo_id"],
        "source_revision": source["revision"],
        "modelopt_revision": MODELOPT_REVISION,
        "recipe": identity["recipe"],
        "calibration_dataset": identity["calibration_dataset"],
        "calibration_size": identity["calibration_size"],
    }
    plan: dict[str, Any] = {
        "status": "planned" if not arguments.execute and not arguments.apply else "running",
        "build_id": build_id,
        "build_root": str(build),
        **identity,
    }
    if not arguments.execute and not arguments.apply:
        print(json.dumps(plan, indent=2))
        return

    build.mkdir(parents=True, exist_ok=True)
    state_path = build / "state.json"
    save_state(state_path, plan)
    runtime_root = (
        arguments.root / "venvs" / f"sglang-{SGLANG_REVISION[:8]}-modelopt-{MODELOPT_REVISION[:8]}"
    )
    runtime_marker = f"sglang={SGLANG_REVISION}\nmodelopt={MODELOPT_REVISION}"
    runtime_ready = (
        (runtime_root / "bin/python").is_file()
        and (runtime_root / ".dgx-moa-revision").is_file()
        and (runtime_root / ".dgx-moa-revision").read_text().strip() == runtime_marker
    )
    manifest = build / "nvfp4/dgx-moa-provenance.json"
    nvfp4_ready = manifest.is_file() and json.loads(manifest.read_text()) == provenance
    free_bytes = shutil.disk_usage(arguments.root.expanduser()).free
    required_bytes = max(
        arguments.minimum_free_bytes,
        required_free_bytes(
            source,
            draft,
            runtime_environment_ready=runtime_ready,
            nvfp4_ready=nvfp4_ready,
        ),
    )
    if free_bytes < required_bytes:
        plan.update(
            {
                "status": "capacity-blocked",
                "free_bytes": free_bytes,
                "required_free_bytes": required_bytes,
            }
        )
        save_state(state_path, plan)
        print(json.dumps(plan, indent=2))
        raise SystemExit(2)

    runtime_python = ensure_venv(
        runtime_root,
        [
            "sglang @ git+https://github.com/sgl-project/sglang.git@"
            f"{SGLANG_REVISION}#subdirectory=python",
            "nvidia-modelopt[hf] @ git+https://github.com/NVIDIA/Model-Optimizer.git@"
            f"{MODELOPT_REVISION}",
        ],
        runtime_marker,
    )
    checkout = arguments.root / "sources" / f"modelopt-{MODELOPT_REVISION[:12]}"
    ensure_checkout(checkout, "https://github.com/NVIDIA/Model-Optimizer.git", MODELOPT_REVISION)
    source_path = build / "source"
    draft_path = build / "draft"
    target_path = build / "nvfp4"
    download_checkpoint(source["repo_id"], source["revision"], source_path)
    users = gpu_users()
    if users and not arguments.allow_busy_gpu:
        plan.update({"status": "gpu-busy", "gpu_users": users})
        save_state(state_path, plan)
        print(json.dumps(plan, indent=2))
        raise SystemExit(2)
    convert_nvfp4(runtime_python, checkout, source_path, target_path, provenance)

    raw = yaml.safe_load(arguments.base_config.read_text())
    plain_raw = build_overlay(
        raw,
        alias=arguments.alias,
        source=source,
        destination=target_path,
        draft_revision=draft["revision"],
        draft_destination=draft_path,
        speculative_enabled=False,
    )
    plain_config = build / "plain-safe.yaml"
    atomic_write(plain_config, yaml.safe_dump(plain_raw, sort_keys=False))
    plain_model = ModelConfig.model_validate(plain_raw["local_models"][arguments.alias])
    plain_evidence = build / "plain-memory.json"
    plan["plain_smoke"] = reusable_smoke(
        plain_evidence,
        plain_model,
        PLAIN_CONTEXT_STAGES,
        arguments.minimum_headroom_bytes,
        log_path=build / "plain-sglang.log",
    ) or smoke_server(
        runtime_python,
        plain_model,
        port=19001,
        log_path=build / "plain-sglang.log",
        evidence_path=plain_evidence,
        timeout=arguments.timeout,
        context_stages=PLAIN_CONTEXT_STAGES,
        minimum_headroom_bytes=arguments.minimum_headroom_bytes,
    )
    save_state(state_path, plan)
    if arguments.through == "plain":
        plan.update({"status": "verified", "completed_through": "plain"})
        save_state(state_path, plan)
        print(json.dumps(plan, indent=2))
        return

    graph_raw = build_overlay(
        raw,
        alias=arguments.alias,
        source=source,
        destination=target_path,
        draft_revision=draft["revision"],
        draft_destination=draft_path,
        speculative_enabled=False,
        decode_cuda_graph=True,
    )
    graph_config = build / "plain-graph.yaml"
    atomic_write(graph_config, yaml.safe_dump(graph_raw, sort_keys=False))
    graph_model = ModelConfig.model_validate(graph_raw["local_models"][arguments.alias])
    graph_evidence = build / "plain-graph-memory.json"
    plan["graph_smoke"] = reusable_smoke(
        graph_evidence,
        graph_model,
        PLAIN_CONTEXT_STAGES,
        arguments.minimum_headroom_bytes,
        log_path=build / "plain-graph-sglang.log",
    ) or smoke_server(
        runtime_python,
        graph_model,
        port=19001,
        log_path=build / "plain-graph-sglang.log",
        evidence_path=graph_evidence,
        timeout=arguments.timeout,
        context_stages=PLAIN_CONTEXT_STAGES,
        minimum_headroom_bytes=arguments.minimum_headroom_bytes,
    )
    save_state(state_path, plan)
    if arguments.through == "graph":
        plan.update({"status": "verified", "completed_through": "graph"})
        save_state(state_path, plan)
        print(json.dumps(plan, indent=2))
        return

    download_checkpoint(draft["repo_id"], draft["revision"], draft_path, draft=True)
    dspark_raw = build_overlay(
        raw,
        alias=arguments.alias,
        source=source,
        destination=target_path,
        draft_revision=draft["revision"],
        draft_destination=draft_path,
        speculative_enabled=True,
        decode_cuda_graph=True,
        torch_compile=True,
    )
    overlay = build / "runtime.yaml"
    atomic_write(overlay, yaml.safe_dump(dspark_raw, sort_keys=False))
    dspark_model = ModelConfig.model_validate(dspark_raw["local_models"][arguments.alias])
    dspark_evidence = build / "dspark-memory.json"
    plan["dspark_smoke"] = reusable_smoke(
        dspark_evidence,
        dspark_model,
        PLAIN_CONTEXT_STAGES,
        arguments.minimum_headroom_bytes,
        log_path=build / "dspark-sglang.log",
    ) or smoke_server(
        runtime_python,
        dspark_model,
        port=19002,
        log_path=build / "dspark-sglang.log",
        evidence_path=dspark_evidence,
        timeout=arguments.timeout,
        context_stages=PLAIN_CONTEXT_STAGES,
        minimum_headroom_bytes=arguments.minimum_headroom_bytes,
    )
    save_state(state_path, plan)
    if arguments.apply:
        apply_runtime(
            arguments.env_file.expanduser(),
            overlay,
            runtime_python,
            admin_url=arguments.admin_url.rstrip("/"),
            role="executor",
            timeout=arguments.timeout,
        )
        plan["applied"] = True
    plan["status"] = "verified"
    save_state(state_path, plan)
    print(json.dumps(plan, indent=2))


if __name__ == "__main__":
    main()
