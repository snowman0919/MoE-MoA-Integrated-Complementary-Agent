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
    max_tokens: int | None = Field(default=None, gt=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_messages(self) -> ChatRequest:
        if not self.messages:
            raise ValueError("messages must not be empty")
        return self


class ProfileResponse(BaseModel):
    active_profile: Literal["resident", "judge", "stopped"]
    status: Literal["ready", "transitioning", "failed", "stopped"]
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
