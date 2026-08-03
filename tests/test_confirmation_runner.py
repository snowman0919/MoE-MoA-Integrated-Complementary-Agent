import json
from argparse import Namespace
from types import SimpleNamespace

from dgx_moa import confirmation_runner


def test_runner_resumes_from_score_files(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    protocol = tmp_path / "sealed"
    protocol.mkdir()
    attempts = [
        {"attempt_id": "a1", "order": 1, "task": "task", "variant": "variant-a"},
        {"attempt_id": "a2", "order": 2, "task": "task", "variant": "variant-a"},
    ]
    (protocol / "confirmation-seal.json").write_text(json.dumps({"attempts": attempts}))
    (protocol / "confirmation-routing.json").write_text(
        json.dumps({"variant_routes": {"variant-a": {"harness": "codex"}}})
    )
    for attempt in attempts:
        evidence = tmp_path / attempt["attempt_id"] / "codex/task"
        evidence.mkdir(parents=True)
        (evidence / "manifest.json").write_text("{}")
    (tmp_path / "a1/codex/task/score.json").write_text('{"status":"passed"}')

    calls: list[str] = []
    monkeypatch.setattr(confirmation_runner.confirmation_seal, "verify_seal", lambda _args: {})
    monkeypatch.setattr(
        confirmation_runner.quality_matrix,
        "TASK_BY_SLUG",
        {"task": SimpleNamespace(slug="task")},
    )
    monkeypatch.setattr(confirmation_runner.quality_matrix, "HIDDEN_CHECKS", {})
    monkeypatch.setattr(
        confirmation_runner.quality_matrix,
        "run_one",
        lambda _args, _harness, _task: calls.append("run"),
    )
    monkeypatch.setattr(
        confirmation_runner.quality_matrix,
        "score_one",
        lambda _args, _harness, _task, _checks: calls.append("score")
        or {"status": "failed"},
    )

    result = confirmation_runner.run(
        Namespace(
            protocol_id="sealed",
            output_root=tmp_path,
            workspace_root=tmp_path,
            gateway="http://127.0.0.1:9000",
            state_db=tmp_path / "state.db",
            timeout=10,
            panel="coding",
        )
    )

    assert calls == ["run", "score"]
    assert result == {"completed": 2, "passed": 1, "failed": 1}
    assert len(capsys.readouterr().out.splitlines()) == 2
