from __future__ import annotations

import argparse
import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from dgx_moa import live_client_validation as MODULE
from dgx_moa.config import load_settings


def base_settings():  # type: ignore[no-untyped-def]
    previous = os.environ.get("DGX_MOA_AUTH_ENABLED")
    os.environ["DGX_MOA_AUTH_ENABLED"] = "false"
    try:
        return load_settings(Path("config/models.yaml"))
    finally:
        if previous is None:
            os.environ.pop("DGX_MOA_AUTH_ENABLED", None)
        else:
            os.environ["DGX_MOA_AUTH_ENABLED"] = previous


def test_checked_in_config_uses_promoted_sglang_topology() -> None:
    models = base_settings().models
    assert models["executor"].base_url == "http://127.0.0.1:18101"
    assert models["executor"].revision == MODULE.EXECUTOR_REVISION
    assert models["planner"].base_url == models["reviewer"].base_url == "http://127.0.0.1:18102"
    assert (
        models["planner"].revision
        == models["reviewer"].revision
        == MODULE.SPECIALIST_REVISION
    )
    assert models["planner"].served_name == models["reviewer"].served_name


def test_candidate_gateway_pins_executor_and_unified_specialist() -> None:
    models = MODULE.candidate_models(
        base_settings(),
        "http://127.0.0.1:18101",
        "http://localhost:18102",
    )

    executor = models["executor"]
    assert executor.base_url == "http://127.0.0.1:18101"
    assert executor.served_name == "dgx-moa-executor-candidate"
    assert executor.revision == MODULE.EXECUTOR_REVISION

    planner, reviewer = models["planner"], models["reviewer"]
    assert planner.base_url == reviewer.base_url == "http://localhost:18102"
    assert planner.served_name == reviewer.served_name == "dgx-moa-specialist-candidate"
    assert planner.revision == reviewer.revision == MODULE.SPECIALIST_REVISION
    assert planner.repository == reviewer.repository == "nvidia/Gemma-4-26B-A4B-NVFP4"
    assert planner.context_length == reviewer.context_length == 65_536
    assert planner.quantization == reviewer.quantization == "modelopt_fp4"
    assert planner.reasoning_parser == reviewer.reasoning_parser == "gemma4"
    assert planner.tool_call_parser == reviewer.tool_call_parser == "gemma4"


@pytest.mark.parametrize(
    "endpoint",
    (
        "https://127.0.0.1:18101",
        "http://127.0.0.1:18101/v1",
        "http://user:secret@127.0.0.1:18101",
        "http://192.168.0.10:18101",
    ),
)
def test_candidate_gateway_rejects_non_loopback_endpoint(endpoint: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        MODULE.local_endpoint(endpoint)


def test_candidate_gateway_frontier_is_explicit_opt_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = []

    class Server:
        should_exit = False

        def __init__(self, _config) -> None:  # type: ignore[no-untyped-def]
            pass

        def run(self) -> None:
            while not self.should_exit:
                time.sleep(0.001)

    monkeypatch.setattr(
        MODULE, "create_app", lambda settings: captured.append(settings) or object()
    )
    monkeypatch.setattr(MODULE.uvicorn, "Server", Server)
    monkeypatch.setattr(MODULE.uvicorn, "Config", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        MODULE.httpx,
        "get",
        lambda *args, **kwargs: SimpleNamespace(status_code=200),
    )

    server, thread = MODULE.start_gateway(
        tmp_path,
        19300,
        "secret",
        "http://127.0.0.1:18101",
        "http://127.0.0.1:18102",
        frontier_enabled=True,
    )
    server.should_exit = True
    thread.join(timeout=1)

    assert captured[0].frontier_enabled is True
