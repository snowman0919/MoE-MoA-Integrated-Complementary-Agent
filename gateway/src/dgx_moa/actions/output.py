"""Post-execution Output Validation Gate.

The Executor must not decide that work is complete. Before any final
user-visible answer is emitted, the Runtime builds a structured
:class:`CompletionManifest` from canonical runtime evidence, resolves every
material claim against that evidence, rejects stale or unsupported evidence,
and runs one bounded deterministic decision:

``PASS`` | ``REWRITE_ONLY`` | ``REEXECUTE`` | ``RESOLVE_RESOURCE``
| ``ESCALATE_REVIEW`` | ``FAIL_CLOSED``

Only ``PASS`` may reach final user-visible synthesis unchanged. Laya may
assist semantic output validation (choosing from the same finite decision
set, or judging claim support) but may never establish facts: filesystem,
Git, tool results, state DB, traces, permissions, and actual runtime
observations remain the factual authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

OutputDecisionCode = Literal[
    "PASS",
    "REWRITE_ONLY",
    "REEXECUTE",
    "RESOLVE_RESOURCE",
    "ESCALATE_REVIEW",
    "FAIL_CLOSED",
]

OUTPUT_DECISIONS: tuple[OutputDecisionCode, ...] = (
    "PASS",
    "REWRITE_ONLY",
    "REEXECUTE",
    "RESOLVE_RESOURCE",
    "ESCALATE_REVIEW",
    "FAIL_CLOSED",
)

OUTPUT_GATE_METRICS = (
    "output_validation_pass",
    "output_validation_rewrite_only",
    "output_validation_reexecute",
    "output_validation_resolve_resource",
    "output_validation_escalate_review",
    "output_validation_fail_closed",
    "output_validation_laya_shadow_agreement",
    "output_validation_laya_shadow_disagreement",
)

# Executor-adjacent prose that must never count as evidence of completion.
_PROGRESS_ONLY_PATTERNS = (
    "will do",
    "will implement",
    "plan to",
    "going to",
    "todo",
    "next step",
    "in progress",
    "working on",
    "almost done",
    "trust me",
    "should work",
    "probably",
    "likely works",
)

_COMPLETION_VERBS = (
    "implemented",
    "fixed",
    "created",
    "updated",
    "deleted",
    "migrated",
    "refactored",
    "tested",
    "passing",
    "passed",
    "deployed",
    "resolved",
)

_PATH_LIKE = re.compile(r"(?:file://|(?<![A-Za-z0-9_.:/)\]-]))/[^\s\"'\\(),;]+")


def _clean_path(raw: str) -> str:
    return raw.rstrip(".,;:!?").removeprefix("file://")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _manifest_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode()).hexdigest()[:16]


def _as_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return ""


def extract_material_claims(final_text: str, *, limit: int = 8) -> list[dict[str, Any]]:
    """Extract bounded material claims from a draft final answer.

    Deterministic and textual: sentences containing a completion verb, or
    sentences referencing a path-like token, become claims. Anything beyond
    ``limit`` is folded into one residual claim so the decision stays bounded.
    """
    sentences = [
        item.strip() for item in re.split(r"(?<=[.!?])\s+", final_text.strip()) if item.strip()
    ]
    claims: list[dict[str, Any]] = []
    for sentence in sentences:
        lowered = f" {sentence.lower()} "
        paths = sorted({_clean_path(item) for item in _PATH_LIKE.findall(sentence)})
        states_completion = any(f" {verb} " in lowered for verb in _COMPLETION_VERBS)
        if states_completion or paths:
            claims.append(
                {
                    "text": sentence[:500],
                    "states_completion": states_completion,
                    "paths": [path[:256] for path in paths[:8]],
                }
            )
        if len(claims) >= limit:
            break
    if len(sentences) > len(claims) and len(claims) >= limit:
        claims.append({"text": "[residual draft content]", "states_completion": False, "paths": []})
    return claims


@dataclass(frozen=True)
class ClaimResolution:
    claim: dict[str, Any]
    supported: bool
    basis: str
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompletionManifest:
    """Structured completion proposal built only from runtime evidence."""

    manifest_id: str
    objective: str
    final_text: str
    claims: tuple[dict[str, Any], ...]
    resolutions: tuple[ClaimResolution, ...]
    evidence_digest: str
    supported_claims: int
    unsupported_claims: int
    stale_rejected: int
    has_pending_tool_calls: bool
    has_tool_calls_in_draft: bool
    active_failures: int
    review_status: str
    truncated: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_id": self.manifest_id,
            "objective": self.objective,
            "final_text": self.final_text,
            "claims": [dict(item) for item in self.claims],
            "resolutions": [
                {
                    "claim": dict(item.claim),
                    "supported": item.supported,
                    "basis": item.basis,
                    "evidence_ids": list(item.evidence_ids),
                }
                for item in self.resolutions
            ],
            "evidence_digest": self.evidence_digest,
            "supported_claims": self.supported_claims,
            "unsupported_claims": self.unsupported_claims,
            "stale_rejected": self.stale_rejected,
            "has_pending_tool_calls": self.has_pending_tool_calls,
            "has_tool_calls_in_draft": self.has_tool_calls_in_draft,
            "active_failures": self.active_failures,
            "review_status": self.review_status,
            "truncated": self.truncated,
        }


@dataclass(frozen=True)
class OutputGateResult:
    decision: OutputDecisionCode
    reason: str
    manifest: CompletionManifest
    laya_choice: str | None = None
    laya_agrees: bool | None = None


@dataclass
class OutputGateContext:
    objective: str = ""
    final_text: str = ""
    finish_reason: str | None = None
    has_tool_calls_in_draft: bool = False
    pending_tool_call_ids: tuple[str, ...] = ()
    active_failures: tuple[dict[str, Any], ...] = ()
    review_status: str = "pending"
    review_required: bool = False
    truncated: bool = False
    successful_executions: tuple[dict[str, Any], ...] = ()
    failed_executions: tuple[dict[str, Any], ...] = ()
    evidence_nodes: tuple[dict[str, Any], ...] = ()
    verified_facts: tuple[str, ...] = ()
    changed_paths: tuple[str, ...] = ()
    completion_evidence: dict[str, str] = field(default_factory=dict)
    acceptance_criteria: tuple[str, ...] = ()
    unresolved_discovery: tuple[str, ...] = ()
    telemetry: Any = None


def _execution_text(execution: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("tool_name", "stdout_summary", "stderr_summary", "target_paths"):
        value = execution.get(key)
        if isinstance(value, str) and value:
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(str(item) for item in value if isinstance(item, str))
    normalized = execution.get("normalized_arguments")
    if isinstance(normalized, dict):
        parts.extend(str(item) for item in normalized.values() if isinstance(item, str))
    elif isinstance(normalized, str):
        parts.append(normalized)
    return "\n".join(parts).lower()


_VERB_LEMMAS = {
    "implemented": "implement",
    "fixed": "fix",
    "created": "create",
    "updated": "update",
    "deleted": "delete",
    "migrated": "migrate",
    "refactored": "refactor",
    "tested": "test",
    "passing": "pass",
    "passed": "pass",
    "deployed": "deploy",
    "resolved": "resolve",
}


def _claim_verb_lemmas(claim: dict[str, Any]) -> set[str]:
    text = str(claim.get("text", "")).lower()
    padded = f" {text} "
    return {_VERB_LEMMAS[verb] for verb in _COMPLETION_VERBS if f" {verb} " in padded}


def _evidence_verb_lemmas(haystack_padded: str) -> set[str]:
    return {lemma for verb, lemma in _VERB_LEMMAS.items() if f" {verb} " in haystack_padded}


def _claim_supported_by_executions(
    claim: dict[str, Any], executions: tuple[dict[str, Any], ...]
) -> tuple[bool, str, tuple[str, ...]]:
    paths = [str(item).lower() for item in claim.get("paths", []) if isinstance(item, str)]
    if not claim.get("states_completion") and not paths:
        return True, "no material completion assertion", ()
    claim_lemmas = _claim_verb_lemmas(claim)
    matched: list[str] = []
    for execution in executions:
        haystack = _execution_text(execution)
        if not haystack:
            continue
        execution_id = str(execution.get("tool_execution_id", ""))
        haystack = f" {haystack} "
        if paths:
            if any(path and path in haystack for path in paths):
                matched.append(execution_id)
            continue
        if (
            claim.get("states_completion")
            and claim_lemmas
            and claim_lemmas & _evidence_verb_lemmas(haystack)
        ):
            matched.append(execution_id)
    if matched:
        return True, "tool-observed execution evidence", tuple(matched[:4])
    return False, "no tool-observed execution supports this claim", ()


def _claim_supported_by_facts(
    claim: dict[str, Any],
    verified_facts: tuple[str, ...],
    changed_paths: tuple[str, ...],
    nodes: tuple[dict[str, Any], ...],
) -> tuple[bool, str, tuple[str, ...]]:
    paths = [str(item).lower() for item in claim.get("paths", []) if isinstance(item, str)]
    matched: list[str] = []
    claim_lemmas = _claim_verb_lemmas(claim)
    for fact in verified_facts:
        fact_lower = f" {str(fact).lower()} "
        if paths:
            if any(path and path in fact_lower for path in paths):
                matched.append("verified_fact")
                break
        elif (
            claim.get("states_completion")
            and claim_lemmas
            and claim_lemmas & _evidence_verb_lemmas(fact_lower)
        ):
            matched.append("verified_fact")
            break
    lowered_paths = [str(item).lower() for item in changed_paths]
    if not matched and paths and any(path and path in lowered_paths for path in paths):
        matched.append("changed_path")
    if not matched:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if node.get("trust_class") not in {"tool_observed_fact", "test_confirmed_fact"}:
                continue
            payload = f" {_canonical_json(node.get('payload')).lower()} "
            if paths:
                if any(path and path in payload for path in paths):
                    matched.append(str(node.get("node_id", "evidence")))
                    break
            elif (
                claim.get("states_completion")
                and claim_lemmas
                and claim_lemmas & _evidence_verb_lemmas(payload)
            ):
                matched.append(str(node.get("node_id", "evidence")))
                break
    if matched:
        return True, "canonical runtime evidence", tuple(matched[:4])
    return False, "no canonical runtime evidence supports this claim", ()


def build_completion_manifest(context: OutputGateContext) -> CompletionManifest:
    """Build the structured completion proposal from runtime evidence only."""
    claims = extract_material_claims(context.final_text)
    resolutions: list[ClaimResolution] = []
    stale_rejected = 0
    for claim in claims:
        ok, basis, evidence_ids = _claim_supported_by_executions(
            claim, context.successful_executions
        )
        if not ok:
            ok, basis, evidence_ids = _claim_supported_by_facts(
                claim, context.verified_facts, context.changed_paths, context.evidence_nodes
            )
        if not ok and str(claim.get("text", "")).lower() in {
            str(fact).lower() for fact in context.verified_facts
        }:
            ok, basis, evidence_ids = True, "verified fact restatement", ("verified_fact",)
        # Stale progress prose that asserts completion without any backing
        # evidence is rejected, never promoted.
        lowered = str(claim.get("text", "")).lower()
        if not ok and any(marker in lowered for marker in _PROGRESS_ONLY_PATTERNS):
            stale_rejected += 1
        resolutions.append(
            ClaimResolution(
                claim=claim, supported=ok, basis=basis, evidence_ids=tuple(evidence_ids)
            )
        )
    supported = sum(1 for item in resolutions if item.supported)
    unsupported = len(resolutions) - supported
    evidence_digest = _manifest_hash(
        {
            "objective": context.objective,
            "executions": [
                {
                    "tool": str(item.get("tool_name", "")),
                    "exit": item.get("exit_code"),
                    "paths": sorted(
                        {
                            str(path)
                            for key in ("changed_paths", "created_paths", "deleted_paths")
                            for path in (
                                item.get("filesystem_effect", {}).get(key, [])
                                if isinstance(item.get("filesystem_effect"), dict)
                                else []
                            )
                        }
                    ),
                }
                for item in (*context.successful_executions, *context.failed_executions)
            ],
            "facts": list(context.verified_facts),
            "changed": list(context.changed_paths),
            "criteria": list(context.acceptance_criteria),
            "evidence": dict(context.completion_evidence),
        }
    )
    manifest_id = _manifest_hash({"digest": evidence_digest, "text": context.final_text[:4000]})
    return CompletionManifest(
        manifest_id=manifest_id,
        objective=context.objective,
        final_text=context.final_text,
        claims=tuple(claims),
        resolutions=tuple(resolutions),
        evidence_digest=evidence_digest,
        supported_claims=supported,
        unsupported_claims=unsupported,
        stale_rejected=stale_rejected,
        has_pending_tool_calls=bool(context.pending_tool_call_ids),
        has_tool_calls_in_draft=context.has_tool_calls_in_draft,
        active_failures=len(context.active_failures),
        review_status=context.review_status,
        truncated=context.truncated,
    )


def decide_output(manifest: CompletionManifest, context: OutputGateContext) -> OutputGateResult:
    """Run the bounded deterministic output decision.

    Order matters: structural blockers first, then evidence resolution, then
    semantic rewrite detection. Laya never runs here; see
    :func:`observe_output_shadow`.
    """
    if manifest.has_pending_tool_calls or manifest.has_tool_calls_in_draft:
        return OutputGateResult(
            "REEXECUTE",
            "draft still proposes tool calls; completion requires observed results",
            manifest,
        )
    if manifest.truncated:
        return OutputGateResult(
            "REEXECUTE", "response was truncated before completion evidence closed", manifest
        )
    if manifest.active_failures:
        return OutputGateResult(
            "REEXECUTE",
            f"{manifest.active_failures} active failure(s) require correction, not completion",
            manifest,
        )
    if context.unresolved_discovery:
        undiscovered = ", ".join(context.unresolved_discovery[:3])
        return OutputGateResult(
            "RESOLVE_RESOURCE",
            f"undiscovered resources block completion: {undiscovered}",
            manifest,
        )
    if manifest.unsupported_claims:
        first = next(item for item in manifest.resolutions if not item.supported)
        return OutputGateResult(
            "FAIL_CLOSED",
            f"unsupported material claim: {str(first.claim.get('text', ''))[:160]} ({first.basis})",
            manifest,
        )
    if context.acceptance_criteria and any(
        criterion not in context.completion_evidence for criterion in context.acceptance_criteria
    ):
        missing_criteria = [
            criterion
            for criterion in context.acceptance_criteria
            if criterion not in context.completion_evidence
        ]
        return OutputGateResult(
            "REEXECUTE",
            f"acceptance criteria lack completion evidence: {', '.join(missing_criteria[:3])}",
            manifest,
        )
    if context.review_required and context.review_status != "approved":
        return OutputGateResult(
            "ESCALATE_REVIEW",
            f"required review is {context.review_status}, not approved",
            manifest,
        )
    if not manifest.claims:
        return OutputGateResult(
            "REWRITE_ONLY",
            "no material completion claims; concise user-facing rewrite only",
            manifest,
        )
    return OutputGateResult("PASS", "all material claims resolve to runtime evidence", manifest)


def observe_output_shadow(
    manifest: CompletionManifest,
    candidates: tuple[str, ...] = OUTPUT_DECISIONS,
    *,
    choose: Any | None = None,
    record: Any | None = None,
) -> tuple[str | None, bool | None]:
    """Let Laya assist semantic output validation without establishing facts.

    ``choose`` receives the bounded candidate set plus the manifest digest and
    returns one candidate string. Anything else (including exceptions) falls
    back to no shadow opinion. ``record`` optionally receives the agreement
    boolean for metrics. The deterministic decision is never overridden here.
    """
    if choose is None:
        return None, None
    try:
        choice = choose(tuple(candidates), manifest.to_dict())
    except Exception:
        return None, None
    if not isinstance(choice, str) or choice not in candidates:
        return None, None
    return choice, None


def shadow_agreement(deterministic: OutputDecisionCode, laya_choice: str | None) -> bool | None:
    if laya_choice is None:
        return None
    return bool(laya_choice == deterministic)
