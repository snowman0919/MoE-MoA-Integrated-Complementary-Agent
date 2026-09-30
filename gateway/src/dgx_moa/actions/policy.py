"""Action policy: deterministic authority with optional Laya shadow."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol

from .types import (
    ActionDecision,
    ActionIntent,
    CandidateAction,
    CapabilitySnapshot,
    resource_references,
    semantic_fingerprint,
)

POLICY_CHOICES = ("NO_ACTION", "RESOLVE_RESOURCE", "REPLAN")


class PolicyBackend(Protocol):
    def choose(
        self, snapshot: CapabilitySnapshot, candidates: list[CandidateAction]
    ) -> int | None: ...


@dataclass
class DeterministicPolicy:
    """Production-safe authority: first executable candidate wins."""

    def choose(self, snapshot: CapabilitySnapshot, candidates: list[CandidateAction]) -> int | None:
        for index, candidate in enumerate(candidates):
            if candidate.capability_id in snapshot.capabilities:
                return index
        return None


@dataclass
class LayaPolicyAdapter:
    """Optional decision assistant over a finite candidate set.

    Laya only returns an index into runtime-provided candidates. Any other
    value falls back to the deterministic policy. Transport is an isolated
    loopback decision service; the gateway never imports Torch here.
    """

    endpoint: str = ""
    timeout_seconds: float = 2.0
    enabled: bool = False

    def choose(self, snapshot: CapabilitySnapshot, candidates: list[CandidateAction]) -> int | None:
        if not self.enabled or not self.endpoint or not candidates:
            return None
        payload = json.dumps(
            {
                "capabilities": sorted(snapshot.capabilities),
                "candidates": [
                    {"capability_id": item.capability_id, "arguments": item.arguments}
                    for item in candidates
                ],
            }
        ).encode()
        try:
            request = urllib.request.Request(
                self.endpoint, data=payload, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode() or "{}")
            index = body.get("index")
            if isinstance(index, int) and 0 <= index < len(candidates):
                return index
        except Exception:
            return None
        return None


@dataclass
class PolicyEngine:
    deterministic: DeterministicPolicy = field(default_factory=DeterministicPolicy)
    laya: LayaPolicyAdapter = field(default_factory=LayaPolicyAdapter)
    shadow_mode: bool = True
    shadow_agreements: int = 0
    shadow_disagreements: int = 0
    shadow_event: Any = None

    def decide(
        self,
        snapshot: CapabilitySnapshot,
        candidates: list[CandidateAction],
        *,
        intent: ActionIntent | None = None,
    ) -> ActionDecision | None:
        chosen = self.deterministic.choose(snapshot, candidates)
        if chosen is None:
            return None
        self._observe_shadow(snapshot, candidates, chosen)
        return self._decision(snapshot, candidates[chosen], source="deterministic")

    def _decision(
        self, snapshot: CapabilitySnapshot, candidate: CandidateAction, *, source: str
    ) -> ActionDecision | None:
        capability = snapshot.capability(candidate.capability_id)
        if capability is None:
            return None
        resources = resource_references(capability, candidate.arguments)
        fingerprint = semantic_fingerprint(capability, candidate.arguments)
        return ActionDecision(
            candidate=candidate,
            capability=capability,
            resources=resources,
            semantic_fingerprint=fingerprint,
            source=source,
        )

    def _observe_shadow(
        self, snapshot: CapabilitySnapshot, candidates: list[CandidateAction], chosen: int
    ) -> None:
        if not self.shadow_mode or not self.laya.enabled:
            return
        try:
            shadow = self.laya.choose(snapshot, candidates)
        except Exception:
            return
        if shadow is None:
            return
        if shadow == chosen:
            self.shadow_agreements += 1
        else:
            self.shadow_disagreements += 1
        record = self.shadow_event
        if record is not None:
            try:
                record(bool(shadow == chosen))
            except Exception:
                return

    def shadow_metrics(self) -> dict[str, int]:
        return {
            "laya_shadow_agreement": self.shadow_agreements,
            "laya_shadow_disagreement": self.shadow_disagreements,
        }


def candidates_from_tool_calls(
    calls: list[dict[str, Any]],
    snapshot: CapabilitySnapshot,
    *,
    source: str = "executor",
) -> list[CandidateAction]:
    candidates: list[CandidateAction] = []
    for call in calls:
        function = call.get("function") if isinstance(call, dict) else None
        name = function.get("name") if isinstance(function, dict) else None
        raw_arguments = function.get("arguments") if isinstance(function, dict) else None
        if not isinstance(name, str) or not name:
            continue
        capability_id = snapshot.capability_id_for(name)
        if capability_id is None:
            continue
        arguments: dict[str, Any] = {}
        if isinstance(raw_arguments, dict):
            arguments = raw_arguments
        elif isinstance(raw_arguments, str) and raw_arguments.strip():
            try:
                parsed = json.loads(raw_arguments)
                arguments = parsed if isinstance(parsed, dict) else {}
            except ValueError:
                continue
        candidates.append(
            CandidateAction(capability_id=capability_id, arguments=arguments, source=source)
        )
    return candidates
