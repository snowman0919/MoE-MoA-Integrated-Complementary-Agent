"""Focused Output Validation Gate tests: manifest, decisions, convergence."""

from __future__ import annotations

import pytest
from dgx_moa.actions.output import (
    OUTPUT_DECISIONS,
    OutputGateContext,
    build_completion_manifest,
    decide_output,
    observe_output_shadow,
    shadow_agreement,
)
from dgx_moa.api import create_app
from fastapi.testclient import TestClient

from .conftest import StubProvider


def _success(command: str = "pytest /work/app.py", path: str = "/work/app.py") -> dict:
    return {
        "tool_name": "terminal",
        "exit_code": 0,
        "tool_execution_id": "exec-1",
        "normalized_arguments": {"command": command},
        "stdout_summary": f"{command} passed",
        "stderr_summary": "",
        "filesystem_effect": {"changed_paths": [path]},
    }


def test_supported_claims_pass() -> None:
    context = OutputGateContext(
        objective="fix app",
        final_text="Fixed /work/app.py. Tests passing.",
        successful_executions=(_success(),),
        verified_facts=("/work/app.py updated",),
        changed_paths=("/work/app.py",),
    )
    manifest = build_completion_manifest(context)
    assert (
        manifest.supported_claims == manifest.supported_claims and manifest.unsupported_claims == 0
    )
    result = decide_output(manifest, context)
    assert result.decision == "PASS"
    assert manifest.manifest_id and manifest.evidence_digest


def test_unsupported_claim_fails_closed() -> None:
    context = OutputGateContext(objective="fix app", final_text="Fixed /etc/passwd. Done.")
    manifest = build_completion_manifest(context)
    assert manifest.unsupported_claims > 0
    result = decide_output(manifest, context)
    assert result.decision == "FAIL_CLOSED"
    assert "unsupported material claim" in result.reason


def test_stale_progress_rejected() -> None:
    context = OutputGateContext(
        objective="fix app",
        final_text="I will implement the fix next. Trust me, it should work.",
    )
    manifest = build_completion_manifest(context)
    result = decide_output(manifest, context)
    # No material completion assertion exists, so the draft is rewrite-only
    # rather than a false completion claim.
    assert result.decision == "REWRITE_ONLY"


def test_pending_tool_calls_reexecute() -> None:
    context = OutputGateContext(
        objective="work",
        final_text="Fixed /work/app.py.",
        pending_tool_call_ids=("call-1",),
        successful_executions=(_success(),),
    )
    manifest = build_completion_manifest(context)
    assert decide_output(manifest, context).decision == "REEXECUTE"


def test_truncated_and_failures_reexecute() -> None:
    truncated = OutputGateContext(objective="w", final_text="Fixed /work/a.py.", truncated=True)
    assert decide_output(build_completion_manifest(truncated), truncated).decision == "REEXECUTE"
    failed = OutputGateContext(
        objective="w",
        final_text="Fixed /work/a.py.",
        active_failures=({"failure_class": "TEST_FAILURE", "resolution_status": "active"},),
    )
    assert decide_output(build_completion_manifest(failed), failed).decision == "REEXECUTE"


def test_missing_criteria_and_review_escalate() -> None:
    criteria = OutputGateContext(
        objective="w",
        final_text="Fixed /work/a.py.",
        successful_executions=(_success("pytest /work/a.py", "/work/a.py"),),
        acceptance_criteria=("tests pass",),
        completion_evidence={},
    )
    assert decide_output(build_completion_manifest(criteria), criteria).decision == "REEXECUTE"
    review = OutputGateContext(
        objective="w",
        final_text="Hello.",
        review_required=True,
        review_status="pending",
    )
    assert decide_output(build_completion_manifest(review), review).decision == "ESCALATE_REVIEW"


def test_rewrite_only_empty_or_plain_text() -> None:
    for text in ["", "Hello, how can I help?"]:
        context = OutputGateContext(objective="chat", final_text=text)
        manifest = build_completion_manifest(context)
        assert decide_output(manifest, context).decision == "REWRITE_ONLY"


def test_laya_shadow_never_overrides() -> None:
    context = OutputGateContext(objective="fix", final_text="Fixed /etc/passwd.")
    manifest = build_completion_manifest(context)
    deterministic = decide_output(manifest, context).decision
    assert deterministic == "FAIL_CLOSED"
    choice, _ = observe_output_shadow(manifest, choose=lambda cands, digest: "PASS")
    assert choice == "PASS"
    assert shadow_agreement(deterministic, choice) is False
    # Invalid and failing shadows fall back to no opinion.
    assert observe_output_shadow(manifest, choose=lambda cands, digest: "NOPE") == (None, None)
    assert observe_output_shadow(manifest)[0] is None
    assert shadow_agreement(deterministic, None) is None
    assert set(OUTPUT_DECISIONS) == {
        "PASS",
        "REWRITE_ONLY",
        "REEXECUTE",
        "RESOLVE_RESOURCE",
        "ESCALATE_REVIEW",
        "FAIL_CLOSED",
    }


def test_chat_nonstream_blocks_unsupported_completion(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    original = stub_provider.complete

    async def unsupported(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        if role == "executor":
            return {
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "Fixed /etc/passwd. Done."},
                        "finish_reason": "stop",
                    }
                ]
            }
        return await original(role, model, request, **kwargs)

    stub_provider.complete = unsupported  # type: ignore[method-assign]
    with TestClient(create_app(settings)) as client:
        client.app.state.provider = stub_provider
        client.app.state.controller.provider = stub_provider
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret", "X-Session-ID": "gate-output"},
            json={"model": "dgx-moa-fast", "messages": [{"role": "user", "content": "fix it"}]},
        )
    assert response.status_code == 502
    blocked = [
        event
        for event in client.app.state.store.events("gate-output")
        if event["event_type"] == "output_validation_blocked"
    ]
    assert blocked and blocked[0]["payload"]["decision"] == "FAIL_CLOSED"


def test_chat_stream_records_output_validation_block(settings, stub_provider: StubProvider) -> None:  # type: ignore[no-untyped-def]
    delta = (
        b'data: {"choices":[{"delta":{"content":"Fixed /etc/passwd."},"finish_reason":null}]}\n\n'
    )

    async def streamed(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        async def upstream():  # type: ignore[no-untyped-def]
            yield delta
            yield b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
            yield b"data: [DONE]\n\n"

        return upstream()

    stub_provider.stream = streamed  # type: ignore[method-assign]
    with TestClient(create_app(settings)) as client:
        client.app.state.provider = stub_provider
        client.app.state.controller.provider = stub_provider
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret", "X-Session-ID": "gate-output-stream"},
            json={
                "model": "dgx-moa-fast",
                "stream": True,
                "messages": [{"role": "user", "content": "fix it"}],
            },
        )
    assert response.status_code == 200
    blocked = [
        event
        for event in client.app.state.store.events("gate-output-stream")
        if event["event_type"] == "output_validation_blocked"
    ]
    assert blocked and blocked[0]["payload"]["decision"] == "FAIL_CLOSED"


def test_chat_nonstream_passes_supported_completion(settings, stub_provider: StubProvider) -> None:  # type: ignore[no-untyped-def]
    original = stub_provider.complete

    async def supported(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        if role == "executor":
            return {
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "Fixed /work/app.py."},
                        "finish_reason": "stop",
                    }
                ]
            }
        return await original(role, model, request, **kwargs)

    stub_provider.complete = supported  # type: ignore[method-assign]
    with TestClient(create_app(settings)) as client:
        client.app.state.provider = stub_provider
        client.app.state.controller.provider = stub_provider
        state = client.app.state.store.get(
            "gate-output-pass"
        ) or client.app.state.controller.session(
            "gate-output-pass", [{"role": "user", "content": "fix it"}]
        )
        state.verified_facts.append("Fixed /work/app.py with passing tests")
        client.app.state.store.save(state)
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret", "X-Session-ID": "gate-output-pass"},
            json={"model": "dgx-moa-fast", "messages": [{"role": "user", "content": "fix it"}]},
        )
    assert response.status_code == 200
    passed = [
        event
        for event in client.app.state.store.events("gate-output-pass")
        if event["event_type"] == "output_validation_passed"
    ]
    assert passed and passed[0]["payload"]["decision"] == "PASS"


@pytest.mark.asyncio
async def test_responses_nonstream_records_output_validation(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    from dgx_moa.schemas import ResponsesRequest
    from fastapi import Request

    from tests.test_action_gates import _responses_endpoint

    original = stub_provider.complete

    async def unsupported(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        if role == "executor":
            return {
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "Fixed /etc/passwd."},
                        "finish_reason": "stop",
                    }
                ]
            }
        return await original(role, model, request, **kwargs)

    stub_provider.complete = unsupported  # type: ignore[method-assign]
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        app.state.provider = stub_provider
        app.state.controller.provider = stub_provider
        response = await _responses_endpoint(app)(
            ResponsesRequest(model="dgx-moa-fast", input="fix it"),
            Request({"type": "http", "app": app}),
            x_session_id="gate-output-responses",
            x_runtime_channel=None,
            x_trace_origin=None,
            x_task_id=None,
            x_workspace_path=None,
            x_workspace_id=None,
            x_repository_branch=None,
            x_repository_commit=None,
            x_dirty_state=None,
        )
    assert response.status_code == 200
    blocked = [
        event
        for event in app.state.store.events("gate-output-responses")
        if event["event_type"] == "output_validation_blocked"
    ]
    assert blocked and blocked[0]["payload"]["decision"] == "FAIL_CLOSED"
    assert blocked[0]["payload"]["path"] in ("chat_nonstream", "responses_nonstream")


def test_responses_stream_records_output_validation_block(
    settings, stub_provider: StubProvider
) -> None:  # type: ignore[no-untyped-def]
    from dgx_moa.schemas import ResponsesRequest
    from fastapi import Request

    from tests.test_action_gates import _responses_endpoint

    async def streamed(role, model, request, **kwargs):  # type: ignore[no-untyped-def]
        async def upstream():  # type: ignore[no-untyped-def]
            yield (
                b'data: {"choices":[{"delta":{"content":"Fixed /etc/passwd."},'
                b'"finish_reason":null}]}\n\n'
            )
            yield b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
            yield b"data: [DONE]\n\n"

        return upstream()

    stub_provider.stream = streamed  # type: ignore[method-assign]
    app = create_app(settings)

    async def run() -> None:  # type: ignore[no-untyped-def]
        from fastapi.responses import StreamingResponse

        async with app.router.lifespan_context(app):
            app.state.provider = stub_provider
            app.state.controller.provider = stub_provider
            response = await _responses_endpoint(app)(
                ResponsesRequest(model="dgx-moa-fast", input="fix it", stream=True),
                Request({"type": "http", "app": app}),
                x_session_id="gate-output-responses-stream",
                x_runtime_channel=None,
                x_trace_origin=None,
                x_task_id=None,
                x_workspace_path=None,
                x_workspace_id=None,
                x_repository_branch=None,
                x_repository_commit=None,
                x_dirty_state=None,
            )
            assert isinstance(response, StreamingResponse)
            text = b"".join([chunk async for chunk in response.body_iterator]).decode()
            assert "Fixed /etc/passwd." in text

    import asyncio

    asyncio.run(run())
    blocked = [
        event
        for event in app.state.store.events("gate-output-responses-stream")
        if event["event_type"] == "output_validation_blocked"
    ]
    assert blocked and blocked[0]["payload"]["decision"] == "FAIL_CLOSED"
    assert blocked[0]["payload"]["path"] in ("chat_stream", "responses_stream")


def test_output_metrics_count_decisions() -> None:
    from dgx_moa.metrics import RuntimeMetrics

    metrics = RuntimeMetrics()
    metrics.observe_event("s", "output_validation_decided", {"decision": "PASS"}, "t")
    metrics.observe_event("s", "output_validation_decided", {"decision": "FAIL_CLOSED"}, "t")
    metrics.observe_event("s", "output_validation_decided", {"decision": "REWRITE_ONLY"}, "t")
    metrics.observe_event("s", "output_validation_decided", {"decision": "REEXECUTE"}, "t")
    metrics.observe_event("s", "output_validation_decided", {"decision": "RESOLVE_RESOURCE"}, "t")
    metrics.observe_event("s", "output_validation_decided", {"decision": "ESCALATE_REVIEW"}, "t")
    metrics.observe_event("s", "output_validation_laya_shadow", {"agreement": True}, "t")
    metrics.observe_event("s", "output_validation_laya_shadow", {"agreement": False}, "t")
    snapshot = metrics.snapshot()
    assert snapshot["output_validation_pass"] == 1
    assert snapshot["output_validation_fail_closed"] == 1
    assert snapshot["output_validation_rewrite_only"] == 1
    assert snapshot["output_validation_reexecute"] == 1
    assert snapshot["output_validation_resolve_resource"] == 1
    assert snapshot["output_validation_escalate_review"] == 1
    assert snapshot["output_validation_laya_shadow_agreement"] == 1
    assert snapshot["output_validation_laya_shadow_disagreement"] == 1


def test_laya_output_endpoint_rejects_non_loopback() -> None:
    from dgx_moa.config import ActionRuntimeConfig

    with pytest.raises(ValueError, match="loopback"):
        ActionRuntimeConfig(laya_enabled=True, laya_endpoint="https://example.com/decide")
