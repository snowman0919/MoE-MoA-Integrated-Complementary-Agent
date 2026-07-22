from __future__ import annotations

import json

import pytest
from dgx_moa.config import Settings
from dgx_moa.controller import Controller, PolicyBlocked
from dgx_moa.policy import PolicyEngine, PolicySet
from dgx_moa.state import Phase, SessionState, StateStore
from pydantic import ValidationError


def policy_set() -> PolicySet:
    return PolicySet.model_validate(
        {
            "version": "2026-07-22.1",
            "policies": [
                {
                    "id": "security-review",
                    "when": {
                        "any": [
                            {"task.security_sensitive": True},
                            {"changed_paths_match": ["auth/**", "security/**"]},
                        ]
                    },
                    "require": {"reviewer": True, "frontier": True},
                    "redact": ["tool.credentials"],
                    "fail_closed": {"reviewer": True, "judge": True},
                },
                {
                    "id": "duplicate-failure",
                    "when": {"failure.same_fingerprint_count_gte": 2},
                    "recommend": {"frontier": True},
                    "limit": {"tool_calls": 10},
                },
                {
                    "id": "destructive-operation",
                    "when": {"tool.destructive": True},
                    "request_approval": ["operator"],
                    "deny": {"tools": ["recursive-delete"]},
                },
            ],
        }
    )


def test_policy_engine_traces_versioned_aggregated_decision() -> None:
    policies = policy_set()
    decision = PolicyEngine(policies).evaluate(
        {
            "task": {"security_sensitive": False},
            "changed_paths": ["auth/routes.py"],
            "failure": {"same_fingerprint_count": 3},
            "tool": {"destructive": True},
        }
    )

    assert decision.matched_rules == [
        "security-review",
        "duplicate-failure",
        "destructive-operation",
    ]
    assert decision.require == {"reviewer": True, "frontier": True}
    assert decision.limits["tool_calls"] == 10
    assert decision.approvals_required == ["operator"]
    assert decision.fail_closed == {"reviewer": True, "judge": True}
    assert len(decision.policy_hash) == 64


def test_policy_nonmatch_has_traceable_empty_decision() -> None:
    decision = PolicyEngine(policy_set()).evaluate(
        {
            "task": {"security_sensitive": False},
            "changed_paths": ["docs/readme.md"],
            "failure": {"same_fingerprint_count": 0},
            "tool": {"destructive": False},
        }
    )

    assert decision.matched_rules == []
    assert decision.policy_version == "2026-07-22.1"


def test_policy_uses_most_restrictive_limit() -> None:
    policies = PolicySet.model_validate(
        {
            "version": "1",
            "policies": [
                {"id": "one", "when": {"task.kind": "test"}, "limit": {"tool_calls": 20}},
                {"id": "two", "when": {"task.kind": "test"}, "limit": {"tool_calls": 5}},
            ],
        }
    )

    assert PolicyEngine(policies).evaluate({"task": {"kind": "test"}}).limits == {"tool_calls": 5}


def test_policy_rejects_ambiguous_or_unbounded_conditions() -> None:
    with pytest.raises(ValidationError, match="one comparison"):
        PolicySet.model_validate(
            {
                "version": "1",
                "policies": [{"id": "bad", "when": {"task.a": True, "task.b": True}, "deny": {}}],
            }
        )


def test_request_deny_is_explicit() -> None:
    policies = PolicySet.model_validate(
        {
            "version": "1",
            "policies": [
                {"id": "deny-request", "when": {"task.blocked": True}, "deny": {"request": True}}
            ],
        }
    )

    assert PolicyEngine(policies).evaluate({"task": {"blocked": True}}).request_denied is True


def test_controller_applies_policy_roles_limits_and_trace(tmp_path) -> None:  # type: ignore[no-untyped-def]
    policies = policy_set()
    settings = Settings(
        auth_enabled=False,
        state_db=tmp_path / "state.db",
        loop_engineering={"enabled": True},
        declarative_policy={
            "enabled": True,
            "version": policies.version,
            "policies": [rule.model_dump() for rule in policies.policies],
        },
    )
    store = StateStore(settings.state_db)
    controller = Controller(
        settings, store, object(), policy=PolicyEngine(settings.declarative_policy.policy_set())
    )  # type: ignore[arg-type]
    state = SessionState(session_id="policy-session", objective="Review auth changes")

    controller.select_route(
        state,
        {
            "task_id": "task-1",
            "security_sensitive": True,
            "changed_paths": ["auth/routes.py"],
        },
    )

    assert {"reviewer", "frontier"}.issubset(state.roles_required)
    assert state.route == "escalation"
    assert state.engineering_loop is not None
    assert state.policy_decisions[-1]["policy_version"] == policies.version
    assert state.policy_fail_closed_roles == ["reviewer", "judge"]
    assert state.review_fail_closed is True
    assert any(node["kind"] == "policy_decision" for node in state.evidence_nodes)


def test_controller_blocks_missing_policy_approval_and_persists_reason(
    tmp_path,  # type: ignore[no-untyped-def]
) -> None:
    policies = policy_set()
    settings = Settings(
        auth_enabled=False,
        state_db=tmp_path / "state.db",
        loop_engineering={"enabled": True},
        declarative_policy={
            "enabled": True,
            "version": policies.version,
            "policies": [rule.model_dump() for rule in policies.policies],
        },
    )
    store = StateStore(settings.state_db)
    controller = Controller(
        settings, store, object(), policy=PolicyEngine(settings.declarative_policy.policy_set())
    )  # type: ignore[arg-type]
    state = SessionState(session_id="approval-session", objective="Delete generated output")

    with pytest.raises(PolicyBlocked, match="operator approval"):
        controller.select_route(
            state,
            {"task_id": "task-2", "destructive_operation": True},
        )

    persisted = store.get(state.session_id)
    assert persisted is not None
    assert persisted.phase == Phase.BLOCKED
    assert persisted.engineering_loop is not None
    assert persisted.engineering_loop.termination_reason == "PERMISSION_REQUIRED"


def test_controller_enforces_tool_deny_and_evidence_field_redaction(tmp_path) -> None:  # type: ignore[no-untyped-def]
    policies = PolicySet.model_validate(
        {
            "version": "tool-policy-1",
            "policies": [
                {
                    "id": "bounded-tools",
                    "when": {"task.restricted": True},
                    "deny": {"tools": ["shell", "mcp__unsafe__*"]},
                    "redact": ["tool.credentials", "arguments.token"],
                }
            ],
        }
    )
    settings = Settings(
        auth_enabled=False,
        state_db=tmp_path / "state.db",
        loop_engineering={"enabled": True},
        declarative_policy={
            "enabled": True,
            "version": policies.version,
            "policies": [rule.model_dump() for rule in policies.policies],
        },
    )
    store = StateStore(settings.state_db)
    controller = Controller(
        settings, store, object(), policy=PolicyEngine(settings.declarative_policy.policy_set())
    )  # type: ignore[arg-type]
    state = SessionState(session_id="tool-policy", objective="bounded tools")
    controller.select_route(state, {"task_id": "task-3", "restricted": True})

    controller.record_evidence(
        state,
        "tool_result",
        "executor",
        {"tool": {"credentials": "synthetic-secret", "status": "ok"}},
    )
    assert state.evidence_nodes[-1]["payload"]["tool"]["credentials"] == ("[REDACTED_BY_POLICY]")
    controller._observe(
        state,
        [
            {
                "role": "tool",
                "tool_call_id": "read-1",
                "content": json.dumps(
                    {
                        "tool_name": "read_file",
                        "arguments": {"token": "synthetic-token", "path": "README.md"},
                        "stdout": "ok",
                        "exit_code": 0,
                    }
                ),
            }
        ],
    )
    assert state.tool_results[-1]["arguments"]["token"] == "[REDACTED_BY_POLICY]"
    assert state.tool_executions[-1]["normalized_arguments"]["token"] == ("[REDACTED_BY_POLICY]")
    controller.admit_tool_call(state, "read_file")
    with pytest.raises(PolicyBlocked, match="tool call denied"):
        controller.admit_tool_call(state, "shell")
    assert state.engineering_loop is not None
    assert state.engineering_loop.termination_reason == "POLICY_BLOCKED"


@pytest.mark.asyncio
async def test_policy_redacts_specialist_state_event_and_evaluation_boundaries(
    settings, stub_provider
) -> None:  # type: ignore[no-untyped-def]
    store = StateStore(settings.state_db)
    controller = Controller(settings, store, stub_provider)
    state = SessionState(
        session_id="specialist-redaction",
        objective="Review a bounded change",
        runtime_mode="orchestrated",
        request_class="standard_task",
        policy_redact_fields=[
            "conclusions",
            "reason",
            "plan",
            "acceptance_criteria",
            "output.findings",
            "summary",
            "observation",
        ],
    )
    request = {
        "model": "dgx-moa-orchestrated",
        "messages": [{"role": "user", "content": state.objective}],
        "metadata": {
            "code_review": True,
            "changed_paths": ["gateway.py"],
            "diff_summary": "+safe change",
            "validation_results": [{"status": "passed"}],
        },
    }

    await controller.prepare_executor(
        state,
        request,
        ("reasoner", "planner", "executor", "reviewer"),
    )
    await controller.judge(state, "synthetic private observation")

    assert state.reasoner_contributions[-1]["conclusions"] == []
    assert state.orchestration_decisions[-1]["reason"] == {}
    assert state.plan == []
    assert state.acceptance_criteria == []
    reviewer = next(item for item in state.agent_artifacts if item["role"] == "reviewer")
    assert reviewer["output"]["findings"] == []
    assert state.judge_verdict and state.judge_verdict["summary"] == "[REDACTED_BY_POLICY]"
    events = store.events(state.session_id)
    review_event = next(item for item in events if item["event_type"] == "review_completed")
    judge_request = next(item for item in events if item["event_type"] == "judge_requested")
    judge_event = next(item for item in events if item["event_type"] == "judge_completed")
    assert review_event["payload"]["findings"] == []
    assert judge_request["payload"]["observation"] == "[REDACTED_BY_POLICY]"
    assert judge_event["payload"]["summary"] == "[REDACTED_BY_POLICY]"
    assert state.evaluations[-1]["result"]["summary"] == "[REDACTED_BY_POLICY]"
