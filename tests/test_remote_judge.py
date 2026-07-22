from __future__ import annotations

import json

import httpx
import pytest
from dgx_moa.controller import Controller
from dgx_moa.remote_judge import (
    JudgeCallLimitExceeded,
    JudgeEvidencePackage,
    JudgeProviderError,
    JudgeUnavailable,
    MockJudgeProvider,
    NvidiaNimJudgeProvider,
    RemoteJudgeVerdict,
)
from dgx_moa.state import SessionState, StateStore


def verdict(verdict: str = "approve") -> dict[str, object]:
    return {
        "verdict": verdict,
        "risk": "low",
        "criteria": {
            "instruction_following": "pass",
            "evidence_grounding": "pass",
            "logical_consistency": "pass",
            "tool_consistency": "pass",
            "test_consistency": "pass",
            "safety": "pass",
            "completeness": "pass",
        },
        "findings": [],
        "required_edits": [],
        "recheck_required": False,
        "confidence_class": "high",
    }


@pytest.mark.asyncio
async def test_nim_judge_sends_redacted_bounded_strict_package(monkeypatch) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(verdict())}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
            },
        )

    monkeypatch.setenv("TEST_NVIDIA_KEY", "synthetic-secret")
    provider = NvidiaNimJudgeProvider(
        endpoint="https://nim.invalid/v1",
        api_key_env="TEST_NVIDIA_KEY",
        transport=httpx.MockTransport(respond),
    )
    result = await provider.judge(
        JudgeEvidencePackage(
            request_id="req-1",
            objective="Review alice@example.invalid authorization: Bearer private-value",
            executor_draft="done",
        )
    )

    assert result.verdict == "approve"
    body = json.loads(requests[0].content)
    assert "tools" not in body
    assert body["model"] == "z-ai/glm-5.2"
    assert body["max_tokens"] == 1024
    assert body["seed"] == 0
    assert "one bounded required edit" in body["messages"][0]["content"]
    assert requests[0].url == "https://nim.invalid/v1/chat/completions"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert "alice@example.invalid" not in body["messages"][1]["content"]
    assert "private-value" not in body["messages"][1]["content"]
    assert requests[0].headers["authorization"] == "Bearer synthetic-secret"
    assert await provider.usage("req-1") == {
        "prompt_tokens": 12,
        "completion_tokens": 8,
        "total_tokens": 20,
    }


@pytest.mark.asyncio
async def test_nim_judge_retries_rate_limit_and_enforces_two_calls(monkeypatch) -> None:
    attempts = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, request=request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(verdict())}}]},
            request=request,
        )

    monkeypatch.setenv("TEST_NVIDIA_KEY", "synthetic-secret")
    provider = NvidiaNimJudgeProvider(
        endpoint="https://nim.invalid",
        api_key_env="TEST_NVIDIA_KEY",
        max_retries=1,
        max_calls_per_request=2,
        transport=httpx.MockTransport(respond),
    )
    package = JudgeEvidencePackage(request_id="req-budget", objective="judge")

    assert (await provider.judge(package)).verdict == "approve"
    assert (await provider.judge(package)).verdict == "approve"
    with pytest.raises(JudgeCallLimitExceeded):
        await provider.judge(package)


@pytest.mark.asyncio
async def test_nim_judge_timeout_and_invalid_output_are_controlled(monkeypatch) -> None:
    monkeypatch.setenv("TEST_NVIDIA_KEY", "synthetic-secret")

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("late", request=request)

    timed = NvidiaNimJudgeProvider(
        endpoint="https://nim.invalid",
        api_key_env="TEST_NVIDIA_KEY",
        max_retries=0,
        transport=httpx.MockTransport(timeout),
    )
    with pytest.raises(JudgeUnavailable):
        await timed.judge(JudgeEvidencePackage(request_id="timeout", objective="judge"))

    invalid = NvidiaNimJudgeProvider(
        endpoint="https://nim.invalid",
        api_key_env="TEST_NVIDIA_KEY",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"choices": [{"message": {"content": "{}"}}]}, request=request
            )
        ),
    )
    with pytest.raises(JudgeProviderError, match="invalid structured output"):
        await invalid.judge(JudgeEvidencePackage(request_id="invalid", objective="judge"))


def test_remote_verdict_requires_every_criterion() -> None:
    payload = verdict()
    del payload["criteria"]["safety"]  # type: ignore[index]
    with pytest.raises(ValueError):
        RemoteJudgeVerdict.model_validate(payload)


def test_selective_judge_policy_covers_risk_and_skips_tool_turns(settings, stub_provider) -> None:
    remote = MockJudgeProvider(RemoteJudgeVerdict.model_validate(verdict()))
    controller = Controller(
        settings,
        StateStore(settings.state_db),
        stub_provider,
        remote_judge=remote,
    )
    state = SessionState(session_id="selective", failure_families={"same-failure": 2})
    reasons = controller.remote_judge_invocation_reasons(
        state,
        {
            "authentication": True,
            "database_schema": True,
            "production_deployment": True,
            "tests_claim_inconsistent": True,
        },
        {"choices": [{"message": {"role": "assistant", "content": "done"}}]},
    )

    assert reasons == [
        "security_or_authentication_change",
        "database_schema_or_migration",
        "production_deployment_approval",
        "test_result_claim_inconsistency",
        "repeated_failure_fingerprint",
    ]
    assert (
        controller.remote_judge_invocation_reasons(
            state,
            {"authentication": True},
            {"choices": [{"message": {"tool_calls": [{"id": "call-1"}]}}]},
        )
        == []
    )


def test_executor_context_includes_bounded_judge_corrections(settings, stub_provider) -> None:
    controller = Controller(settings, StateStore(settings.state_db), stub_provider)
    state = SessionState(
        session_id="correction",
        judge_verdict={"verdict": "revise", "required_edits": [{"target": "claim"}]},
    )

    context = controller.role_context("executor", state, "apply corrections")

    assert context["judge_corrections"] == state.judge_verdict
