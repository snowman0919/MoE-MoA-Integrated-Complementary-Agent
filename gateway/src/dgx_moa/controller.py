from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .compression import compress_messages
from .config import Settings
from .providers import ModelProvider, parse_json_content
from .routing import ChangeRisk, heavy_eligible, needs_planner
from .schemas import JudgeVerdict
from .security import redact
from .state import Phase, SessionState, StateStore
from .validation import completion_ready


class DuplicateFailedCall(ValueError):
    pass


def fingerprint(call: dict[str, Any]) -> str:
    normalized_call = call.get("function", call)
    normalized = json.dumps(normalized_call, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode()).hexdigest()


def failure_family(observation: str) -> str:
    first = next(
        (
            line.strip().lower()
            for line in observation.splitlines()
            if any(word in line.lower() for word in ("error", "failed", "exception"))
        ),
        observation.strip().lower()[:200],
    )
    return hashlib.sha256(first.encode()).hexdigest()[:16]


class Controller:
    def __init__(self, settings: Settings, store: StateStore, provider: ModelProvider):
        self.settings = settings
        self.store = store
        self.provider = provider

    def session(self, session_id: str, messages: list[dict[str, Any]]) -> SessionState:
        state = self.store.get(session_id) or SessionState(session_id=session_id)
        if not state.objective:
            state.objective = next(
                (
                    str(message.get("content", ""))
                    for message in messages
                    if message["role"] == "user"
                ),
                "",
            )
        self._observe(state, messages)
        if state.step_count >= self.settings.limits.max_steps:
            state.phase = Phase.BLOCKED
            self.store.save(state)
            raise ValueError("session step budget exhausted")
        return state

    def _observe(self, state: SessionState, messages: list[dict[str, Any]]) -> None:
        for index, message in enumerate(messages):
            if message.get("role") == "assistant" and message.get("tool_calls"):
                calls = message["tool_calls"]
                if len(calls) > 1:
                    raise ValueError("executor emitted more than one tool call")
                state.last_tool_call = calls[0]
            if message.get("role") != "tool":
                continue
            observation = str(message.get("content", ""))
            fact = f"tool:{message.get('tool_call_id', index)} {observation}"
            if fact in state.verified_facts:
                continue
            state.verified_facts.append(fact)
            state.verified_facts = state.verified_facts[
                -self.settings.limits.max_retained_observations :
            ]
            state.no_progress_count = 0
            failed = any(
                marker in observation.lower() for marker in ("error", "failed", "exception")
            ) or bool(re.search(r'(?i)(?:"exit_code"\s*:\s*|exit code\s+)[1-9]\d*', observation))
            if failed and state.last_tool_call:
                call_fingerprint = fingerprint(state.last_tool_call)
                if call_fingerprint in state.failed_call_fingerprints:
                    raise DuplicateFailedCall("identical failed tool call blocked")
                state.failed_call_fingerprints.append(call_fingerprint)
                family = failure_family(observation)
                state.failure_families[family] = state.failure_families.get(family, 0) + 1
        if state.no_progress_count >= 3:
            state.phase = Phase.BLOCKED

    def note_no_progress(self, state: SessionState) -> None:
        state.no_progress_count += 1
        if state.no_progress_count >= 3:
            state.phase = Phase.BLOCKED
        self.store.save(state)

    def apply_metadata(self, state: SessionState, metadata: dict[str, Any]) -> None:
        evidence = metadata.get("completion_evidence")
        if isinstance(evidence, dict):
            state.completion_evidence.update(
                {str(criterion): str(value) for criterion, value in evidence.items()}
            )
        risk = ChangeRisk(
            files_changed=int(metadata.get("files_changed", 0)),
            meaningful_lines=int(metadata.get("meaningful_lines", 0)),
            public_api=bool(metadata.get("public_api")),
            authentication=bool(metadata.get("authentication")),
            cryptography=bool(metadata.get("cryptography")),
            database_schema=bool(metadata.get("database_schema")),
            deployment_security=bool(metadata.get("deployment_security")),
            explicit=bool(metadata.get("heavy_review")),
        )
        if heavy_eligible(state, risk):
            state.judge_status = "eligible"
            state.phase = Phase.AWAITING_HEAVY_JUDGE
        elif completion_ready(state):
            state.phase = Phase.COMPLETED
        self.store.save(state)

    def prompt_sandwich(
        self,
        role: str,
        state: SessionState,
        observation: str,
        decision: str,
    ) -> str:
        schema = {
            "planner": '{"plan":[{"step":"..."}],"acceptance_criteria":["..."]}',
            "reviewer": '{"status":"approved|rejected","findings":[]}',
            "judge": json.dumps(JudgeVerdict.model_json_schema(), separators=(",", ":")),
        }.get(role, "OpenAI assistant message or one tool call")
        return "\n\n".join(
            (
                f"IMMUTABLE ROLE POLICY\n{role} policy applies; read-only unless executor.",
                f"EXACT OUTPUT SCHEMA\n{schema}",
                "COMPRESSED VERIFIED STATE\n"
                + json.dumps(redact(state.model_dump()), ensure_ascii=False),
                f"CURRENT OBJECTIVE\n{state.objective}",
                f"CURRENT OBSERVATION\n{observation}",
                f"IMMEDIATE DECISION\n{decision}",
                "FINAL CONSTRAINTS\nNo hidden reasoning. No invented facts. Respect output schema.",
            )
        )

    async def prepare_executor(
        self, state: SessionState, request: dict[str, Any]
    ) -> dict[str, Any]:
        if state.phase == Phase.BLOCKED:
            raise ValueError("session blocked after no progress")
        if needs_planner(state) and "planner" in self.settings.models:
            state.phase = Phase.PLANNING
            planner_request = {
                "model": self.settings.models["planner"].served_name,
                "messages": [
                    {
                        "role": "system",
                        "content": self.prompt_sandwich(
                            "planner",
                            state,
                            "New or invalidated task",
                            "Create dependency-ordered plan",
                        ),
                    }
                ],
                "max_tokens": self.settings.limits.planner_tokens,
                "stream": False,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "plan",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "plan": {"type": "array", "items": {"type": "object"}},
                                "acceptance_criteria": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["plan", "acceptance_criteria"],
                            "additionalProperties": False,
                        },
                    },
                },
            }
            planner = await self.provider.complete(
                "planner", self.settings.models["planner"], planner_request
            )
            parsed = parse_json_content(planner)
            state.plan = parsed.get("plan", [])
            state.acceptance_criteria = parsed.get("acceptance_criteria", [])
        state.phase = Phase.EXECUTING
        state.step_count += 1
        self.store.save(state)
        body = request.copy()
        messages = compress_messages(body["messages"], self.settings.limits)
        messages.insert(
            0,
            {
                "role": "system",
                "content": self.prompt_sandwich(
                    "executor", state, "Proceed from verified state", "Take one useful step"
                ),
            },
        )
        body["messages"] = messages
        body["max_tokens"] = min(
            int(body.get("max_tokens") or self.settings.limits.executor_tokens),
            self.settings.limits.executor_tokens,
        )
        return body

    async def review(self, state: SessionState, observation: str) -> dict[str, Any]:
        state.phase = Phase.REVIEWING
        request = {
            "model": self.settings.models["reviewer"].served_name,
            "messages": [
                {
                    "role": "system",
                    "content": self.prompt_sandwich(
                        "reviewer",
                        state,
                        observation,
                        "Review correctness and requirement coverage",
                    ),
                }
            ],
            "max_tokens": self.settings.limits.reviewer_tokens,
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "review",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "status": {"type": "string", "enum": ["approved", "rejected"]},
                            "findings": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["status", "findings"],
                        "additionalProperties": False,
                    },
                },
            },
        }
        response = await self.provider.complete(
            "reviewer", self.settings.models["reviewer"], request
        )
        result = parse_json_content(response)
        state.review_status = result.get("status", "rejected")
        state.phase = Phase.CORRECTION if state.review_status != "approved" else Phase.EXECUTING
        self.store.save(state)
        return result

    async def judge(self, state: SessionState, observation: str) -> dict[str, Any]:
        state.phase = Phase.HEAVY_REVIEW
        schema = JudgeVerdict.model_json_schema()
        request = {
            "model": self.settings.models["judge"].served_name,
            "messages": [
                {
                    "role": "system",
                    "content": self.prompt_sandwich(
                        "judge",
                        state,
                        observation,
                        "Resolve disagreements and decide completion",
                    ),
                }
            ],
            "max_tokens": self.settings.limits.judge_tokens,
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "judge_verdict", "strict": True, "schema": schema},
            },
        }
        response = await self.provider.complete("judge", self.settings.models["judge"], request)
        verdict = JudgeVerdict.model_validate(parse_json_content(response))
        result = verdict.model_dump()
        state.judge_status = verdict.verdict
        state.heavy_switch_count += 1
        if verdict.verdict == "blocked":
            state.phase = Phase.BLOCKED
        elif verdict.verdict == "accept" and verdict.completion_allowed:
            state.phase = Phase.COMPLETED
        else:
            state.phase = Phase.CORRECTION
        self.store.save(state)
        return result
