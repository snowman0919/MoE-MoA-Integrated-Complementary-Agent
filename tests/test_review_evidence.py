from dgx_moa.review_evidence import (
    execution_succeeded,
    is_successful_validation_execution,
    review_tool_results,
    tool_execution_changes_files,
)
from dgx_moa.state import SessionState


def test_review_tool_results_drop_superseded_failures() -> None:
    state = SessionState(
        session_id="latest-review-evidence",
        tool_results=[
            {"stdout": "superseded failure"},
            {"stdout": "superseded stub"},
            *[{"stdout": f"latest pass {index}"} for index in range(4)],
        ],
    )

    results = review_tool_results(state)

    assert [result["stdout"] for result in results] == [
        f"latest pass {index}" for index in range(4)
    ]


def test_tempfile_validation_is_not_a_source_change() -> None:
    assert not tool_execution_changes_files(
        {
            "tool_name": "bash",
            "normalized_arguments": {
                "command": "from tempfile import TemporaryDirectory\n"
                "with TemporaryDirectory() as directory:\n"
                "    path.write_text('{}')"
            },
        }
    )


def test_failed_validation_wrapper_is_not_review_evidence() -> None:
    assert not is_successful_validation_execution(
        {
            "exit_code": 0,
            "failure_class": "NONEXISTENT_PATH",
            "normalized_arguments": {"cmd": "timeout 120s python -m unittest discover -s tests -v"},
        }
    )


def test_python3_validation_is_evidence_only_with_a_successful_real_exit() -> None:
    for interpreter in ("python", "python3", "python3.11"):
        execution = {
            "exit_code": 0,
            "normalized_arguments": {
                "command": f"timeout 120s {interpreter} -m unittest -q test_result"
            },
        }
        assert is_successful_validation_execution(execution)
        for change in ({"exit_code": 1}, {"exit_code": None}, {"failure_class": "TEST_FAILURE"}):
            assert not is_successful_validation_execution({**execution, **change})
    assert not is_successful_validation_execution(
        {
            "exit_code": 0,
            "normalized_arguments": {"command": "python3 -m unittest | cat"},
        }
    )


def test_verified_native_file_write_does_not_invent_a_process_exit() -> None:
    execution = {
        "tool_name": "write_file",
        "exit_code": None,
        "filesystem_effect": {"verified": True, "changed_paths": ["result.txt"]},
    }
    assert execution_succeeded(execution)
    assert execution["exit_code"] is None
    for change in (
        {"tool_name": "terminal"},
        {"exit_code": 1},
        {"failure_class": "WRITE_FAILURE"},
        {"filesystem_effect": {"verified": False, "changed_paths": ["result.txt"]}},
        {"filesystem_effect": {"verified": True}},
    ):
        assert not execution_succeeded({**execution, **change})
