from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from dgx_moa.config import ModelConfig, Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    models = {
        role: ModelConfig(
            repository=f"test/{role}",
            revision="abc123",
            classification="official",
            base_url=f"http://127.0.0.1:{port}",
            served_name=role,
            destination=tmp_path / role,
            context_length=65536,
        )
        for role, port in {
            "executor": 8101,
            "planner": 8102,
            "reviewer": 8103,
            "reasoner": 8104,
            "judge": 8110,
        }.items()
    }
    return Settings(
        api_key="test-secret",
        state_db=tmp_path / "state.db",
        run_dir=tmp_path / "run",
        models=models,
    )


class StubProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.requests: list[dict[str, Any]] = []
        self.call_options: list[dict[str, Any]] = []

    async def complete(
        self,
        role: str,
        model: ModelConfig,
        request: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
        stage: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(role)
        self.requests.append(request)
        self.call_options.append({"timeout_seconds": timeout_seconds, "stage": stage})
        if role == "planner":
            content = json.dumps(
                {"plan": [{"step": "change"}], "acceptance_criteria": ["tests pass"]}
            )
        elif role == "reviewer":
            content = json.dumps({"status": "approved", "findings": []})
        elif role == "reasoner":
            content = json.dumps(
                {
                    "assumptions": [],
                    "constraints": ["Use verified evidence."],
                    "conclusions": ["Complete the requested task."],
                    "hypotheses": [],
                    "evidence_references": [],
                    "recommended_actions": ["Proceed with the Executor."],
                    "additional_agents": [],
                    "confidence_category": "high",
                }
            )
        elif role == "judge":
            content = json.dumps(
                {
                    "verdict": "accept",
                    "summary": "requirements satisfied",
                    "resolved_disagreements": [],
                    "mandatory_changes": [],
                    "risk_level": "low",
                    "completion_allowed": True,
                }
            )
        elif role == "executor" and (
            request.get("response_format", {}).get("json_schema", {}).get("name")
            == "orchestration_decision"
        ):
            content = json.dumps(
                {
                    "action": "respond",
                    "required_agents": [],
                    "optional_agents": [],
                    "reason": {},
                    "parallelizable": False,
                    "continue_after": "respond",
                    "confidence": 0.9,
                }
            )
        else:
            return {
                "id": "chatcmpl-test",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-preserved",
                                    "type": "function",
                                    "function": {"name": "read_file", "arguments": '{"path":"x"}'},
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"total_tokens": 3},
            }
        return {
            "choices": [
                {"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
            ]
        }

    async def stream(
        self,
        role: str,
        model: ModelConfig,
        request: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
        stage: str | None = None,
    ) -> AsyncIterator[bytes]:
        self.calls.append(role)
        self.requests.append(request)
        self.call_options.append({"timeout_seconds": timeout_seconds, "stage": stage})

        async def chunks() -> AsyncIterator[bytes]:
            yield b'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":null}]}\n\n'
            yield (
                b'data: {"choices":[{"delta":{},"finish_reason":"stop"}],'
                b'"usage":{"total_tokens":1}}\n\n'
            )
            yield b"data: [DONE]\n\n"

        return chunks()


@pytest.fixture
def stub_provider() -> StubProvider:
    return StubProvider()
