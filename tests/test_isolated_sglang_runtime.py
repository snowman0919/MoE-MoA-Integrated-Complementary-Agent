from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from dgx_moa import isolated_sglang_validation as MODULE


def response(
    content: str = "",
    *,
    reasoning: str = "",
    cached: int = 0,
    tool_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "choices": [
            {
                "finish_reason": "tool_calls" if tool_calls else "stop",
                "message": {
                    "content": content,
                    "reasoning_content": reasoning,
                    "tool_calls": tool_calls,
                },
            }
        ],
        "usage": {
            "prompt_tokens": 200,
            "completion_tokens": 20,
            "total_tokens": 220,
            "prompt_tokens_details": {"cached_tokens": cached},
        },
    }


def planner_json() -> str:
    return json.dumps(
        {
            "scope": ["API"],
            "assumptions": [],
            "ordered_steps": [
                {
                    "step_id": "one",
                    "action": "migrate",
                    "dependencies": [],
                    "expected_evidence": ["tests"],
                }
            ],
            "dependencies": [],
            "risks": ["compatibility"],
            "validation_plan": ["tests"],
            "rollback_plan": ["revert"],
            "acceptance_criteria": ["green"],
        }
    )


def reviewer_json() -> str:
    return json.dumps(
        {
            "status": "rejected",
            "findings": [
                {
                    "finding_id": "race",
                    "severity": "important",
                    "category": "concurrency",
                    "evidence_references": ["shared dictionary"],
                    "affected_location": "cache",
                    "impact": "lost updates",
                    "required_correction": "add synchronization",
                    "optional_recommendation": None,
                }
            ],
        }
    )


def valid_runtime_snapshot() -> dict[str, Any]:
    common = {
        "available": True,
        "status": "running",
        "oom_killed": False,
        "image": MODULE.IMAGE,
    }
    return {
        "containers": {
            "executor": {
                **common,
                "model_revision": MODULE.EXECUTOR_REVISION,
                "ports": ["127.0.0.1:18101->18101/tcp"],
                "settings": {
                    "context-length": "65536",
                    "mem-fraction-static": "0.45",
                    "max-running-requests": "1",
                    "max-total-tokens": "65536",
                    "max-mamba-cache-size": "5",
                    "quantization": "modelopt_fp4",
                    "tool-call-parser": "qwen3_coder",
                    "radix-cache": True,
                    "metrics": True,
                    "cache-report": True,
                    "incremental-streaming": True,
                    "overlap-schedule": False,
                },
                "memory": {"memory_current_bytes": 6 * 1024**3},
            },
            "specialist": {
                **common,
                "model_revision": MODULE.SPECIALIST_REVISION,
                "ports": ["127.0.0.1:18102->18102/tcp"],
                "settings": {
                    "context-length": "65536",
                    "mem-fraction-static": "0.90",
                    "max-running-requests": "1",
                    "max-total-tokens": "65536",
                    "swa-full-tokens-ratio": "0.06",
                    "quantization": "modelopt_fp4",
                    "reasoning-parser": "gemma4",
                    "tool-call-parser": "gemma4",
                    "radix-cache": True,
                    "metrics": True,
                    "cache-report": True,
                    "incremental-streaming": True,
                    "overlap-schedule": True,
                },
                "memory": {"memory_current_bytes": 30 * 1024**3},
            },
        },
        "gpu": [],
        "memory": {
            "memavailable_kib": 12 * 1024**2,
            "memtotal_kib": 125_441_420,
        },
    }


def test_runtime_validator_covers_real_contract_without_retaining_payloads(monkeypatch) -> None:
    cache_calls = 0
    structured_payloads: list[dict[str, Any]] = []

    def fake_post(
        _url: str, payload: dict[str, Any], _timeout: float
    ) -> tuple[dict[str, Any], float]:
        nonlocal cache_calls
        prompt = payload["messages"][-1]["content"]
        all_content = " ".join(str(item.get("content") or "") for item in payload["messages"])
        if payload.get("tools"):
            name = payload["tools"][0]["function"]["name"]
            field, value = ("path", "README.md") if name == "inspect_file" else ("risk", "race")
            return response(
                tool_calls=[
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps({field: value})},
                    }
                ]
            ), 0.1
        if payload.get("response_format"):
            structured_payloads.append(payload)
            content = planner_json() if "API migration" in all_content else reviewer_json()
            return response(content), 0.2
        if "API migration" in all_content or "shared dictionary" in all_content:
            structured_payloads.append(payload)
            return response("", reasoning="private analysis"), 0.2
        if "17 * 19" in prompt:
            return response("323", reasoning="private arithmetic"), 0.1
        if "Radix validation" in prompt:
            cache_calls += 1
            return response("4", cached=0 if cache_calls == 1 else 3000), 0.1
        if "2+2" in prompt:
            return response("4"), 0.1
        marker = "EXECUTOR_READY" if "EXECUTOR_READY" in prompt else "SPECIALIST_READY"
        return response(marker), 0.1

    monkeypatch.setattr(MODULE, "post_json", fake_post)
    monkeypatch.setattr(
        MODULE,
        "get_json",
        lambda url, _timeout: (
            {
                "data": [
                    {
                        "id": (
                            "dgx-moa-executor-candidate"
                            if "18101" in url
                            else "dgx-moa-specialist-candidate"
                        )
                    }
                ]
            },
            0.01,
        ),
    )
    monkeypatch.setattr(
        MODULE,
        "stream_json",
        lambda *_args: {
            "latency_seconds": 0.1,
            "chunks": 2,
            "done": True,
            "marker": True,
        },
    )
    monkeypatch.setattr(
        MODULE,
        "runtime_snapshot",
        valid_runtime_snapshot,
    )
    monkeypatch.setattr(
        MODULE,
        "get_text",
        lambda _url, _timeout: (
            'sglang:max_total_num_tokens{model_name="dgx-moa-executor-candidate"} '
            "65536\n"
            'sglang:max_total_num_tokens{model_name="dgx-moa-specialist-candidate"} '
            "65536\n"
        ),
    )

    result = MODULE.run_validation("http://127.0.0.1:18101", "http://localhost:18102", 1)

    assert result["passed"] is True
    assert result["checks"]["executor_radix_cache"]["second_cached_tokens"] == 3000
    assert [payload["max_tokens"] for payload in structured_payloads] == [768, 1536, 768, 1536]
    assert [
        payload["chat_template_kwargs"]["enable_thinking"]
        for payload in structured_payloads
    ] == [True, False, True, False]
    rendered = json.dumps(result)
    for private in ("private analysis", "private arithmetic", "API migration", "shared dictionary"):
        assert private not in rendered


def test_runtime_contract_rejects_low_headroom_and_oom() -> None:
    snapshot = valid_runtime_snapshot()

    assert MODULE.runtime_contract(snapshot)["host_memory_available_gib"] == 12.0

    snapshot["memory"]["memavailable_kib"] = 10 * 1024**2 - 1
    with pytest.raises(RuntimeError, match="host_memory_headroom_below_minimum"):
        MODULE.runtime_contract(snapshot)

    snapshot = valid_runtime_snapshot()
    snapshot["containers"]["specialist"]["oom_killed"] = True
    with pytest.raises(RuntimeError, match="runtime_contract_mismatch"):
        MODULE.runtime_contract(snapshot)


def test_runtime_validator_skips_inference_when_contract_is_unsafe(monkeypatch) -> None:
    snapshot = valid_runtime_snapshot()
    snapshot["memory"]["memavailable_kib"] = 1
    monkeypatch.setattr(MODULE, "runtime_snapshot", lambda: snapshot)
    monkeypatch.setattr(
        MODULE,
        "post_json",
        lambda *_args, **_kwargs: pytest.fail("unsafe inference dispatched"),
    )
    monkeypatch.setattr(
        MODULE,
        "get_json",
        lambda url, _timeout: (
            {
                "data": [
                    {
                        "id": (
                            "dgx-moa-executor-candidate"
                            if "18101" in url
                            else "dgx-moa-specialist-candidate"
                        )
                    }
                ]
            },
            0.01,
        ),
    )
    monkeypatch.setattr(
        MODULE,
        "get_text",
        lambda _url, _timeout: (
            'sglang:max_total_num_tokens{model_name="dgx-moa-executor-candidate"} '
            "65536\n"
            'sglang:max_total_num_tokens{model_name="dgx-moa-specialist-candidate"} '
            "65536\n"
        ),
    )

    result = MODULE.run_validation("http://127.0.0.1:18101", "http://127.0.0.1:18102", 1)

    assert result["passed"] is False
    assert result["checks"]["executor_readiness"] == {
        "status": "skipped",
        "failure": "unsafe_runtime_contract",
    }


def test_expected_catalog_rejects_wrong_served_model(monkeypatch) -> None:
    monkeypatch.setattr(
        MODULE,
        "get_json",
        lambda _url, _timeout: ({"data": [{"id": "wrong-model"}]}, 0.01),
    )

    with pytest.raises(RuntimeError, match="model_catalog_mismatch"):
        MODULE.expected_catalog("http://127.0.0.1:18101", "expected-model", 1)


@pytest.mark.parametrize(
    "endpoint",
    (
        "https://127.0.0.1:18101",
        "http://127.0.0.1:18101/v1",
        "http://user:secret@127.0.0.1:18101",
        "http://192.168.0.10:18101",
        "file://127.0.0.1/tmp/socket",
    ),
)
def test_runtime_validator_rejects_non_candidate_endpoints(endpoint: str) -> None:
    with pytest.raises(MODULE.argparse.ArgumentTypeError):
        MODULE.local_endpoint(endpoint)


def test_runtime_validator_fails_closed_when_reasoning_or_cache_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        MODULE,
        "completion",
        lambda *_args, **_kwargs: (response("323"), 0.1),
    )

    reasoning = MODULE.checked(lambda: MODULE.reasoning("http://127.0.0.1:18102", "candidate", 1))

    assert reasoning == {
        "status": "failed",
        "error_type": "RuntimeError",
        "failure": "reasoning_split_failure",
    }


def test_runtime_validator_redacts_unknown_failure_text() -> None:
    result = MODULE.checked(lambda: (_ for _ in ()).throw(RuntimeError("private output")))

    assert result == {
        "status": "failed",
        "error_type": "RuntimeError",
        "failure": "check_failed",
    }


def test_stream_validator_accepts_marker_split_across_sse_chunks(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def __iter__(self):  # type: ignore[no-untyped-def]
            events = (
                {"choices": [{"delta": {"content": "STREAM_"}}]},
                {"choices": [{"delta": {"content": "OK"}}]},
                {
                    "choices": [],
                    "usage": {
                        "prompt_tokens": 4,
                        "completion_tokens": 2,
                        "total_tokens": 6,
                    },
                },
            )
            lines = [f"data: {json.dumps(event)}\n\n".encode() for event in events]
            return iter([*lines, b"data: [DONE]\n\n"])

    monkeypatch.setattr(MODULE, "urlopen", lambda *_args, **_kwargs: FakeResponse())

    result = MODULE.stream_json("http://127.0.0.1:18101/v1/chat/completions", {}, 1)

    assert result["marker"] is True
    assert result["done"] is True
    assert result["total_tokens"] == 6


def test_process_memory_reads_cgroup_and_process_usage(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    cgroup = tmp_path / "cgroup"
    (proc / "42").mkdir(parents=True)
    (cgroup / "candidate").mkdir(parents=True)
    (proc / "42" / "status").write_text("VmRSS: 123 kB\nVmSwap: 7 kB\n")
    (proc / "42" / "cgroup").write_text("0::/candidate\n")
    (cgroup / "candidate" / "memory.current").write_text("456")
    (cgroup / "candidate" / "memory.peak").write_text("789")
    (cgroup / "candidate" / "memory.swap.current").write_text("12")

    assert MODULE.process_memory(42, proc, cgroup) == {
        "process_vmrss_kib": 123,
        "process_vmswap_kib": 7,
        "memory_current_bytes": 456,
        "memory_peak_bytes": 789,
        "memory_swap_current_bytes": 12,
    }
