from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from dgx_moa.adapters import evaluate, register
from dgx_moa.benchmark import TASKS, benchmark_models, summarize
from dgx_moa.dataset import build, quality_tier
from dgx_moa.improvement import compare, mine, statistics


def read_required_doc(path: str) -> str:
    document = Path(path)
    assert document.is_file(), f"missing documentation contract: {path}"
    return document.read_text()


def test_model_lifecycle_documentation_contract() -> None:
    lifecycle = read_required_doc("docs/MODEL_LIFECYCLE.md")

    for state in (
        "cold",
        "load_queued",
        "process_starting",
        "loading_weights",
        "initializing_engine",
        "warming_up",
        "ready",
        "sleeping",
        "unloading",
        "failed",
    ):
        assert f"`{state}`" in lifecycle
    for value in (
        "Retry-After",
        "X-DGX-MOA-Model-State",
        "X-DGX-MOA-Weight-Load-Percent",
        "model_loading",
        "model_state",
        "weight_load_percent",
        "progress_quality",
        "overall_load_percent",
        "estimated_ready_seconds",
        "measured_bytes",
        "measured_shards",
        "estimated",
        "unavailable",
    ):
        assert value in lifecycle
    assert "100%" in lifecycle
    assert "engine initialization" in lifecycle.lower()
    assert "warmup" in lifecycle.lower()

    for mode in ("disabled", "observe", "fixed", "adaptive"):
        assert f"`{mode}`" in lifecycle
    assert "two consecutive" in lifecycle.lower()
    assert "optional" in lifecycle.lower() and "before `executor`" in lifecycle
    assert "minimum residency" in lifecycle.lower()
    assert "inclusive p75" in lifecycle.lower()
    assert "1.5" in lifecycle
    assert "20 usable positive role-local gaps" in lifecycle
    assert "| Executor | 7200 | 14400 | 28800 | 600 |" in lifecycle
    assert "| Planner | 600 | 1200 | 3600 | 600 |" in lifecycle
    assert "| Reviewer | 600 | 1200 | 3600 | 600 |" in lifecycle
    assert "| Reasoner (external) | n/a | n/a | n/a | n/a |" in lifecycle
    assert "external Reasoner" in lifecycle and "outside local idle automation" in lifecycle
    assert "idle unload is disabled by default" in lifecycle
    assert "30-second" in lifecycle
    assert "`lifecycle_mode: disabled`" in lifecycle
    assert "`lifecycle_unit_map: {}`" in lifecycle


def test_model_lifecycle_safety_and_status_contract() -> None:
    lifecycle = read_required_doc("docs/MODEL_LIFECYCLE.md")

    for value in (
        "lifecycle_unit_map",
        "unique",
        "dgx-moa-dev-",
        "full service stop",
        "active request",
        "open stream",
        "unexpired tool continuation",
        "evaluation guard",
        "profile guard",
        "transient state",
        "atomic recheck",
        "single-flight",
        "/v1/model-status",
        "/v1/model-status/{role}",
        "/v1/admin/runtime-status",
        "/admin/profile",
        "/admin/profile/resident",
        "/admin/profile/judge",
        "/admin/profile/restore",
        "current-mode",
        "content-free",
        "shutdown",
        "rollback",
    ):
        assert value in lifecycle
    assert "only implemented unload action" in lifecycle.lower()
    assert "status reads never call the lifecycle driver" in lifecycle.lower()
    assert "failed" in lifecycle and "unmanaged" in lifecycle and "503" in lifecycle
    assert "disabled mode and an empty unit map" in lifecycle.lower()
    normalized_lifecycle = " ".join(lifecycle.lower().split())
    assert "no detached lifecycle work remains" not in normalized_lifecycle
    for boundary in (
        "scheduler and load tasks",
        "load driver capture/start work",
        "admitted unload stop task",
        "bounded read-only status/progress probes",
        "may finish after parent cancellation",
    ):
        assert boundary in normalized_lifecycle
    assert "request bodies cannot supply a unit, path, command" not in normalized_lifecycle
    assert (
        "inference request fields and content are never consulted for lifecycle "
        "unit/path/command authorization or driver argument vectors" in normalized_lifecycle
    )
    assert (
        "only validated settings and `lifecycle_unit_map` authorize lifecycle driver targets"
        in normalized_lifecycle
    )
    assert "authorized service is inactive" not in normalized_lifecycle
    for cold_boundary in (
        "`cold` record is persisted controller state",
        "not standalone proof that its service is inactive",
        "`fixed`/`adaptive` startup reconciliation",
        "successful full stop",
        "verifies inactive status",
    ):
        assert cold_boundary in normalized_lifecycle


def test_lifecycle_docs_link_canonical_contract_and_keep_evidence_pending() -> None:
    lifecycle = read_required_doc("docs/MODEL_LIFECYCLE.md")
    related = {
        path: read_required_doc(path)
        for path in (
            "README.md",
            "docs/STATE.md",
            "docs/OPERATIONS.md",
            "docs/ARCHITECTURE.md",
            "docs/TRACE_SCHEMA.md",
            "docs/DECISIONS.md",
        )
    }
    for text in related.values():
        assert "MODEL_LIFECYCLE.md" in text

    checked_in = yaml.safe_load(Path("config/models.yaml").read_text())["gateway"]
    assert checked_in["lifecycle_mode"] == "disabled"
    assert checked_in["lifecycle_unit_map"] == {}
    assert "527 passed" in related["docs/STATE.md"]
    for variable in (
        "DGX_MOA_LIFECYCLE_MODE",
        "DGX_MOA_LIFECYCLE_POLL_SECONDS",
        "DGX_MOA_LIFECYCLE_UNIT_MAP",
        "DGX_MOA_RUNTIME_CHANNEL",
        "DGX_MOA_STATE_DB",
    ):
        assert variable in related["docs/OPERATIONS.md"]
    isolated_operations = (
        related["docs/OPERATIONS.md"]
        .split("## Isolated lifecycle development", 1)[1]
        .split("## Profiles", 1)[0]
    )
    assert "DGX_MOA_BIND_HOST=127.0.0.1" in isolated_operations
    assert "run_dir: /path/to/isolated-dev/run" in isolated_operations
    assert "DGX_MOA_RUN_DIR" not in isolated_operations
    for component in ("LifecycleCoordinator", "LifecycleStore", "SystemdLifecycleDriver"):
        assert component in related["docs/ARCHITECTURE.md"]
    for table in ("request_usage", "model_lifecycle_decisions", "lifecycle_samples"):
        assert table in related["docs/TRACE_SCHEMA.md"]
    trace_schema = related["docs/TRACE_SCHEMA.md"]
    assert "raw prompt" in trace_schema.lower()
    assert "`load_triggered`" in trace_schema
    lifecycle_sample_contract = trace_schema.split("`lifecycle_samples`", 1)[1].split("\n\n", 1)[0]
    assert "cold-start" not in lifecycle_sample_contract
    for field in ("role", "kind", "duration", "memory"):
        assert field in lifecycle_sample_contract

    pending = lifecycle.split("## Pending physical evidence", 1)
    assert len(pending) == 2
    for evidence in (
        "real-weight cold-load and progress",
        "memory bytes",
        "idle-unload guards under real-weight",
        "mechanism comparison",
        "64K physical quality",
        "production recommendation",
    ):
        assert evidence in pending[1]


def test_api_client_mode_documentation() -> None:
    api_modes = Path("docs/API_CLIENT_MODES.md").read_text()
    hermes = Path("docs/HERMES_AGENT.md").read_text()
    for alias in ("dgx-moa", "dgx-moa-fast", "dgx-moa-agent", "dgx-moa-orchestrated"):
        assert alias in api_modes
    assert "http://100.125.239.72:9000/v1" in hermes
    assert "DGX_MOA_API_KEY" in hermes
    assert "127.0.0.1:9000" not in hermes
    assert "Tailscale Serve" not in hermes


def test_external_reasoner_uses_requested_q4_model() -> None:
    reasoner = yaml.safe_load(Path("config/models.yaml").read_text())["models"]["reasoner"]
    assert reasoner["revision"] == "Q4"
    assert reasoner["served_name"] == "Qwythos-v2-9B:Q4"
    assert reasoner["provider"] == "ollama"
    assert reasoner["lifecycle_control"] == "external"


def test_hermes_documentation_matches_physical_config() -> None:
    hermes = Path("docs/HERMES_AGENT.md").read_text()
    yaml_block = hermes.split("```yaml\n", 1)[1].split("\n```", 1)[0]
    assert yaml.safe_load(yaml_block) == {
        "model": {
            "default": "dgx-moa-agent",
            "provider": "custom",
            "base_url": "http://100.125.239.72:9000/v1",
            "api_key": "${DGX_MOA_API_KEY}",
            "context_length": 65536,
            "max_tokens": 16384,
        },
        "platform_toolsets": {"cli": ["file"]},
    }
    assert "custom_openai" not in hermes
    assert "Hermes Agent `0.18.2`" in hermes
    assert "HERMES_OK" in hermes
    assert "deferred" not in hermes.lower()


def test_opencode_validation_uses_standard_agent_requests() -> None:
    harness = Path("scripts/validate-opencode-loop.sh").read_text()
    assert harness.count('"model":"dgx-moa-agent"') == 2
    assert '"metadata":' not in harness


def test_benchmark_shape_and_improvement_tools(tmp_path) -> None:  # type: ignore[no-untyped-def]
    assert len(TASKS) == 10
    benchmark = tmp_path / "baseline.json"
    tasks = [
        {
            "task_success": True,
            "wall_clock_seconds": 1.0,
            "tool_calls": 1,
            "failure_classes": ["REPEATED_ACTION"],
            "expected_route": "fast",
            "reviewer_rejections": 0,
            "judge_invocations": 0,
        }
    ]
    benchmark.write_text(
        json.dumps(
            {
                "summary": summarize(tasks),
                "tasks": tasks,
            }
        )
    )
    proposal = mine(benchmark, tmp_path / "proposal.json")
    assert proposal["proposal_id"] == "IMP-2026-0001"
    assert proposal["statistics"]["failure_frequency"] == {"REPEATED_ACTION": 1}
    assert statistics({"tasks": []})["replan_rate"] == 0
    assert benchmark_models(tmp_path / "missing.yaml") == {}
    candidate = tmp_path / "candidate.json"
    candidate.write_text(json.dumps({"summary": summarize([])}))
    verdict = compare(benchmark, candidate, tmp_path / "comparison.json")
    assert verdict["automatic_merge"] is False


def test_dataset_and_adapter_promotion_guard(tmp_path) -> None:  # type: ignore[no-untyped-def]
    traces = tmp_path / "traces"
    traces.mkdir()
    trace = json.dumps(
        {
            "schema_version": "agent-trace-v2",
            "session_id": "one",
            "objective": "x",
            "final_status": "completed",
            "review_outcome": {"status": "approved"},
            "verified_state": [],
            "tool_observation": {},
            "assistant_tool_call": {},
            "training_eligibility": "eligible",
        }
    )
    (traces / "one.jsonl").write_text(trace + "\n" + trace + "\n")
    assert build(traces, tmp_path / "set.jsonl", tmp_path / "manifest.json")["count"] == 1
    metadata = {
        "adapter_id": "executor-v1",
        "status": "approved",
        "base_model_repository": "x",
        "base_model_revision": "x",
        "dataset_revision": "x",
        "dataset_hash": "x",
        "training_backend": "manual",
        "training_config_hash": "x",
        "created_at": "x",
        "benchmark": {},
    }
    path = tmp_path / "adapter.json"
    path.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="human approval"):
        register(path, tmp_path / "adapters")
    metadata["status"] = "candidate"
    path.write_text(json.dumps(metadata))
    assert register(path, tmp_path / "adapters").is_file()
    benchmark = tmp_path / "adapter-benchmark.json"
    benchmark.write_text(
        json.dumps(
            {
                "summary": {
                    "failure_class_distribution": {},
                    "task_success_rate": 1.0,
                    "time_per_successful_task": 1.0,
                }
            }
        )
    )
    result = evaluate(path, benchmark, benchmark, tmp_path / "adapter-comparison.json")
    assert result["adapter_id"] == "executor-v1"
    assert result["automatic_promotion"] is False


def test_dataset_quality_tiers() -> None:
    assert quality_tier({"human_correction": {"fix": "x"}}) == "Gold"
    assert (
        quality_tier({"final_status": "completed", "review_outcome": {"status": "approved"}})
        == "Silver"
    )
    assert quality_tier({"failure_classification": {"TEST_FAILURE": 1}}) == "Negative"
