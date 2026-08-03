from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .config import ModelConfig, load_settings, parse_bool

PORTS = {"executor": 8101, "planner": 8102, "reviewer": 8103, "reasoner": 8104, "judge": 8110}
KV_CACHE = {
    "executor": 1_700_000_000,
    "planner": 600_000_000,
    "reviewer": 2_300_000_000,
    "reasoner": 2_450_000_000,
    "judge": 4_000_000_000,
}
GPU_UTILIZATION = {
    "executor": 0.50,
    "planner": 0.25,
    "reviewer": 0.25,
    "reasoner": 0.10,
    "judge": 0.85,
}


def role_environment(role: str, name: str, default: str | int | float) -> str:
    return os.getenv(f"DGX_MOA_{role.upper()}_{name}", str(default))


def role_bool_environment(role: str, name: str, default: bool = False) -> bool:
    return parse_bool(os.getenv(f"DGX_MOA_{role.upper()}_{name}", str(default)))


def role_context_length(role: str, configured: int) -> str:
    return role_environment(role, "MAX_MODEL_LEN", configured)


def vllm_command(role: str, model: ModelConfig, run_dir: Path) -> list[str]:
    arguments = [
        os.path.expanduser(os.getenv("VLLM_BIN", "~/.pyenv/shims/vllm")),
        "serve",
        str(model.destination),
        "--host",
        "127.0.0.1",
        "--port",
        str(PORTS[role]),
        "--served-model-name",
        model.served_name,
        "--max-model-len",
        role_context_length(role, model.context_length),
        "--max-num-seqs",
        os.getenv("DGX_MOA_MAX_NUM_SEQS", str(model.max_num_seqs)),
        "--kv-cache-memory-bytes",
        role_environment(role, "KV_CACHE_MEMORY_BYTES", KV_CACHE[role]),
        "--gpu-memory-utilization",
        role_environment(role, "GPU_MEMORY_UTILIZATION", GPU_UTILIZATION[role]),
    ]
    if model.trust_remote_code:
        arguments.append("--trust-remote-code")
    if role_bool_environment(role, "ENFORCE_EAGER"):
        arguments.append("--enforce-eager")
    if moe_backend := os.getenv(
        f"DGX_MOA_{role.upper()}_MOE_BACKEND",
        "MARLIN" if role == "executor" else "",
    ):
        arguments += ["--moe-backend", moe_backend]
    if role == "reviewer":
        source = model.destination / "config.json"
        patched = json.loads(source.read_text())
        patched["model_type"] = "cohere2"
        destination = run_dir / "reviewer-hf-config"
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "config.json").write_text(json.dumps(patched))
        arguments += ["--hf-config-path", str(destination)]
    if model.quantization == "modelopt_fp4":
        arguments += ["--quantization", "modelopt_fp4"]
    if model.reasoning_parser:
        arguments += ["--reasoning-parser", model.reasoning_parser]
    if role == "executor" and model.tool_call_parser:
        arguments += ["--enable-auto-tool-choice", "--tool-call-parser", model.tool_call_parser]
    if role == "executor" and model.lora_adapter:
        arguments += ["--enable-lora", "--lora-modules", f"executor={model.lora_adapter}"]
    return arguments


def sglang_executor_command(model: ModelConfig) -> list[str]:
    arguments = [
        os.path.expanduser(os.getenv("SGLANG_BIN", "~/.pyenv/shims/sglang")),
        "serve",
        "--model-path",
        str(model.destination),
        "--host",
        "127.0.0.1",
        "--port",
        str(PORTS["executor"]),
        "--served-model-name",
        model.served_name,
        "--context-length",
        role_context_length("executor", model.context_length),
        "--mem-fraction-static",
        role_environment("executor", "SGLANG_MEM_FRACTION_STATIC", 0.60),
        "--max-running-requests",
        role_environment("executor", "SGLANG_MAX_RUNNING_REQUESTS", model.max_num_seqs),
        "--max-total-tokens",
        role_environment("executor", "SGLANG_MAX_TOTAL_TOKENS", model.context_length),
        "--max-mamba-cache-size",
        role_environment("executor", "SGLANG_MAX_MAMBA_CACHE_SIZE", 16),
        "--quantization",
        model.quantization or "compressed-tensors",
        "--enable-metrics",
        "--enable-cache-report",
    ]
    if model.trust_remote_code:
        arguments.append("--trust-remote-code")
    if model.tool_call_parser:
        arguments += ["--tool-call-parser", model.tool_call_parser]
    return arguments


def command(role: str) -> list[str]:
    settings = load_settings()
    model = settings.models[role]
    if role != "executor":
        return vllm_command(role, model, settings.run_dir)
    backend = os.getenv("DGX_MOA_EXECUTOR_BACKEND", "vllm").strip().lower()
    if backend == "vllm":
        return vllm_command(role, model, settings.run_dir)
    if backend == "sglang":
        return sglang_executor_command(model)
    raise ValueError(f"unsupported executor backend: {backend}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=PORTS)
    parser.add_argument("--print", action="store_true")
    arguments = parser.parse_args()
    built = command(arguments.role)
    if arguments.print:
        print(" ".join(built))
        return
    os.execv(built[0], built)


if __name__ == "__main__":
    main()
