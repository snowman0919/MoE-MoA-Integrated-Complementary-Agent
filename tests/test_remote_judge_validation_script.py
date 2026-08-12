from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts/validate-remote-judge.py"
spec = importlib.util.spec_from_file_location("validate_remote_judge", SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load script module from {SCRIPT}")
module = importlib.util.module_from_spec(spec)
sys.modules.setdefault("validate_remote_judge", module)
spec.loader.exec_module(module)


class FailingJudge:
    def __init__(self, **values: object) -> None:
        del values

    async def available(self) -> bool:
        return True

    async def judge(self, evidence: object) -> None:
        del evidence
        raise RuntimeError("raw judge detail must not be persisted")


@pytest.mark.asyncio
async def test_validator_records_failed_case_without_raw_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPENCODE_GO_API_KEY", "synthetic")
    monkeypatch.setattr(module, "OpenCodeGoJudgeProvider", FailingJudge)
    output = tmp_path / "judge.json"

    with pytest.raises(RuntimeError, match="raw judge detail"):
        await module.validate(output)

    rendered = output.read_text()
    payload = json.loads(rendered)
    assert payload["status"] == "failed"
    assert payload["cases"] == {
        "approve_valid_response": {
            "failure_class": "RuntimeError",
            "status": "failed",
        }
    }
    assert "raw judge detail" not in rendered
    assert not output.with_suffix(".json.tmp").exists()
