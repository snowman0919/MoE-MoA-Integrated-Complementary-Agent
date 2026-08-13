from dgx_moa.review_evidence import review_tool_results, tool_execution_changes_files
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
