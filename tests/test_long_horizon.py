from __future__ import annotations

import hashlib

from dgx_moa.compression import compress_messages
from dgx_moa.controller import Controller
from dgx_moa.loop_engineering import begin_iteration, set_criterion
from dgx_moa.state import StateStore


def test_ten_hour_goal_survives_compaction_and_controller_restart(
    settings, stub_provider  # type: ignore[no-untyped-def]
) -> None:
    settings.loop_engineering.enabled = True
    first_store = StateStore(settings.state_db)
    first = Controller(settings, first_store, stub_provider)
    objective = "10시간 동안 구현하고 각 검증 기준의 증거를 보존하라"
    state = first.session("long-goal", [{"role": "user", "content": objective}])
    first.select_route(state, {})
    assert state.engineering_loop is not None
    state.plan = [{"step": "implement"}, {"step": "test"}, {"step": "review"}]
    state.completed_steps = ["implement"]
    state.acceptance_criteria = ["tests pass", "review approved"]
    state.completion_evidence = {"tests pass": "pytest:0"}
    state.implementation_evidence = [{"kind": "file_change", "path": "src/runtime.py"}]
    state.pending_tool_call_ids = ["call-next"]
    state.step_count = 900
    set_criterion(
        state.engineering_loop,
        "tests pass",
        "passed",
        evidence_ids=["pytest:0"],
    )
    state.engineering_loop.started_at_epoch = 1_000
    first_store.save(state)

    history = [
        {"role": "user", "content": f"observation {index}"}
        for index in range(100)
    ]
    compacted = compress_messages(history, settings.limits)
    assert len(compacted) == settings.limits.max_retained_observations

    restarted_store = StateStore(settings.state_db)
    restarted = Controller(settings, restarted_store, stub_provider)
    recovered = restarted.session(
        "long-goal",
        [*compacted, {"role": "user", "content": "계속 진행해"}],
    )
    assert recovered.engineering_loop is not None
    assert begin_iteration(recovered.engineering_loop, now_epoch=37_000)
    restarted_store.save(recovered)

    final = StateStore(settings.state_db).get("long-goal")
    assert final is not None and final.engineering_loop is not None
    assert hashlib.sha256(final.objective.encode()).hexdigest() == hashlib.sha256(
        objective.encode()
    ).hexdigest()
    assert final.plan == [{"step": "implement"}, {"step": "test"}, {"step": "review"}]
    assert final.completed_steps == ["implement"]
    assert final.acceptance_criteria == ["tests pass", "review approved"]
    assert final.completion_evidence == {"tests pass": "pytest:0"}
    assert final.implementation_evidence == [{"kind": "file_change", "path": "src/runtime.py"}]
    assert final.pending_tool_call_ids == ["call-next"]
    assert final.engineering_loop.remaining_budget.wall_clock_seconds == 7_200
    assert final.engineering_loop.acceptance_criteria[0].state == "passed"
    assert final.engineering_loop.termination_reason is None
