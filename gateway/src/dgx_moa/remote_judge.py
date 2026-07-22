from __future__ import annotations

import asyncio
import os
from abc import ABC, abstractmethod
from collections import OrderedDict
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from .security import redact
from .training import sanitize


class JudgeEvidencePackage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    request_id: str
    objective: str
    request_constraints: list[str] = Field(default_factory=list)
    risk_class: Literal["low", "medium", "high", "critical"] = "low"
    acceptance_criteria: list[Any] = Field(default_factory=list)
    executor_draft: str = ""
    changed_diff_summary: list[Any] = Field(default_factory=list)
    tool_evidence: list[Any] = Field(default_factory=list)
    test_evidence: list[Any] = Field(default_factory=list)
    build_evidence: list[Any] = Field(default_factory=list)
    reviewer_findings: list[Any] = Field(default_factory=list)
    frontier_findings: list[Any] = Field(default_factory=list)
    open_failures: list[Any] = Field(default_factory=list)
    resolved_failures: list[Any] = Field(default_factory=list)
    policy_decisions: list[Any] = Field(default_factory=list)
    selected_skills: list[Any] = Field(default_factory=list)
    retrieved_knowledge: list[Any] = Field(default_factory=list)
    specific_judgment_question: str = "Is this result ready for final delivery?"

    def sanitized(self) -> JudgeEvidencePackage:
        cleaned = sanitize(redact(self.model_dump(mode="json"))).value
        return JudgeEvidencePackage.model_validate(cleaned)


class JudgeFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_id: str
    severity: Literal["info", "minor", "important", "critical"]
    category: str
    evidence_ids: list[str] = Field(default_factory=list)
    target: str
    description: str
    required_action: str


class JudgeEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["remove", "replace", "insert", "revalidate"]
    target: str
    instruction: str


class JudgeCriteria(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction_following: Literal["pass", "partial", "fail", "unknown"]
    evidence_grounding: Literal["pass", "partial", "fail", "unknown"]
    logical_consistency: Literal["pass", "partial", "fail", "unknown"]
    tool_consistency: Literal["pass", "partial", "fail", "unknown"]
    test_consistency: Literal["pass", "partial", "fail", "unknown"]
    safety: Literal["pass", "partial", "fail", "unknown"]
    completeness: Literal["pass", "partial", "fail", "unknown"]


class RemoteJudgeVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal[
        "approve", "approve_with_edits", "revise", "retry_with_evidence", "escalate", "reject"
    ]
    risk: Literal["low", "medium", "high", "critical"]
    criteria: JudgeCriteria
    findings: list[JudgeFinding] = Field(default_factory=list)
    required_edits: list[JudgeEdit] = Field(default_factory=list)
    recheck_required: bool
    confidence_class: Literal["low", "medium", "high"]


class JudgeProviderError(RuntimeError):
    pass


class JudgeUnavailable(JudgeProviderError):
    pass


class JudgeTimeout(JudgeUnavailable):
    pass


class JudgeRateLimited(JudgeUnavailable):
    pass


class JudgeCallLimitExceeded(JudgeProviderError):
    pass


class JudgeProvider(ABC):
    @abstractmethod
    async def judge(self, package: JudgeEvidencePackage) -> RemoteJudgeVerdict:
        raise NotImplementedError

    @abstractmethod
    async def available(self) -> bool:
        raise NotImplementedError

    async def usage(self, request_id: str) -> dict[str, int]:
        del request_id
        return {}


class DisabledJudgeProvider(JudgeProvider):
    async def judge(self, package: JudgeEvidencePackage) -> RemoteJudgeVerdict:
        del package
        raise JudgeUnavailable("Remote Judge is disabled")

    async def available(self) -> bool:
        return False


class MockJudgeProvider(JudgeProvider):
    def __init__(self, verdict: RemoteJudgeVerdict):
        self.verdict = verdict
        self.packages: list[JudgeEvidencePackage] = []

    async def judge(self, package: JudgeEvidencePackage) -> RemoteJudgeVerdict:
        self.packages.append(package.sanitized())
        return self.verdict

    async def available(self) -> bool:
        return True


class NvidiaNimJudgeProvider(JudgeProvider):
    def __init__(
        self,
        *,
        endpoint: str,
        api_key_env: str,
        model: str = "z-ai/glm-5.2",
        timeout_seconds: float = 120,
        max_retries: int = 1,
        max_calls_per_request: int = 2,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.api_key_env = api_key_env
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.max_calls_per_request = max_calls_per_request
        self.transport = transport
        self._calls: OrderedDict[str, int] = OrderedDict()
        self._usage: OrderedDict[str, dict[str, int]] = OrderedDict()
        self._call_lock = asyncio.Lock()

    def _url(self, resource: str) -> str:
        base = self.endpoint if self.endpoint.endswith("/v1") else f"{self.endpoint}/v1"
        return f"{base}/{resource.lstrip('/')}"

    def _headers(self) -> dict[str, str]:
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise JudgeUnavailable(
                f"Remote Judge credential environment is unset: {self.api_key_env}"
            )
        return {"Authorization": f"Bearer {api_key}"}

    async def _admit(self, request_id: str) -> None:
        async with self._call_lock:
            calls = self._calls.get(request_id, 0) + 1
            if calls > self.max_calls_per_request:
                raise JudgeCallLimitExceeded("Remote Judge call budget exhausted")
            self._calls[request_id] = calls
            self._calls.move_to_end(request_id)
            # ponytail: bounded process-local ledger; persist it if cross-restart budgets matter.
            while len(self._calls) > 10_000:
                self._calls.popitem(last=False)

    async def available(self) -> bool:
        try:
            async with httpx.AsyncClient(
                transport=self.transport, timeout=self.timeout_seconds
            ) as client:
                response = await client.get(self._url("models"), headers=self._headers())
                response.raise_for_status()
            return True
        except (httpx.HTTPError, JudgeUnavailable):
            return False

    async def judge(self, package: JudgeEvidencePackage) -> RemoteJudgeVerdict:
        await self._admit(package.request_id)
        evidence = package.sanitized()
        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an independent read-only engineering quality Judge. "
                        "Use only the supplied evidence. Return one JSON object matching "
                        "the schema."
                    ),
                },
                {"role": "user", "content": evidence.model_dump_json()},
            ],
            "temperature": 0,
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "judge-verdict-v1",
                    "strict": True,
                    "schema": RemoteJudgeVerdict.model_json_schema(),
                },
            },
        }
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    transport=self.transport, timeout=self.timeout_seconds
                ) as client:
                    response = await client.post(
                        self._url("chat/completions"),
                        headers=self._headers(),
                        json=body,
                    )
                    if response.status_code == 429 or response.status_code >= 500:
                        response.raise_for_status()
                    response.raise_for_status()
                    payload = response.json()
                content = payload["choices"][0]["message"]["content"]
                verdict = RemoteJudgeVerdict.model_validate_json(content)
                raw_usage = payload.get("usage", {})
                usage = {
                    key: int(raw_usage[key])
                    for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                    if isinstance(raw_usage.get(key), int)
                }
                async with self._call_lock:
                    self._usage[package.request_id] = usage
                    self._usage.move_to_end(package.request_id)
                    while len(self._usage) > 10_000:
                        self._usage.popitem(last=False)
                return verdict
            except httpx.TimeoutException as error:
                if attempt == self.max_retries:
                    raise JudgeTimeout("Remote Judge timed out") from error
            except httpx.HTTPStatusError as error:
                if attempt == self.max_retries:
                    if error.response.status_code == 429:
                        raise JudgeRateLimited("Remote Judge rate limited") from error
                    raise JudgeUnavailable("Remote Judge provider unavailable") from error
            except (KeyError, TypeError, ValueError) as error:
                raise JudgeProviderError(
                    "Remote Judge returned invalid structured output"
                ) from error
        raise AssertionError("unreachable")

    async def usage(self, request_id: str) -> dict[str, int]:
        async with self._call_lock:
            return dict(self._usage.get(request_id, {}))
