from __future__ import annotations

from typing import Any

METRIC_NAMES = (
    "loop_started_total",
    "loop_completed_total",
    "loop_failed_total",
    "loop_iterations",
    "loop_no_progress_total",
    "loop_budget_exhausted_total",
    "failure_fingerprint_recurrence",
    "skill_invocations_total",
    "skill_success_total",
    "skill_override_total",
    "skill_regression_total",
    "skill_candidate_created_total",
    "skill_promoted_total",
    "skill_deprecated_total",
    "observer_events_sent_total",
    "observer_events_dropped_total",
    "discord_errors_total",
    "telegram_errors_total",
    "approval_requests_total",
    "approval_timeouts_total",
    "training_events_collected_total",
    "training_candidates_created_total",
    "training_candidates_excluded_total",
    "secret_redactions_total",
    "privacy_exclusions_total",
    "license_exclusions_total",
    "exact_duplicates_removed_total",
    "near_duplicates_removed_total",
    "weekly_packages_created_total",
    "weekly_package_failures_total",
    "weekly_package_bytes",
    "archive_verification_failures_total",
)


class RuntimeMetrics:
    """Fixed, label-free metrics; event payload content is never retained."""

    def __init__(self) -> None:
        self._values: dict[str, float] = {name: 0.0 for name in METRIC_NAMES}

    def increment(self, name: str, amount: int | float = 1) -> None:
        if name not in METRIC_NAMES:
            raise KeyError("unknown runtime metric")
        self._values[name] += amount

    def observe_event(
        self, session_id: str, event_type: str, payload: dict[str, Any], created_at: str
    ) -> None:
        del session_id, created_at
        if event_type == "engineering_loop_started":
            self.increment("loop_started_total")
        elif event_type == "engineering_loop_iteration_started":
            self.increment("loop_iterations")
        elif event_type == "engineering_loop_terminated":
            reason = payload.get("reason")
            if reason in {"SUCCESS", "PARTIAL_SUCCESS"}:
                self.increment("loop_completed_total")
            else:
                self.increment("loop_failed_total")
            if reason == "NO_PROGRESS":
                self.increment("loop_no_progress_total")
            if reason == "BUDGET_EXHAUSTED":
                self.increment("loop_budget_exhausted_total")
        elif (
            event_type == "engineering_loop_failure_registered"
            and int(payload.get("occurrence_count", 0)) > 1
        ):
            self.increment("failure_fingerprint_recurrence")
        elif event_type == "frontier_candidate_awaiting_approval":
            self.increment("approval_requests_total")

    def snapshot(self, overlays: dict[str, int | float] | None = None) -> dict[str, int | float]:
        values = {name: self._values[name] for name in METRIC_NAMES}
        for name, value in (overlays or {}).items():
            if name in values:
                values[name] = value
        return values

    def prometheus(self, overlays: dict[str, int | float] | None = None) -> str:
        values = self.snapshot(overlays)
        return "".join(f"# TYPE {name} gauge\n{name} {values[name]}\n" for name in METRIC_NAMES)
