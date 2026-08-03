from __future__ import annotations

import asyncio
import os
from abc import ABC, abstractmethod
from collections import OrderedDict
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from .evidence import active_failures, effective_objective
from .security import redact
from .state import SessionState
from .training import sanitize


def selective_judge_reasons(
    enabled: bool,
    state: SessionState,
    metadata: dict[str, Any],
    response: dict[str, Any] | None = None,
) -> list[str]:
    if not enabled or state.judge_status in {"approve", "reject", "escalate"}:
        return []
    if response is not None:
        message = (response.get("choices") or [{}])[0].get("message", {})
        if message.get("tool_calls"):
            return []
    trigger_fields = {
        "authentication": "security_or_authentication_change",
        "cryptography": "security_or_authentication_change",
        "security_sensitive_change": "security_or_authentication_change",
        "database_schema": "database_schema_or_migration",
        "destructive_migration": "database_schema_or_migration",
        "concurrency": "concurrency_or_state_machine_change",
        "state_machine": "concurrency_or_state_machine_change",
        "destructive_action": "destructive_action",
        "production_deployment": "production_deployment_approval",
        "production_skill_promotion": "production_skill_promotion",
        "prompt_promotion": "runtime_candidate_promotion",
        "policy_promotion": "runtime_candidate_promotion",
        "routing_promotion": "runtime_candidate_promotion",
        "weekly_gold_candidate": "weekly_gold_candidate",
        "tests_claim_inconsistent": "test_result_claim_inconsistency",
        "unresolved_disagreement": "reviewer_frontier_disagreement",
    }
    reasons = [reason for field, reason in trigger_fields.items() if metadata.get(field)]
    if state.request_class == "high_risk_task" or metadata.get("heavy_review"):
        reasons.append("high_or_critical_risk")
    if state.review_status.startswith("rejected"):
        reasons.append("unresolved_reviewer_finding")
    if any(count >= 2 for count in state.failure_families.values()):
        reasons.append("repeated_failure_fingerprint")
    return list(dict.fromkeys(reasons))


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


def judge_evidence_package(
    state: SessionState,
    observation: str,
    risk_class: Literal["low", "medium", "high", "critical"],
) -> JudgeEvidencePackage:
    metadata = {
        key: item
        for decision in state.decisions[-8:]
        for key, item in decision.items()
        if key in {"changed_paths", "diff_summary", "validation_results", "build_results"}
    }
    package = JudgeEvidencePackage(
        request_id=state.current_request_id or state.session_id,
        objective=effective_objective(state),
        request_constraints=list(state.acceptance_criteria),
        risk_class=risk_class,
        acceptance_criteria=(
            [item.model_dump(mode="json") for item in state.engineering_loop.acceptance_criteria]
            if state.engineering_loop is not None
            else list(state.acceptance_criteria)
        ),
        executor_draft=observation,
        changed_diff_summary=list(metadata.get("diff_summary", []))
        if isinstance(metadata.get("diff_summary"), list)
        else [metadata["diff_summary"]]
        if metadata.get("diff_summary")
        else [],
        tool_evidence=state.tool_results[-8:],
        test_evidence=list(metadata.get("validation_results", []))
        if isinstance(metadata.get("validation_results"), list)
        else [],
        build_evidence=list(metadata.get("build_results", []))
        if isinstance(metadata.get("build_results"), list)
        else [],
        reviewer_findings=[
            item for item in state.agent_artifacts[-8:] if item.get("role") == "reviewer"
        ],
        frontier_findings=[
            item for item in state.agent_artifacts[-8:] if item.get("role") == "frontier"
        ],
        open_failures=active_failures(state)[-8:],
        resolved_failures=[
            item for item in state.failures[-8:] if item.get("resolution_status") == "resolved"
        ],
        policy_decisions=state.policy_decisions[-8:],
        selected_skills=state.skill_selections[-8:],
        retrieved_knowledge=state.knowledge_selections[-8:],
    )
    if state.repository_training_policy not in {"internal_only", "training_denied"}:
        return package
    criteria = [
        {
            key: item[key]
            for key in ("criterion_id", "required", "state", "evidence_ids")
            if key in item
        }
        for item in package.acceptance_criteria
        if isinstance(item, dict)
    ]
    evidence_fields = {
        "id",
        "status",
        "exit_code",
        "failure_class",
        "tool_name",
        "evidence_ids",
    }
    return package.model_copy(
        update={
            "objective": "[WITHHELD_BY_REPOSITORY_POLICY]",
            "request_constraints": [],
            "acceptance_criteria": criteria,
            "executor_draft": "[WITHHELD_BY_REPOSITORY_POLICY]",
            "changed_diff_summary": [],
            "tool_evidence": [
                {key: value for key, value in item.items() if key in evidence_fields}
                for item in package.tool_evidence
                if isinstance(item, dict)
            ],
            "test_evidence": [
                {key: value for key, value in item.items() if key in evidence_fields}
                for item in package.test_evidence
                if isinstance(item, dict)
            ],
            "build_evidence": [
                {key: value for key, value in item.items() if key in evidence_fields}
                for item in package.build_evidence
                if isinstance(item, dict)
            ],
            "reviewer_findings": [],
            "frontier_findings": [],
            "open_failures": [],
            "resolved_failures": [],
            "policy_decisions": [],
            "selected_skills": [],
            "retrieved_knowledge": [],
        }
    )


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
    def __init__(self, verdict: RemoteJudgeVerdict | list[RemoteJudgeVerdict]):
        self.verdicts = list(verdict) if isinstance(verdict, list) else [verdict]
        self.packages: list[JudgeEvidencePackage] = []

    async def judge(self, package: JudgeEvidencePackage) -> RemoteJudgeVerdict:
        self.packages.append(package.sanitized())
        return self.verdicts[min(len(self.packages) - 1, len(self.verdicts) - 1)]

    async def available(self) -> bool:
        return True


class OpenCodeGoJudgeProvider(JudgeProvider):
    def __init__(
        self,
        *,
        endpoint: str,
        api_key_env: str,
        model: str = "glm-5.2",
        timeout_seconds: float = 120,
        max_retries: int = 1,
        max_calls_per_request: int = 2,
        transport: httpx.AsyncBaseTransport | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.api_key_env = api_key_env
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.max_calls_per_request = max_calls_per_request
        self.transport = transport
        self.client = client
        self._calls: OrderedDict[str, int] = OrderedDict()
        self._usage: OrderedDict[str, dict[str, int]] = OrderedDict()
        self._call_lock = asyncio.Lock()

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        if self.client is not None:
            return await self.client.request(
                method, url, timeout=self.timeout_seconds, **kwargs
            )
        async with httpx.AsyncClient(
            transport=self.transport, timeout=self.timeout_seconds
        ) as client:
            return await client.request(method, url, **kwargs)

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
            response = await self._request(
                "GET", self._url("models"), headers=self._headers()
            )
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
                        "the schema; do not include hidden reasoning or prose outside it. "
                        "Approve only when every acceptance criterion is supported and no "
                        "open failure contradicts the draft. For approve, return no findings, "
                        "no required edits, and no recheck. For every non-approval caused by "
                        "an unsupported claim, failed criterion, or open failure, return at "
                        "least one evidence-linked finding and one bounded required edit; do "
                        "not replace the final response wholesale. Request a recheck only "
                        "when an Important or Critical correction must be validated."
                    ),
                },
                {"role": "user", "content": evidence.model_dump_json()},
            ],
            "temperature": 0,
            "max_tokens": 1024,
            "seed": 0,
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
                response = await self._request(
                    "POST",
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
