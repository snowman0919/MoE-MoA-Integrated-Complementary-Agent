from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def text_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(
            part["text"]
            for part in value
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        )
    return "" if value is None else str(value)


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: Literal["system", "user", "assistant", "tool", "developer"]
    content: str | list[dict[str, Any]] | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[ChatMessage]
    stream: bool = False
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    parallel_tool_calls: bool | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, gt=0)
    stop: str | list[str] | None = None
    stream_options: dict[str, Any] | None = None
    response_format: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_messages(self) -> ChatRequest:
        if not self.messages:
            raise ValueError("messages must not be empty")
        if self.tool_choice is not None and not self.tools:
            raise ValueError("tool_choice requires tools")
        if self.parallel_tool_calls is not None and not self.tools:
            raise ValueError("parallel_tool_calls requires tools")
        if self.stream_options is not None and not self.stream:
            raise ValueError("stream_options requires stream=true")
        reasoner_mode = self.metadata.get("reasoner_mode")
        if reasoner_mode is not None and reasoner_mode != "required":
            raise ValueError("Reasoner is required; use dgx-moa-fast to bypass it")
        if reasoner_mode is not None and self.model != "dgx-moa-orchestrated":
            raise ValueError("metadata.reasoner_mode requires dgx-moa-orchestrated")
        return self


class ResponsesRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    input: str | list[dict[str, Any]]
    instructions: str | None = None
    stream: bool = False
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    parallel_tool_calls: bool | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    max_output_tokens: int | None = Field(default=None, gt=0)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    stop: str | list[str] | None = None

    @model_validator(mode="after")
    def require_input_messages(self) -> ResponsesRequest:
        if isinstance(self.input, str):
            if not self.input.strip():
                raise ValueError("input must not be empty")
            return self
        if not self.input:
            raise ValueError("input must not be empty")
        for item in self.input:
            if not isinstance(item, dict):
                raise ValueError("input entries must be message objects")
            item_type = item.get("type")
            if item_type == "reasoning":
                continue
            if item_type in {"function_call", "custom_tool_call"}:
                if not all(isinstance(item.get(key), str) for key in ("call_id", "name")):
                    raise ValueError(f"{item_type} must include call_id and name")
                value_key = "arguments" if item_type == "function_call" else "input"
                if not isinstance(item.get(value_key), str):
                    raise ValueError(f"{item_type} must include {value_key}")
                continue
            if item_type in {"function_call_output", "custom_tool_call_output"}:
                if not isinstance(item.get("call_id"), str) or "output" not in item:
                    raise ValueError(f"{item_type} must include call_id and output")
                continue
            if not isinstance(item.get("role"), str):
                raise ValueError("input message must include role")
            if item.get("content") is None:
                raise ValueError("input message must include content")
        return self


class AdditionalAgentRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["planner", "reviewer", "frontier", "judge"]
    needed: bool
    reason: str


class ReasonerContribution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assumptions: list[str]
    constraints: list[str]
    conclusions: list[str]
    hypotheses: list[str]
    evidence_references: list[str]
    recommended_actions: list[str]
    additional_agents: list[AdditionalAgentRecommendation]
    confidence_category: Literal["low", "medium", "high"]

    @model_validator(mode="before")
    @classmethod
    def discard_legacy_reasoning(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "confidence_category" in value:
            return value
        legacy = dict(value)
        confidence = legacy.pop("confidence", 0.5)
        interpretation = legacy.pop("problem_interpretation", "")
        legacy.pop("reasoning", None)
        risks = legacy.pop("risks", [])
        unknowns = legacy.pop("unknowns", [])
        legacy.setdefault("assumptions", [])
        legacy.setdefault("conclusions", [interpretation] if interpretation else [])
        legacy.setdefault("hypotheses", [*risks, *unknowns])
        legacy.setdefault("evidence_references", [])
        legacy["confidence_category"] = (
            "high" if float(confidence) >= 0.8 else "low" if float(confidence) < 0.5 else "medium"
        )
        return legacy


class OrchestrationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["respond", "invoke_agents"]
    required_agents: list[Literal["planner", "reviewer", "frontier", "judge"]]
    optional_agents: list[Literal["planner", "reviewer", "frontier", "judge"]]
    reason: dict[str, str]
    parallelizable: bool
    continue_after: Literal["respond", "synthesize", "reason_again"]
    confidence: float = Field(ge=0, le=1)


class PlannerStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1, max_length=128)
    action: str = Field(min_length=1, max_length=2_000)
    dependencies: list[str]
    expected_evidence: list[str]


class PlannerPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: list[str]
    assumptions: list[str]
    ordered_steps: list[PlannerStep]
    dependencies: list[str]
    risks: list[str]
    validation_plan: list[str]
    rollback_plan: list[str]
    acceptance_criteria: list[str]

    @model_validator(mode="before")
    @classmethod
    def convert_legacy_plan(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "ordered_steps" in value or "plan" not in value:
            return value
        legacy = dict(value)
        steps = legacy.pop("plan")
        legacy["ordered_steps"] = [
            {
                "step_id": f"step-{index}",
                "action": str(item.get("step", item)) if isinstance(item, dict) else str(item),
                "dependencies": [],
                "expected_evidence": [],
            }
            for index, item in enumerate(steps, 1)
        ]
        for field in (
            "scope",
            "assumptions",
            "dependencies",
            "risks",
            "validation_plan",
            "rollback_plan",
        ):
            legacy.setdefault(field, [])
        return legacy


class ReviewFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_id: str = Field(min_length=1, max_length=128)
    severity: Literal["info", "minor", "important", "critical"]
    category: str = Field(min_length=1, max_length=128)
    evidence_references: list[str]
    affected_location: str = Field(min_length=1, max_length=512)
    impact: str = Field(min_length=1, max_length=2_000)
    required_correction: str = Field(min_length=1, max_length=2_000)
    optional_recommendation: str | None = Field(default=None, max_length=2_000)


class ReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["approved", "rejected"]
    findings: list[ReviewFinding]


class ProfileResponse(BaseModel):
    active_profile: Literal["resident", "judge", "stopped"]
    status: Literal["ready", "transitioning", "failed", "degraded", "stopped"]
    updated_at: str
    from_profile: str | None = Field(default=None, alias="from")
    to: str | None = None


class ResolvedDisagreement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    decision: str
    evidence: list[str]


class MandatoryChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_id: str
    problem: str
    required_correction: str


class JudgeVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal["accept", "revise", "reject", "blocked"]
    summary: str
    resolved_disagreements: list[ResolvedDisagreement]
    mandatory_changes: list[MandatoryChange]
    risk_level: Literal["low", "medium", "high", "critical"]
    completion_allowed: bool
