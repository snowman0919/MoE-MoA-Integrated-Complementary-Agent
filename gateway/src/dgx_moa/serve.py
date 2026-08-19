from __future__ import annotations

import argparse
import json
import os
from urllib.parse import urlsplit

from .config import ModelConfig, Settings, load_settings, parse_bool

PORTS = {"executor": 8101, "planner": 8102, "reviewer": 8103, "reasoner": 8104, "judge": 8110}
KV_CACHE = {
    "executor": 3_400_000_000,
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


def _sglang_command(role: str, model: ModelConfig) -> list[str]:
    arguments = [
        os.path.expanduser(os.getenv("SGLANG_PYTHON", "~/.pyenv/shims/python")),
        "-m",
        "sglang.launch_server",
        "--model-path",
        str(model.destination),
        "--host",
        "127.0.0.1",
        "--port",
        str(urlsplit(model.base_url).port or PORTS[role]),
        "--served-model-name",
        model.served_name,
        "--context-length",
        role_context_length(role, model.context_length),
        "--max-running-requests",
        os.getenv("DGX_MOA_MAX_NUM_SEQS", str(model.max_num_seqs)),
        "--mem-fraction-static",
        role_environment(role, "GPU_MEMORY_UTILIZATION", model.gpu_memory_utilization or 0.5),
    ]
    for flag, value in (
        ("--attention-backend", model.attention_backend),
        ("--kv-cache-dtype", model.kv_cache_dtype),
        ("--max-total-tokens", model.max_total_tokens),
        ("--max-mamba-cache-size", model.max_mamba_cache_size),
        ("--chunked-prefill-size", model.chunked_prefill_size),
        ("--cuda-graph-max-bs", model.cuda_graph_max_bs),
        ("--reasoning-parser", model.reasoning_parser),
        ("--tool-call-parser", model.tool_call_parser),
        ("--watchdog-timeout", model.watchdog_timeout),
    ):
        if value is not None:
            arguments += [flag, str(value)]
    if model.trust_remote_code:
        arguments.append("--trust-remote-code")
    if model.disable_flashinfer_autotune:
        arguments.append("--disable-flashinfer-autotune")
    if model.disable_prefill_cuda_graph:
        arguments.append("--disable-prefill-cuda-graph")
    if model.disable_decode_cuda_graph:
        arguments.append("--disable-decode-cuda-graph")
    if model.enable_torch_compile:
        arguments.append("--enable-torch-compile")
    if model.torch_compile_max_bs is not None:
        arguments += ["--torch-compile-max-bs", str(model.torch_compile_max_bs)]
    if model.skip_server_warmup:
        arguments.append("--skip-server-warmup")
    if model.quantization == "modelopt_fp4":
        arguments += ["--quantization", "modelopt_fp4"]
    if model.speculative.enabled:
        arguments += [
            "--speculative-algorithm",
            model.speculative.method.upper(),
            "--speculative-draft-model-path",
            str(model.speculative.model),
            "--speculative-draft-model-revision",
            str(model.speculative.revision),
        ]
        if model.speculative.draft_attention_backend:
            arguments += [
                "--speculative-draft-attention-backend",
                model.speculative.draft_attention_backend,
            ]
        if model.speculative.draft_quantization:
            arguments += [
                "--speculative-draft-model-quantization",
                model.speculative.draft_quantization,
            ]
        arguments += [
            "--num-continuous-decode-steps",
            str(model.speculative.num_continuous_decode_steps),
        ]
        if model.speculative.num_speculative_tokens:
            arguments += [
                "--speculative-dspark-block-size",
                str(model.speculative.num_speculative_tokens - 1),
            ]
    return arguments


def _vllm_command(role: str, model: ModelConfig, settings: Settings) -> list[str]:
    arguments = [
        os.path.expanduser(os.getenv("VLLM_BIN", "~/.pyenv/shims/vllm")),
        "serve",
        str(model.destination),
        "--host",
        "127.0.0.1",
        "--port",
        str(urlsplit(model.base_url).port or PORTS[role]),
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
    if role == "executor":
        if linear_backend := role_environment(role, "LINEAR_BACKEND", ""):
            arguments += ["--linear-backend", linear_backend]
        arguments += [
            "--attention-backend",
            role_environment(role, "ATTENTION_BACKEND", "TRITON_MLA"),
            "--safetensors-load-strategy",
            "lazy",
            "--compilation-config",
            role_environment(role, "COMPILATION_CONFIG", '{"cudagraph_mode":"FULL_DECODE_ONLY"}'),
        ]
    if role_bool_environment(role, "ENFORCE_EAGER"):
        arguments.append("--enforce-eager")
    if moe_backend := os.getenv(
        f"DGX_MOA_{role.upper()}_MOE_BACKEND",
        "flashinfer_b12x" if role == "executor" else "",
    ):
        arguments += ["--moe-backend", moe_backend]
    if role == "reviewer":
        source = model.destination / "config.json"
        patched = json.loads(source.read_text())
        patched["model_type"] = "cohere2"
        destination = settings.run_dir / "reviewer-hf-config"
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


def command(role: str) -> list[str]:
    settings = load_settings()
    model = settings.models[role]
    if model.engine == "sglang":
        return _sglang_command(role, model)
    return _vllm_command(role, model, settings)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=PORTS)
    parser.add_argument("--print", action="store_true")
    arguments = parser.parse_args()
    settings = load_settings()
    if not arguments.print and not settings.models[arguments.role].runtime_validated:
        raise SystemExit(f"{arguments.role} runtime is not physically validated")
    built = command(arguments.role)
    if arguments.print:
        print(" ".join(built))
        return
    os.execv(built[0], built)


if __name__ == "__main__":
    main()
