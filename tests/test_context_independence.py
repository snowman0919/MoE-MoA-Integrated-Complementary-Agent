from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from dgx_moa.controller import Controller
from dgx_moa.frontier import FrontierCollaborationResult, FrontierConfig
from dgx_moa.state import SessionState, StateStore

from .conftest import StubProvider


@pytest.mark.asyncio
async def test_collaborators_share_one_immutable_pre_dispatch_snapshot(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    release = asyncio.Event()
    started = {role: asyncio.Event() for role in ("reasoner", "planner", "frontier")}
    captured: dict[str, dict[str, Any]] = {}
    output_markers = {
        "reasoner": "REASONER_OUTPUT_MARKER",
        "planner": "PLANNER_OUTPUT_MARKER",
        "frontier": "FRONTIER_OUTPUT_MARKER",
    }
    mutation_marker = "POST_PROJECTION_MUTATION"
    original_complete = stub_provider.complete

    async def gated_complete(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        if role not in {"reasoner", "planner"}:
            return await original_complete(role, model, request, **kwargs)
        captured[role] = request
        started[role].set()
        await release.wait()
        response = await original_complete(role, model, request, **kwargs)
        content = json.loads(response["choices"][0]["message"]["content"])
        if role == "reasoner":
            content["recommended_actions"] = [output_markers[role]]
        else:
            content["plan"][0]["step"] = output_markers[role]
        response["choices"][0]["message"]["content"] = json.dumps(content)
        return response

    class GatedFrontier:
        config = FrontierConfig(enabled=True, max_invocations_per_task=1)

        async def collaborate(self, mode, evidence, correlation_id):  # type: ignore[no-untyped-def]
            captured["frontier"] = evidence
            started["frontier"].set()
            await release.wait()
            return FrontierCollaborationResult(
                mode="architecture",
                output={
                    "recommended_architecture": output_markers["frontier"],
                    "design_decisions": [],
                    "tradeoffs": [],
                    "failure_modes": [],
                    "implementation_sequence": [],
                    "review_questions": [],
                },
                latency_ms=1,
                transmitted_categories=sorted(evidence),
            )

    stub_provider.complete = gated_complete  # type: ignore[method-assign]
    store = StateStore(settings.state_db)
    state = SessionState(
        session_id="immutable-collaboration-context",
        objective="Design the bounded architecture",
        acceptance_criteria=["initial constraint"],
        runtime_mode="agent",
        request_class="explicit_orchestrated",
        roles_required=["reasoner", "planner", "frontier", "executor"],
        tool_results=[{"stdout": "initial evidence", "exit_code": 0}],
    )
    request = {
        "model": "dgx-moa",
        "messages": [{"role": "user", "content": state.objective}],
        "metadata": {
            "architecture": True,
            "validation_results": [{"name": "unit", "passed": True}],
            "frontier_questions": ["Which boundary is safest?"],
        },
    }
    controller = Controller(  # type: ignore[arg-type]
        settings, store, stub_provider, GatedFrontier()
    )

    preparation = asyncio.create_task(
        controller.prepare_executor(
            state,
            request,
            ("reasoner", "planner", "frontier", "executor"),
        )
    )
    await asyncio.wait_for(asyncio.gather(*(event.wait() for event in started.values())), timeout=1)
    assert not preparation.done()

    state.acceptance_criteria.append(mutation_marker)
    state.tool_results[0]["stdout"] = mutation_marker
    request["metadata"]["validation_results"].append({"name": mutation_marker, "passed": False})
    request["metadata"]["frontier_questions"].append(mutation_marker)
    release.set()
    prepared = await asyncio.wait_for(preparation, timeout=1)

    for role, projection in captured.items():
        serialized = json.dumps(projection, ensure_ascii=False, sort_keys=True)
        for source_role, marker in output_markers.items():
            assert marker not in serialized, (role, source_role)

    executor_projection = json.dumps(prepared["messages"], ensure_ascii=False)
    assert all(marker in executor_projection for marker in output_markers.values())

    for role, projection in captured.items():
        serialized = json.dumps(projection, ensure_ascii=False, sort_keys=True)
        assert mutation_marker not in serialized, role

    projection_events = [
        event["payload"]
        for event in store.events(state.session_id)
        if event["event_type"] == "collaboration_context_projected"
        and event["payload"]["stage"] == "fanout"
    ]
    assert {event["role"] for event in projection_events} == {
        "reasoner",
        "planner",
        "frontier_a",
    }
    assert len({event["snapshot_hash"] for event in projection_events}) == 1
    assert all(event.get("projection_hash") for event in projection_events)
    assert all(
        event["snapshot_bytes"] > 0 and event["projection_bytes"] > 0 for event in projection_events
    )
    assert all(isinstance(event["dropped_evidence"], list) for event in projection_events)
    rendered_roles = {
        item["role"] for item in state.role_context_projections if item.get("rendered_prompt_bytes")
    }
    assert {"reasoner", "planner"}.issubset(rendered_roles)
    measured_invocations = [
        item for item in state.agent_invocations if item["role"] in {"reasoner", "planner"}
    ]
    assert all(
        item["provider_prompt_tokens"] == item["prompt_tokens"] for item in measured_invocations
    )
    assert all(item["snapshot_bytes"] and item["projection_bytes"] for item in measured_invocations)
