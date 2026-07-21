from __future__ import annotations

from dgx_moa.metrics import METRIC_NAMES, RuntimeMetrics


def test_runtime_metrics_are_fixed_label_free_and_drop_event_content() -> None:
    metrics = RuntimeMetrics()
    metrics.observe_event(
        "sensitive-request-id",
        "engineering_loop_started",
        {"prompt": "sensitive prompt"},
        "2026-07-22T00:00:00Z",
    )
    metrics.observe_event(
        "request",
        "engineering_loop_failure_registered",
        {"occurrence_count": 2, "failure_text": "sensitive failure"},
        "2026-07-22T00:00:01Z",
    )
    rendered = metrics.prometheus()

    assert metrics.snapshot()["loop_started_total"] == 1
    assert metrics.snapshot()["failure_fingerprint_recurrence"] == 1
    assert set(metrics.snapshot()) == set(METRIC_NAMES)
    assert "{" not in rendered
    assert "sensitive" not in rendered


def test_runtime_metrics_classify_loop_outcomes_without_reason_labels() -> None:
    metrics = RuntimeMetrics()
    for reason in ("SUCCESS", "NO_PROGRESS", "BUDGET_EXHAUSTED"):
        metrics.observe_event(
            "request", "engineering_loop_terminated", {"reason": reason}, "timestamp"
        )

    snapshot = metrics.snapshot()
    assert snapshot["loop_completed_total"] == 1
    assert snapshot["loop_failed_total"] == 2
    assert snapshot["loop_no_progress_total"] == 1
    assert snapshot["loop_budget_exhausted_total"] == 1
