from __future__ import annotations

import argparse
import json
import runpy
import sqlite3
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "run-long-horizon-client.py"
MODULE = runpy.run_path(str(SCRIPT))


def arguments(tmp_path: Path, harness: str) -> argparse.Namespace:
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    inputs = []
    for name in ("objective.md", "acceptance.md", "plan.md"):
        path = tmp_path / name
        path.write_text(name)
        inputs.append(path)
    provider_manifest = tmp_path / "provider.json"
    provider_manifest.write_text(
        json.dumps(
            {
                "executor": {"model": "executor-fixed", "revision": "a" * 40},
                "specialist": {"model": "specialist-fixed", "revision": "b" * 40},
            }
        )
    )
    return argparse.Namespace(
        harness=harness,
        workspace=workspace,
        objective=inputs[0],
        acceptance=inputs[1],
        plan=inputs[2],
        gateway="http://127.0.0.1:19300",
        api_key_env="TEST_LONG_API_KEY",
        provider_manifest=provider_manifest,
        provider_manifest_sha256=MODULE["sha256_file"](provider_manifest),
    )


def test_evidence_is_durable_and_rejects_private_fields(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.jsonl"
    MODULE["append_event"](evidence, {"type": "header", "value": 1}, create=True)
    MODULE["append_event"](evidence, {"type": "checkpoint", "value": 2})

    assert evidence.stat().st_mode & 0o777 == 0o600
    assert [row["type"] for row in MODULE["load_events"](evidence)] == [
        "header",
        "checkpoint",
    ]
    with pytest.raises(ValueError, match="private evidence"):
        MODULE["append_event"](evidence, {"type": "bad", "raw_prompt": "secret"})
    with pytest.raises(ValueError, match="private evidence"):
        MODULE["append_event"](evidence, {"type": "bad", "nested": {"session_id": "raw"}})


def test_provider_manifest_hash_rejects_private_fields(tmp_path: Path) -> None:
    manifest = tmp_path / "provider.json"
    manifest.write_text(json.dumps({"executor": {"model": "fixed", "revision": "abc"}}))

    assert MODULE["provider_manifest_hash"](manifest) == MODULE["sha256_file"](manifest)

    manifest.write_text(json.dumps({"executor": {"api_key": "private"}}))
    with pytest.raises(ValueError, match="private evidence"):
        MODULE["provider_manifest_hash"](manifest)


def test_codex_model_catalog_enables_native_patch_tool() -> None:
    model = MODULE["codex_model_catalog"]()["models"][0]

    assert model["slug"] == "dgx-moa-orchestrated"
    assert model["apply_patch_tool_type"] == "freeform"
    assert model["context_window"] == 65_536
    assert "apply_patch" in model["base_instructions"]


@pytest.mark.parametrize(
    ("harness", "binary", "resume_flag"),
    (
        ("codex", "/tools/codex", "resume"),
        ("opencode", "/tools/opencode", "--session"),
        ("hermes", "/home/kotori9/.hermes/hermes-agent/venv/bin/python", "--resume"),
    ),
)
def test_client_commands_resume_the_same_private_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    harness: str,
    binary: str,
    resume_flag: str,
) -> None:
    monkeypatch.setenv("TEST_LONG_API_KEY", "private-test-value")
    args = arguments(tmp_path, harness)
    state = tmp_path / f"state-{harness}"

    command, environment, _ = MODULE["client_command"](
        args, state, "private-session", 4, "private-gateway-session"
    )

    inner = command[command.index(binary) :]
    assert resume_flag in inner
    assert "private-session" in inner
    assert environment["TEST_LONG_API_KEY"] == "private-test-value"
    assert str(args.objective) in " ".join(command)
    assert "private-test-value" not in " ".join(command)
    if harness == "codex":
        catalog = json.loads((state / "model-catalog.json").read_text())
        assert catalog["models"][0]["apply_patch_tool_type"] == "freeform"
        assert 'model_catalog_json="/state/model-catalog.json"' in inner


def test_client_metrics_and_provider_pinning_are_aggregated_without_payloads(
    tmp_path: Path,
) -> None:
    repeated_read = {
        "type": "tool_use",
        "sessionID": "private-session",
        "part": {"tool": "read", "state": {"input": {"filePath": "/private/file"}}},
    }
    finish = {
        "type": "step_finish",
        "sessionID": "private-session",
        "part": {
            "reason": "stop",
            "tokens": {"input": 100, "cache": {"read": 75}},
        },
    }
    metrics = MODULE["client_metrics"](
        "opencode",
        "\n".join(json.dumps(row) for row in (repeated_read, repeated_read, finish)),
        "",
        None,
    )

    assert metrics["session"] == "private-session"
    assert metrics["terminal"] is True
    assert metrics["tool_calls"] == 2
    assert metrics["context_tokens"] == 100
    assert metrics["cached_tokens"] == 75
    assert metrics["unjustified_repeated_reads"] == 1
    assert "/private/file" not in json.dumps(metrics)

    database = tmp_path / "state.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE model_invocation_usage ("
            "role TEXT, provider TEXT, model TEXT, status TEXT, latency_ms REAL, "
            "prompt_tokens INTEGER, total_tokens INTEGER, invoked_at REAL)"
        )
        connection.executemany(
            "INSERT INTO model_invocation_usage VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ("executor", "local", "executor-fixed", "completed", 10, 120, 130, 2),
                ("reviewer", "local", "specialist-fixed", "success", 20, 80, 90, 3),
            ),
        )

    provider = MODULE["provider_metrics"](database, 1, 4)

    assert provider["provider_pinned"] is True
    assert provider["provider_errors"] == 0
    assert provider["context_tokens"] == 120
    assert provider["provider_provenance"] == [
        {"role": "executor", "provider": "local", "model": "executor-fixed"},
        {"role": "reviewer", "provider": "local", "model": "specialist-fixed"},
    ]


def test_hermes_metrics_use_tool_rows_not_model_api_count(tmp_path: Path) -> None:
    usage = tmp_path / "usage.json"
    usage.write_text(
        json.dumps(
            {
                "session_id": "private-hermes",
                "input_tokens": 90,
                "cache_read_tokens": 40,
                "api_calls": 99,
                "completed": True,
                "failed": False,
            }
        )
    )
    with sqlite3.connect(tmp_path / "state.db") as connection:
        connection.execute(
            "CREATE TABLE messages ("
            "id INTEGER, session_id TEXT, tool_name TEXT, tool_calls TEXT)"
        )
        connection.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?)",
            (
                1,
                "private-hermes",
                None,
                json.dumps(
                    [
                        {
                            "function": {
                                "name": "read_file",
                                "arguments": {"path": "/private/file"},
                            }
                        }
                    ]
                ),
            ),
        )

    metrics = MODULE["client_metrics"]("hermes", "done", "", usage, tmp_path)

    assert metrics["tool_calls"] == 1
    assert metrics["context_tokens"] == 90
    assert metrics["cached_tokens"] == 40
    assert "/private/file" not in json.dumps(metrics)


def test_checkpoint_interrupt_removes_only_its_named_container(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = arguments(tmp_path, "codex")
    args.state_db = tmp_path / "unused.db"
    args.timeout = 1
    state = tmp_path / "state"
    state.mkdir()
    control = {
        "started_at_epoch": 1,
        "baseline": {},
        "gateway_session": "private-gateway",
        "client_session": None,
    }
    existence = iter((False, True))
    removed: list[str] = []
    globals_ = MODULE["run_checkpoint"].__globals__
    monkeypatch.setenv("TEST_LONG_API_KEY", "private-test-value")
    monkeypatch.setitem(
        MODULE["QUALITY"],
        "run_process",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    monkeypatch.setitem(MODULE["RUNTIME"], "runtime_snapshot", lambda: {})
    monkeypatch.setitem(
        globals_,
        "client_command",
        lambda *_args: (["docker", "run", "--rm", "image", "command"], {}, None),
    )
    monkeypatch.setitem(globals_, "wait_until", lambda _target: None)
    monkeypatch.setitem(globals_, "container_exists", lambda _name: next(existence))
    monkeypatch.setitem(globals_, "remove_client_container", removed.append)

    with pytest.raises(KeyboardInterrupt):
        MODULE["run_checkpoint"](args, state, control, 0)

    assert removed == [MODULE["client_container_name"](args, state, 0)]
