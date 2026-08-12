from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts/validate-specialist-routing.py"
spec = importlib.util.spec_from_file_location("validate_specialist_routing", SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load script module from {SCRIPT}")
module = importlib.util.module_from_spec(spec)
sys.modules.setdefault("validate_specialist_routing", module)
spec.loader.exec_module(module)


class Provider:
    fail_reviewer = False
    invalid_reviewer_once = False
    reviewer_calls = 0

    def __init__(self, **values: object) -> None:
        self.model = values["model"]

    async def complete(self, request: dict[str, object], *, timeout_seconds: float) -> dict:
        del timeout_seconds
        is_reviewer = "Review" in json.dumps(request)
        if is_reviewer:
            self.__class__.reviewer_calls += 1
        if self.fail_reviewer and is_reviewer:
            raise RuntimeError("raw provider detail must not be persisted")
        if self.invalid_reviewer_once and is_reviewer and self.reviewer_calls == 1:
            return {"choices": [{"message": {"content": ""}}], "usage": {"total_tokens": 1}}
        content = (
            {
                "scope": ["docs/a.md"],
                "assumptions": [],
                "ordered_steps": [
                    {
                        "step_id": "step-1",
                        "action": "correct typo",
                        "dependencies": [],
                        "expected_evidence": ["lint passes"],
                    }
                ],
                "dependencies": [],
                "risks": [],
                "validation_plan": ["run lint"],
                "rollback_plan": ["revert file"],
                "acceptance_criteria": ["lint passes"],
            }
            if not is_reviewer
            else {"status": "approved", "findings": []}
        )
        return {
            "choices": [{"message": {"content": json.dumps(content)}}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        }


@pytest.mark.asyncio
async def test_validator_atomically_preserves_sanitized_partial_progress(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPENCODE_GO_API_KEY", "synthetic")
    monkeypatch.setattr(module, "RemotePlannerProvider", Provider)
    monkeypatch.setattr(module, "RemoteReviewerProvider", Provider)
    output = tmp_path / "specialists.json"

    await module.validate(output)

    passed = json.loads(output.read_text())
    assert passed["status"] == "passed"
    assert passed["cases"]["planner"]["total_tokens"] == 5
    assert passed["cases"]["reviewer"]["structured_output"] == "valid"
    assert passed["cases"]["reviewer"]["attempts"] == 1

    Provider.reviewer_calls = 0
    Provider.invalid_reviewer_once = True
    await module.validate(output)
    retried = json.loads(output.read_text())
    assert retried["cases"]["reviewer"]["attempts"] == 2
    assert retried["cases"]["reviewer"]["total_tokens"] == 6
    Provider.invalid_reviewer_once = False

    Provider.fail_reviewer = True
    with pytest.raises(RuntimeError, match="raw provider detail"):
        await module.validate(output)
    failed_text = output.read_text()
    failed = json.loads(failed_text)
    assert failed["status"] == "failed"
    assert failed["cases"]["planner"]["status"] == "passed"
    assert failed["cases"]["reviewer"] == {
        "failure_class": "RuntimeError",
        "model": "deepseek-v4-pro",
        "status": "failed",
    }
    assert "raw provider detail" not in failed_text
    assert not output.with_suffix(".json.tmp").exists()
