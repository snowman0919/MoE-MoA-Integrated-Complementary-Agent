from __future__ import annotations

import copy
import fnmatch
import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PolicyActions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    require: dict[str, bool] = Field(default_factory=dict)
    recommend: dict[str, bool] = Field(default_factory=dict)
    deny: dict[str, bool | list[str]] = Field(default_factory=dict)
    limit: dict[str, int | float] = Field(default_factory=dict)
    redact: list[str] = Field(default_factory=list, max_length=64)
    request_approval: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("limit")
    @classmethod
    def validate_limits(cls, value: dict[str, int | float]) -> dict[str, int | float]:
        if any(isinstance(item, bool) or item < 0 for item in value.values()):
            raise ValueError("policy limits must be nonnegative numbers")
        return value


class PolicyRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    when: dict[str, Any]
    actions: PolicyActions = Field(default_factory=PolicyActions)

    @model_validator(mode="before")
    @classmethod
    def collect_action_keys(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        action_keys = {"require", "recommend", "deny", "limit", "redact", "request_approval"}
        if "actions" not in value and action_keys.intersection(value):
            value = dict(value)
            value["actions"] = {key: value.pop(key) for key in tuple(value) if key in action_keys}
        return value

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if (
            not value
            or len(value) > 64
            or not all(
                character.islower() or character.isdigit() or character in "-."
                for character in value
            )
        ):
            raise ValueError("invalid policy ID")
        return value

    @field_validator("when")
    @classmethod
    def validate_condition(cls, value: dict[str, Any]) -> dict[str, Any]:
        def visit(condition: object, depth: int = 0) -> None:
            if depth > 8 or not isinstance(condition, dict) or not condition:
                raise ValueError("invalid policy condition")
            if set(condition).intersection({"any", "all"}):
                if len(condition) != 1:
                    raise ValueError("policy boolean condition must have one operator")
                children = next(iter(condition.values()))
                if not isinstance(children, list) or not children or len(children) > 32:
                    raise ValueError("invalid policy condition list")
                for child in children:
                    visit(child, depth + 1)
                return
            if len(condition) != 1:
                raise ValueError("policy leaf condition must have one comparison")

        visit(value)
        return value


class PolicySet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    policies: list[PolicyRule] = Field(default_factory=list, max_length=256)

    @model_validator(mode="after")
    def unique_ids(self) -> PolicySet:
        ids = [rule.id for rule in self.policies]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate policy ID")
        return self

    def content_hash(self) -> str:
        return hashlib.sha256(
            json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


class PolicyDecision(BaseModel):
    policy_version: str
    policy_hash: str
    matched_rules: list[str]
    require: dict[str, bool]
    recommend: dict[str, bool]
    deny: dict[str, bool | list[str]]
    limits: dict[str, int | float]
    redact: list[str]
    approvals_required: list[str]

    @property
    def request_denied(self) -> bool:
        return bool(self.deny.get("request"))


def lookup(context: dict[str, Any], dotted: str) -> Any:
    current: Any = context
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def redact_fields(value: Any, dotted_paths: list[str]) -> Any:
    result = copy.deepcopy(value)
    for dotted in dotted_paths:
        current = result
        parts = dotted.split(".")
        for part in parts[:-1]:
            if not isinstance(current, dict) or part not in current:
                current = None
                break
            current = current[part]
        if isinstance(current, dict) and parts[-1] in current:
            original = current[parts[-1]]
            current[parts[-1]] = (
                []
                if isinstance(original, list)
                else {}
                if isinstance(original, dict)
                else "[REDACTED_BY_POLICY]"
            )
    return result


def condition_matches(condition: dict[str, Any], context: dict[str, Any]) -> bool:
    if "any" in condition:
        children = condition["any"]
        return isinstance(children, list) and any(
            isinstance(child, dict) and condition_matches(child, context) for child in children
        )
    if "all" in condition:
        children = condition["all"]
        return isinstance(children, list) and all(
            isinstance(child, dict) and condition_matches(child, context) for child in children
        )
    key, expected = next(iter(condition.items()))
    if key == "changed_paths_match":
        paths = context.get("changed_paths", [])
        return (
            isinstance(paths, list)
            and isinstance(expected, list)
            and any(
                fnmatch.fnmatch(str(path), str(pattern)) for path in paths for pattern in expected
            )
        )
    if key.endswith("_gte"):
        actual = lookup(context, key.removesuffix("_gte"))
        return (
            isinstance(actual, int | float)
            and not isinstance(actual, bool)
            and isinstance(expected, int | float)
            and not isinstance(expected, bool)
            and actual >= expected
        )
    return bool(lookup(context, key) == expected)


class PolicyEngine:
    def __init__(self, policy_set: PolicySet):
        self.policy_set = policy_set

    def evaluate(self, context: dict[str, Any]) -> PolicyDecision:
        matched = [
            rule for rule in self.policy_set.policies if condition_matches(rule.when, context)
        ]
        require: dict[str, bool] = {}
        recommend: dict[str, bool] = {}
        deny: dict[str, bool | list[str]] = {}
        limits: dict[str, int | float] = {}
        redactions: list[str] = []
        approvals: list[str] = []
        for rule in matched:
            require.update(rule.actions.require)
            recommend.update(rule.actions.recommend)
            deny.update(rule.actions.deny)
            for name, value in rule.actions.limit.items():
                current = limits.get(name)
                limits[name] = value if current is None else min(current, value)
            redactions.extend(rule.actions.redact)
            approvals.extend(rule.actions.request_approval)
        return PolicyDecision(
            policy_version=self.policy_set.version,
            policy_hash=self.policy_set.content_hash(),
            matched_rules=[rule.id for rule in matched],
            require=require,
            recommend=recommend,
            deny=deny,
            limits=limits,
            redact=list(dict.fromkeys(redactions)),
            approvals_required=list(dict.fromkeys(approvals)),
        )
