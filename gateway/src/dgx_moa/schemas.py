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
        if reasoner_mode is not None and reasoner_mode not in {"required", "optional"}:
            raise ValueError("metadata.reasoner_mode must be required or optional")
        if reasoner_mode is not None and self.model != "dgx-moa-orchestrated":
            raise ValueError("metadata.reasoner_mode requires dgx-moa-orchestrated")
        return self


class ResponsesRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    input: str | list[str | dict[str, Any]]
    stream: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    max_output_tokens: int | None = Field(default=None, gt=0)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    stop: str | list[str] | None = None

    @model_validator(mode="after")
    def require_input(self) -> ResponsesRequest:
        if isinstance(self.input, list) and not self.input:
            raise ValueError("input must not be empty")
        return self


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
