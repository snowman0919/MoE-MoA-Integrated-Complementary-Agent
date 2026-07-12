from __future__ import annotations

from dgx_moa.context_tuning import (
    HEADROOM,
    candidate_vectors,
    next_larger_rejection,
    parse_vllm_capacity,
    select_best,
    stable,
    weighted_context_score,
)


def test_resident_headroom_is_10_gib() -> None:
    assert HEADROOM["resident"] == 10 * 1024**3


def result(contexts, *, headroom=30 * 1024**3, failure=None):  # type: ignore[no-untyped-def]
    value = {
        "profile": "resident",
        "contexts": contexts,
        "startup_attempts": 3,
        "readiness": True,
        "minimum_completion": True,
        "structured_output": True,
        "sequential_requests": 5,
        "near_limit": True,
        "service_restart": True,
        "responsive": True,
        "oom": False,
        "mem_available_bytes": headroom,
    }
    if failure:
        value["failure_reason"] = failure
    return value


def test_candidate_generation_respects_native_limits() -> None:
    candidates = candidate_vectors(
        "resident", {"executor": 32768, "planner": 16384, "reviewer": 12288, "reasoner": 8192}
    )
    assert {"executor": 32768, "planner": 16384, "reviewer": 12288, "reasoner": 8192} in candidates
    assert all(candidate["executor"] <= 32768 for candidate in candidates)


def test_vllm_result_parsing() -> None:
    parsed = parse_vllm_capacity(
        "GPU KV cache size: 17,829 tokens\nMaximum concurrency for 16,384 tokens per request: 1.09x"
    )
    assert parsed == {"kv_cache_tokens": 17829, "maximum_concurrency": 1.09}


def test_weighted_context_selection_prioritizes_executor() -> None:
    first = result({"executor": 32768, "planner": 8192, "reviewer": 8192, "reasoner": 8192})
    second = result({"executor": 24576, "planner": 16384, "reviewer": 16384, "reasoner": 8192})
    assert weighted_context_score(first["contexts"]) > weighted_context_score(second["contexts"])
    assert select_best([first, second], "resident") == first


def test_headroom_and_next_larger_rejection() -> None:
    selected = result({"executor": 24576, "planner": 8192, "reviewer": 8192, "reasoner": 8192})
    rejected = result(
        {"executor": 32768, "planner": 8192, "reviewer": 8192, "reasoner": 8192},
        headroom=9 * 1024**3,
        failure="headroom below 10 GiB",
    )
    assert stable(selected)
    assert not stable(rejected)
    assert next_larger_rejection(selected, [selected, rejected]) == rejected
