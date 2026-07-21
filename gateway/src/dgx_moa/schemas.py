from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    stream: bool = False
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
        for message in self.input:
            if not isinstance(message, dict):
                raise ValueError("input entries must be message objects")
            if not isinstance(message.get("role"), str):
                raise ValueError("input message must include role")
            if message.get("content") is None:
                raise ValueError("input message must include content")
        return self


class AdditionalAgentRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["planner", "reviewer", "frontier", "judge"]
    needed: bool
    reason: str


class ReasonerContribution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    problem_interpretation: str
    constraints: list[str]
    reasoning: list[str]
    risks: list[str]
    unknowns: list[str]
    recommended_actions: list[str]
    additional_agents: list[AdditionalAgentRecommendation]
    confidence: float = Field(ge=0, le=1)


class OrchestrationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["respond", "invoke_agents"]
    required_agents: list[Literal["planner", "reviewer", "frontier", "judge"]]
    optional_agents: list[Literal["planner", "reviewer", "frontier", "judge"]]
    reason: dict[str, str]
    parallelizable: bool
    continue_after: Literal["respond", "synthesize", "reason_again"]
    confidence: float = Field(ge=0, le=1)


class ReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["approved", "rejected"]
    findings: list[str]


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
