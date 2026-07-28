#!/usr/bin/env python3
"""Run one real client through the sustained-Goal context-retention protocol."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dgx_moa import isolated_sglang_validation as RUNTIME
from dgx_moa import quality_matrix as QUALITY

PROJECT = Path(__file__).resolve().parents[3]

PROTOCOL = "frontier-long-goal-v47"
PHASES = (
    "intake_and_plan",
    "core_implementation",
    "integration_and_tests",
    "independent_review_and_repair",
    "full_validation_and_final",
)
CHECKPOINTS = len(PHASES)
INTERVAL_SECONDS = 0
SAFE_HOSTS = {"127.0.0.1", "::1", "localhost"}
FORBIDDEN_KEYS = {
    "api_key",
    "authorization",
    "cookie",
    "hidden_reasoning",
    "prompt",
    "raw_output",
    "raw_prompt",
    "repository_name",
    "request_id",
    "session_id",
}
TERMINAL_TYPES = {
    "codex": "turn.completed",
    "opencode": "stop",
}
FIXED_PLAN_PROVIDERS = {
    "codex",
    "default",
    "frontier",
    "local",
    "opencode_go",
    "primary",
    "remote",
    "secondary",
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode())


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def provider_manifest_hash(path: Path) -> str:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("provider manifest must be a JSON object")
    reject_private_fields(value)
    return sha256_file(path)


def local_gateway(value: str) -> str:
    endpoint = value.rstrip("/")
    parsed = urlparse(endpoint)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in SAFE_HOSTS
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise argparse.ArgumentTypeError("gateway must be loopback-only")
    return endpoint


def reject_private_fields(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                raise ValueError(f"private evidence field forbidden: {key}")
            reject_private_fields(item)
    elif isinstance(value, list):
        for item in value:
            reject_private_fields(item)


def append_event(path: Path, event: dict[str, Any], *, create: bool = False) -> None:
    reject_private_fields(event)
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | (os.O_EXCL if create else os.O_APPEND)
    descriptor = os.open(path, flags, 0o600)
    try:
        os.write(descriptor, (json.dumps(event, sort_keys=True) + "\n").encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.chmod(path, 0o600)


def load_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_private(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(descriptor, (json.dumps(value, sort_keys=True) + "\n").encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    os.chmod(path, 0o600)


def git(workspace: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(workspace), *arguments],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("git_command_failed")
    return result.stdout.strip()


def git_snapshot(workspace: Path) -> dict[str, str]:
    return {
        "commit": git(workspace, "rev-parse", "HEAD"),
        "branch": git(workspace, "branch", "--show-current"),
        "dirty_state": "clean" if not git(workspace, "status", "--porcelain") else "dirty",
    }


def ensure_local_git_identity(workspace: Path) -> None:
    for key, value in (
        ("user.name", "DGX MoA Evaluation"),
        ("user.email", "evaluation@localhost"),
    ):
        result = subprocess.run(
            ["git", "-C", str(workspace), "config", "--local", "--get", key],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode == 1:
            git(workspace, "config", "--local", key, value)
        elif result.returncode:
            raise RuntimeError("git_command_failed")


def stable_hashes(
    args: argparse.Namespace,
    session: str,
    baseline: dict[str, str],
) -> dict[str, str]:
    return {
        "session_sha256": sha256_text(session),
        "objective_sha256": sha256_file(args.objective),
        "acceptance_sha256": sha256_file(args.acceptance),
        "plan_sha256": sha256_file(args.plan),
        "repository_sha256": sha256_text(git(args.workspace, "rev-parse", "--show-toplevel")),
        "branch_sha256": sha256_text(baseline["branch"]),
        "provider_config_sha256": args.provider_manifest_sha256,
    }


def client_prompt(
    index: int,
    workspace: Path,
    validation_command: str,
    input_paths: tuple[Path, Path, Path],
) -> str:
    phase = PHASES[index]
    final = index == CHECKPOINTS - 1
    phase_rule = (
        (
            "운영 문서와 입력 문서를 서로 독립적인 묶음으로 한 번만 읽고, 저장소 상태를 "
            "확인해 의존 순서가 있는 계획을 확정하라. 코드는 건드리지 말고 이후 단계가 "
            "남아 있다고 명시하라. "
        ),
        (
            "확정된 계획의 핵심 기능만 구현하고 관련 단위 검증과 preliminary Reviewer "
            "승인을 받은 뒤 변경을 작은 논리 단위로 commit하라. 통합 검증과 최종 독립 "
            "검토는 이후 단계에 남겨라. "
        ),
        (
            "결과물을 통합해 자동 테스트를 실제로 실행하라. 실패가 있으면 원인을 고치고 "
            "재실행하며, 변경이 생긴 경우에만 commit하라. 독립 검토는 다음 단계에 남겨라. "
        ),
        (
            "결과물·보안·동시성·누락 테스트를 독립적으로 검토하고 실제 검증 명령을 실행하라. "
            "중요한 지적이 있으면 고치고 재검증하며, 변경이 생긴 경우에만 commit하라. "
            "전체 완료 선언은 다음 단계에 남겨라. "
        ),
        (
            "전체 검증과 독립 Reviewer 검토를 완료하고 /state/long-review.json에 "
            "최종 검토 근거를 남긴 뒤에만 완료를 선언하라. "
        ),
    )
    return (
        f"장기 작업 단계 {index}/{CHECKPOINTS - 1}({phase})를 수행하라. "
        f"현재 저장소 루트는 {workspace}이고 모든 도구의 현재 작업 디렉터리도 이 경로다. "
        "추측한 경로로 cd하지 말고 입력 문서가 지정한 source/test 경로를 정확히 사용하며 "
        "별도 대체 src 또는 tests 루트는 허용되지 않는다. "
        f"검증 명령은 정확히 `{validation_command}`이다. "
        f"첫 단계에서만 {input_paths[0]}, {input_paths[1]}, {input_paths[2]}와 "
        "저장소 운영 문서를 읽고 이후에는 같은 세션 맥락을 사용하라. 이 세 경로만 "
        "host/client 공통 입력 경로다. /inputs 별칭이나 입력 문서 안에 적힌 다른 "
        "source 환경 절대경로를 도구로 열지 마라. "
        f"{phase_rule[index]}"
        "각 단계는 최소 한 번의 실제 호스트 도구를 사용하고 단계 종료 시 worktree를 "
        "clean으로 유지해야 한다. 계획·검토 전용 단계는 새 커밋을 강제하지 않는다. "
        "같은 파일을 근거 없이 반복해서 읽지 마라. "
        + (
            "최종 검토 파일은 "
            '{"status":"approved|changes_requested","unresolved_critical_findings":0,'
            '"evidence":"..."} 형식이어야 한다. '
            if final
            else ""
        )
        + "최종 응답 직전 반드시 실제 도구로 "
        "해당 단계의 증거와 clean worktree를 확인하라. 하나라도 미완료면 응답을 "
        "끝내지 마라. "
        "사용자에게 보이는 설명은 한국어로 간결하게 하라."
    )


def opencode_config(args: argparse.Namespace, gateway_session: str) -> str:
    value = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            "dgx-moa": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "DGX MoA long horizon",
                "options": {
                    "baseURL": args.gateway + "/v1",
                    "apiKey": "{env:DGX_MOA_API_KEY}",
                    "headers": {
                        "X-Session-ID": gateway_session,
                        "X-Runtime-Channel": "dev",
                        "X-Trace-Origin": "validation",
                        "X-Workspace-ID": "long-horizon",
                    },
                },
                "models": {
                    "dgx-moa-orchestrated": {
                        "name": "DGX MoA orchestrated",
                        "limit": {"context": 65_536, "output": 4_096},
                    }
                },
            }
        },
        "model": "dgx-moa/dgx-moa-orchestrated",
        "permission": {
            "*": "deny",
            "bash": "allow",
            "edit": "allow",
            "glob": "allow",
            "grep": "allow",
            "read": "allow",
            "write": "allow",
        },
    }
    return json.dumps(value, separators=(",", ":"))


codex_model_catalog = QUALITY.codex_model_catalog


def prepare_hermes(state: Path, args: argparse.Namespace) -> None:
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    config = state / "config.yaml"
    if config.exists():
        return
    config.write_text(
        "model:\n"
        "  default: dgx-moa-orchestrated\n"
        "  provider: custom\n"
        f"  base_url: {args.gateway}/v1\n"
        f"  api_key: ${{{args.api_key_env}}}\n"
        "  context_length: 65536\n"
        "  max_tokens: 16384\n"
    )
    config.chmod(0o600)


def client_command(
    args: argparse.Namespace,
    state: Path,
    session: str | None,
    index: int,
    gateway_session: str,
) -> tuple[list[str], dict[str, str], Path | None]:
    input_paths = (args.objective, args.acceptance, args.plan)
    prompt = client_prompt(
        index,
        args.workspace,
        args.validation_command,
        input_paths,
    )
    environment = QUALITY.filtered_env({args.api_key_env: os.environ[args.api_key_env]})
    inputs = tuple((path, str(path)) for path in input_paths)
    usage_file: Path | None = None
    if args.harness == "codex":
        write_private(state / "model-catalog.json", codex_model_catalog())
        provider = "dgx_moa_long"
        headers = (
            "{ "
            f'"X-Session-ID" = {json.dumps(gateway_session)}, '
            f'"X-Runtime-Channel" = "candidate", '
            f'"X-Trace-Origin" = "candidate_evaluation", '
            f'"X-Workspace-ID" = "long-horizon"'
            " }"
        )
        common = [
            "--json",
            "--dangerously-bypass-approvals-and-sandbox",
            "--strict-config",
            "--ignore-user-config",
            "-c",
            'model="dgx-moa-orchestrated"',
            "-c",
            "model_context_window=65536",
            "-c",
            'model_catalog_json="/state/model-catalog.json"',
            "-c",
            'model_reasoning_effort="high"',
            "-c",
            'model_verbosity="low"',
            "-c",
            f"model_provider={json.dumps(provider)}",
            "-c",
            f"model_providers.{provider}.name={json.dumps('DGX MoA long horizon')}",
            "-c",
            f"model_providers.{provider}.base_url={json.dumps(args.gateway + '/v1')}",
            "-c",
            f"model_providers.{provider}.env_key={json.dumps(args.api_key_env)}",
            "-c",
            f"model_providers.{provider}.wire_api={json.dumps('responses')}",
            "-c",
            f"model_providers.{provider}.http_headers={headers}",
        ]
        inner = (
            ["/tools/codex", "exec", *common, prompt]
            if session is None
            else ["/tools/codex", "exec", "resume", *common, session, prompt]
        )
        command = QUALITY.docker_command(
            args.workspace,
            state,
            inner,
            environment_names=(args.api_key_env,),
            extra_environment=("CODEX_HOME=/state",),
            read_only_mounts=(
                (QUALITY.CODEX_BINARY, "/tools/codex"),
                *inputs,
            ),
        )
    elif args.harness == "opencode":
        inner = [
            "/tools/opencode",
            "run",
            "--format",
            "json",
            "--pure",
            "--auto",
            "--dir",
            str(args.workspace),
            "--model",
            "dgx-moa/dgx-moa-orchestrated",
        ]
        if session is not None:
            inner.extend(("--session", session))
        inner.append(prompt)
        isolation = {
            **QUALITY.OPENCODE_ISOLATION_ENV,
            "OPENCODE_CONFIG_CONTENT": opencode_config(args, gateway_session),
        }
        command = QUALITY.docker_command(
            args.workspace,
            state,
            inner,
            environment_names=(args.api_key_env,),
            extra_environment=tuple(f"{key}={value}" for key, value in isolation.items()),
            read_only_mounts=(
                (QUALITY.OPENCODE_BINARY, "/tools/opencode"),
                *QUALITY.opencode_runtime_mounts(state),
                *inputs,
            ),
        )
    else:
        prepare_hermes(state, args)
        usage_file = state / f"usage-{index}.json"
        inner = [
            str(QUALITY.HERMES_ROOT / "venv/bin/python"),
            "-m",
            "hermes_cli.main",
            "-z",
            prompt,
            "--usage-file",
            f"/state/{usage_file.name}",
            "--provider",
            "custom:dgx-moa-agent",
            "--model",
            "dgx-moa-orchestrated",
        ]
        if session is not None:
            inner.extend(("--resume", session))
        command = QUALITY.docker_command(
            args.workspace,
            state,
            inner,
            environment_names=(args.api_key_env,),
            extra_environment=("HERMES_HOME=/state",),
            read_only_mounts=(
                (QUALITY.HERMES_ROOT, str(QUALITY.HERMES_ROOT)),
                (QUALITY.HERMES_PYTHON_ROOT, str(QUALITY.HERMES_PYTHON_ROOT)),
                *inputs,
            ),
        )
    return command, environment, usage_file


def json_lines(value: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in value.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def client_metrics(
    harness: str,
    stdout: str,
    stderr: str,
    usage_file: Path | None,
    state: Path | None = None,
) -> dict[str, Any]:
    rows = json_lines(stdout)
    session: str | None = None
    context_tokens = 0
    cached_tokens = 0
    tool_calls = 0
    terminal = False
    read_fingerprints: list[str] = []
    if harness == "codex":
        for row in rows:
            if row.get("type") == "thread.started":
                session = str(row.get("thread_id") or "") or session
            if row.get("type") == "turn.completed":
                terminal = True
                usage = row.get("usage") or {}
                context_tokens = max(context_tokens, int(usage.get("input_tokens") or 0))
                cached_tokens = max(cached_tokens, int(usage.get("cached_input_tokens") or 0))
            item = row.get("item") or {}
            if row.get("type") == "item.completed" and item.get("type") in {
                "command_execution",
                "mcp_tool_call",
                "file_change",
            }:
                tool_calls += 1
                if (
                    item.get("type") == "mcp_tool_call"
                    and "read" in str(item.get("tool") or "").lower()
                ):
                    read_fingerprints.append(sha256_text(json.dumps(item, sort_keys=True)))
    elif harness == "opencode":
        for row in rows:
            session = str(row.get("sessionID") or "") or session
            if row.get("type") == "tool_use":
                tool_calls += 1
                part = row.get("part") or {}
                if part.get("tool") == "read":
                    tool_state = part.get("state") or {}
                    read_fingerprints.append(
                        sha256_text(json.dumps(tool_state.get("input") or {}, sort_keys=True))
                    )
            if row.get("type") == "step_finish":
                part = row.get("part") or {}
                terminal = terminal or part.get("reason") == TERMINAL_TYPES["opencode"]
                tokens = part.get("tokens") or {}
                context_tokens = max(context_tokens, int(tokens.get("input") or 0))
                cached_tokens = max(
                    cached_tokens, int((tokens.get("cache") or {}).get("read") or 0)
                )
    else:
        if usage_file is None or not usage_file.is_file():
            raise RuntimeError("hermes_usage_missing")
        usage = json.loads(usage_file.read_text())
        session = str(usage.get("session_id") or "") or None
        context_tokens = int(usage.get("input_tokens") or usage.get("total_tokens") or 0)
        cached_tokens = int(usage.get("cache_read_tokens") or 0)
        terminal = bool(usage.get("completed")) and not bool(usage.get("failed"))
        if state is not None and session is not None:
            tool_calls, read_fingerprints = hermes_tool_metrics(state, session)
    repeated_reads = len(read_fingerprints) - len(set(read_fingerprints))
    lowered = (stdout + "\n" + stderr).lower()
    return {
        "session": session,
        "context_tokens": context_tokens,
        "cached_tokens": cached_tokens,
        "tool_calls": tool_calls,
        "retries": lowered.count("retry") + lowered.count("reconnecting"),
        "unjustified_repeated_reads": repeated_reads,
        "terminal": terminal,
        "output_sha256": sha256_text(stdout + "\n" + stderr),
    }


def hermes_tool_metrics(state: Path, session: str) -> tuple[int, list[str]]:
    database = state / "state.db"
    if not database.is_file():
        return 0, []
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT tool_name, tool_calls FROM messages WHERE session_id = ? ORDER BY id",
            (session,),
        ).fetchall()
    calls = 0
    reads: list[str] = []
    for tool_name, raw_calls in rows:
        if tool_name:
            calls += 1
            if "read" in str(tool_name).lower():
                reads.append(sha256_text(str(tool_name)))
        if not raw_calls:
            continue
        try:
            parsed = json.loads(raw_calls)
        except (TypeError, json.JSONDecodeError):
            continue
        for item in parsed if isinstance(parsed, list) else []:
            calls += 1
            function = item.get("function") or {} if isinstance(item, dict) else {}
            name = str(function.get("name") or item.get("name") or "")
            if "read" in name.lower():
                reads.append(
                    sha256_text(
                        name
                        + json.dumps(
                            function.get("arguments") or item.get("arguments") or {},
                            sort_keys=True,
                        )
                    )
                )
    return calls, reads


def provider_metrics(
    database: Path,
    started: float,
    completed: float,
    session_id: str | None = None,
) -> dict[str, Any]:
    with sqlite3.connect(database) as connection:
        columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(model_invocation_usage)")
        }
        cost_column = "invocation.cost_usd" if "cost_usd" in columns else "NULL"
        session_filter = (
            " AND EXISTS (SELECT 1 FROM role_request_usage AS role_request "
            "WHERE role_request.request_id = invocation.request_id "
            "AND role_request.session_id_hash = ?)"
            if session_id
            else ""
        )
        parameters: tuple[object, ...] = (
            (started, completed, sha256_text(session_id)) if session_id else (started, completed)
        )
        rows = connection.execute(
            "SELECT invocation.request_id, invocation.role, invocation.provider, "
            "invocation.model, invocation.status, invocation.latency_ms, "
            "invocation.prompt_tokens, invocation.total_tokens, "
            f"{cost_column} "
            "FROM model_invocation_usage AS invocation "
            "WHERE invocation.invoked_at >= ? AND invocation.invoked_at <= ?"
            f"{session_filter} ORDER BY invocation.invoked_at",
            parameters,
        ).fetchall()
    provenance = sorted(
        {(str(role), str(provider), str(model)) for _, role, provider, model, *_ in rows}
    )
    providers_by_call: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for request_id, role, provider, model, *_ in rows:
        providers_by_call.setdefault((str(request_id), str(role)), set()).add(
            (str(provider), str(model))
        )
    pinned = bool(providers_by_call) and all(
        len(providers) == 1 for providers in providers_by_call.values()
    )
    variable_cost_total = 0.0
    variable_cost_complete = True
    for row in rows:
        provider, cost = str(row[2]), row[8]
        if provider in FIXED_PLAN_PROVIDERS:
            continue
        if not provider.startswith("openrouter:") or cost is None:
            variable_cost_complete = False
            break
        variable_cost_total += float(cost)
    return {
        "provider_provenance": [
            {"role": role, "provider": provider, "model": model}
            for role, provider, model in provenance
        ],
        "provider_pinned": pinned,
        "provider_errors": sum(str(row[4]) not in {"completed", "success"} for row in rows),
        "context_tokens": max((int(row[6] or 0) for row in rows), default=0),
        "variable_cost_usd": variable_cost_total if variable_cost_complete else None,
    }


def runtime_metrics(snapshot: dict[str, Any]) -> tuple[int, int]:
    memories = [
        container.get("memory") or {}
        for container in (snapshot.get("containers") or {}).values()
        if isinstance(container, dict)
    ]
    peak = max(
        (
            int(memory.get("memory_peak_bytes") or memory.get("memory_current_bytes") or 0)
            for memory in memories
        ),
        default=0,
    )
    swap = sum(int(memory.get("memory_swap_current_bytes") or 0) for memory in memories)
    return peak, swap


def gateway_progress_state(database: Path, session: str, index: int) -> dict[str, Any]:
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT payload FROM sessions WHERE session_id = ? ORDER BY updated_at DESC LIMIT 1",
            (session,),
        ).fetchone()
    if row is None:
        raise RuntimeError("gateway_state_missing")
    try:
        value = json.loads(row[0])
    except (TypeError, json.JSONDecodeError):
        raise RuntimeError("invalid_gateway_state") from None
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("objective"), str)
        or not value["objective"]
        or not isinstance(value.get("plan"), list)
        or not value["plan"]
    ):
        raise RuntimeError("invalid_gateway_state")

    def fingerprint(fields: tuple[str, ...]) -> str:
        selected = {field: value.get(field) for field in fields}
        return sha256_text(json.dumps(selected, sort_keys=True, separators=(",", ":")))

    return {
        "phase_index": index,
        "phase": PHASES[index],
        "next_action_sha256": fingerprint(
            (
                "phase",
                "step_count",
                "completed_steps",
                "pending_tool_call_ids",
                "review_status",
                "frontier_correction_pending_verification",
            )
        ),
        "context_summary_sha256": fingerprint(
            (
                "objective",
                "acceptance_criteria",
                "plan",
                "phase",
                "completed_steps",
                "resolved_objective",
                "active_user_turn_sha256",
            )
        ),
        "evidence_sha256": fingerprint(
            (
                "implementation_evidence",
                "completion_evidence",
                "review_status",
                "tool_executions",
                "failures",
            )
        ),
        "premature_completion": index < CHECKPOINTS - 1
        and value.get("final_status") in {"achieved", "completed", "success"},
    }


def wait_until(target: float) -> None:
    while True:
        remaining = target - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 30))


def client_container_name(args: argparse.Namespace, state: Path, index: int) -> str:
    identity = sha256_text(str(state))[:12]
    return f"moa-long-{args.harness}-{identity}-{index}"


def with_container_name(command: list[str], name: str) -> list[str]:
    if command[:2] != ["docker", "run"]:
        raise ValueError("docker run command required")
    return [*command[:2], "--name", name, *command[2:]]


def container_exists(name: str) -> bool:
    return (
        subprocess.run(
            ["docker", "container", "inspect", name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )


def remove_client_container(name: str) -> None:
    subprocess.run(
        ["docker", "container", "rm", "--force", name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def secure_client_state(state: Path) -> None:
    snapshots = state / "shell_snapshots"
    if snapshots.is_dir():
        snapshots.chmod(0o700)
        for path in snapshots.glob("*.sh"):
            path.chmod(0o600)


def run_validation(args: argparse.Namespace, state: Path) -> tuple[int, str]:
    command = shlex.split(args.validation_command)
    name = f"moa-long-validation-{sha256_text(str(state))[:12]}"
    if container_exists(name):
        raise RuntimeError("validation_container_already_exists")
    try:
        run = QUALITY.run_process(
            with_container_name(
                QUALITY.docker_command(
                    args.workspace,
                    state / "validator",
                    command,
                    network="none",
                    workspace_mode="ro",
                ),
                name,
            ),
            cwd=args.workspace,
            environment=QUALITY.filtered_env(),
            timeout=args.timeout,
        )
    finally:
        if container_exists(name):
            remove_client_container(name)
    return run.returncode, sha256_text(run.stdout + "\n" + run.stderr)


def final_event(
    args: argparse.Namespace,
    state: Path,
    header: dict[str, Any],
    checkpoint: dict[str, Any],
) -> dict[str, Any]:
    review_path = state / "long-review.json"
    if not review_path.is_file():
        raise RuntimeError("review_evidence_missing")
    review = json.loads(review_path.read_text())
    validation_exit, validation_hash = run_validation(args, state)
    snapshot = git_snapshot(args.workspace)
    implementation = git(
        args.workspace, "diff", "--binary", header["baseline_commit"], snapshot["commit"]
    )
    reviewer_seen = any(row.get("role") == "reviewer" for row in checkpoint["provider_provenance"])
    return {
        "type": "final",
        "completed_at_epoch": time.time(),
        "implementation_evidence": bool(implementation) and snapshot["dirty_state"] == "clean",
        "implementation_commit": snapshot["commit"],
        "implementation_sha256": sha256_text(implementation),
        "review_sha256": sha256_file(review_path),
        "validation_sha256": validation_hash,
        "review_status": review.get("status") if reviewer_seen else "reviewer_not_observed",
        "validation_exit": validation_exit,
        "terminal": checkpoint["terminal"],
        "unresolved_critical_findings": int(review.get("unresolved_critical_findings", -1)),
        "task_outcome": (
            "completed"
            if review.get("status") == "approved"
            and reviewer_seen
            and validation_exit == 0
            and bool(implementation)
            and snapshot["dirty_state"] == "clean"
            else "failed"
        ),
        **{field: header[field] for field in stable_hashes_fields()},
    }


def stable_hashes_fields() -> tuple[str, ...]:
    return (
        "session_sha256",
        "objective_sha256",
        "acceptance_sha256",
        "plan_sha256",
        "repository_sha256",
        "branch_sha256",
        "provider_config_sha256",
    )


def run_checkpoint(
    args: argparse.Namespace,
    state: Path,
    control: dict[str, Any],
    index: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    scheduled = float(control["started_at_epoch"]) + index * INTERVAL_SECONDS
    wait_until(scheduled)
    before = RUNTIME.runtime_snapshot()
    started = time.time()
    command, environment, usage_file = client_command(
        args,
        state,
        control.get("client_session"),
        index,
        control["gateway_session"],
    )
    container_name = client_container_name(args, state, index)
    if container_exists(container_name):
        raise RuntimeError("client_container_already_exists")
    try:
        run = QUALITY.run_process(
            with_container_name(command, container_name),
            cwd=args.workspace,
            environment=environment,
            timeout=args.timeout,
        )
    finally:
        if container_exists(container_name):
            remove_client_container(container_name)
        secure_client_state(state)
    completed = time.time()
    after = RUNTIME.runtime_snapshot()
    metrics = client_metrics(args.harness, run.stdout, run.stderr, usage_file, state)
    session = metrics.pop("session")
    if run.returncode == 124:
        raise RuntimeError("client_checkpoint_timeout")
    if run.returncode:
        raise RuntimeError("client_nonzero_exit")
    if not metrics["terminal"]:
        raise RuntimeError("client_terminal_missing")
    if not session:
        raise RuntimeError("client_session_missing")
    if control.get("client_session") not in {None, session}:
        raise RuntimeError("client_session_changed")
    control["client_session"] = session
    progress = gateway_progress_state(args.state_db, control["gateway_session"], index)
    git_state = git_snapshot(args.workspace)
    if git_state["dirty_state"] != "clean":
        raise RuntimeError("dirty_checkpoint")
    if index == 1 and not git(
        args.workspace,
        "diff",
        "--binary",
        control["baseline"]["commit"],
        git_state["commit"],
    ).strip():
        raise RuntimeError("implementation_checkpoint_unchanged")
    control["last_commit"] = git_state["commit"]
    provider = provider_metrics(
        args.state_db,
        started,
        completed,
        control["gateway_session"],
    )
    peak_before, swap_before = runtime_metrics(before)
    peak_after, swap_after = runtime_metrics(after)
    checkpoint = {
        "type": "checkpoint",
        "index": index,
        "phase_index": progress["phase_index"],
        "phase": progress["phase"],
        "scheduled_at_epoch": scheduled,
        "completed_at_epoch": completed,
        "latency_seconds": round(completed - started, 3),
        "next_action_sha256": progress["next_action_sha256"],
        "context_summary_sha256": progress["context_summary_sha256"],
        "evidence_sha256": sha256_text(
            progress["evidence_sha256"] + metrics.pop("output_sha256")
        ),
        "commit": git_state["commit"],
        "dirty_state": git_state["dirty_state"],
        "provider_pinned": provider["provider_pinned"],
        "provider_provenance": provider["provider_provenance"],
        "context_tokens": max(metrics["context_tokens"], provider["context_tokens"]),
        "cached_tokens": metrics["cached_tokens"],
        "tool_calls": metrics["tool_calls"],
        "retries": metrics["retries"],
        "provider_errors": provider["provider_errors"],
        "unjustified_repeated_reads": max(
            metrics["unjustified_repeated_reads"],
            0,
        ),
        "peak_memory_bytes": max(peak_before, peak_after),
        "swap_delta_bytes": max(0, swap_after - swap_before),
        "variable_cost_usd": provider["variable_cost_usd"],
        "intentional_reconnect": index == CHECKPOINTS // 2,
        "premature_completion": progress["premature_completion"],
        "terminal": metrics["terminal"],
        **control.get("stable_hashes", {}),
    }
    return checkpoint, control


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--harness", choices=("codex", "opencode", "hermes"), required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--objective", type=Path, required=True)
    parser.add_argument("--acceptance", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--provider-manifest", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--state-db", type=Path, required=True)
    parser.add_argument("--gateway", type=local_gateway, required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--api-key-env", default="DGX_MOA_API_KEY")
    parser.add_argument("--timeout", type=int, default=1_800)
    parser.add_argument(
        "--validation-command",
        default="python -m unittest discover -s tests -v",
    )
    args = parser.parse_args()
    if not args.variant.startswith("V") or not args.variant[1:].isdigit():
        parser.error("variant must be opaque V<number>")
    for field in (
        "workspace",
        "objective",
        "acceptance",
        "plan",
        "provider_manifest",
        "state_db",
    ):
        value = getattr(args, field).resolve()
        if not value.exists():
            parser.error(f"{field} does not exist")
        setattr(args, field, value)
    try:
        args.provider_manifest_sha256 = provider_manifest_hash(args.provider_manifest)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(f"invalid provider manifest: {type(error).__name__}")
    args.evidence = args.evidence.resolve()
    args.state_dir = args.state_dir.resolve()
    if args.evidence == args.state_dir or args.state_dir in args.evidence.parents:
        parser.error("evidence must be outside the private state directory")
    if args.api_key_env not in os.environ:
        parser.error(f"{args.api_key_env} is unset")
    return args


def main() -> int:
    args = parse_args()
    ensure_local_git_identity(args.workspace)
    state = args.state_dir
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(state, 0o700)
    control_path = state / "long-control.json"
    events = load_events(args.evidence)
    if any(event.get("type") == "final" for event in events):
        raise SystemExit("evidence already finalized")
    if control_path.is_file():
        control = json.loads(control_path.read_text())
        header = events[0]
    else:
        baseline = git_snapshot(args.workspace)
        if baseline["dirty_state"] != "clean":
            raise SystemExit("workspace must start clean")
        control = {
            "started_at_epoch": time.time(),
            "baseline": baseline,
            "gateway_session": "long-" + os.urandom(16).hex(),
            "client_session": None,
            "last_commit": baseline["commit"],
        }
        header = {}
    start_index = sum(event.get("type") == "checkpoint" for event in events)
    active_index = start_index
    last_checkpoint: dict[str, Any] | None = None
    failure_path = args.evidence.with_suffix(args.evidence.suffix + ".failure.json")
    try:
        for index in range(start_index, CHECKPOINTS):
            active_index = index
            checkpoint, control = run_checkpoint(args, state, control, index)
            if not header:
                control["stable_hashes"] = stable_hashes(
                    args, control["client_session"], control["baseline"]
                )
                checkpoint.update(control["stable_hashes"])
                header = {
                    "type": "header",
                    "protocol": PROTOCOL,
                    "variant": args.variant,
                    "started_at_epoch": control["started_at_epoch"],
                    "expected_checkpoints": CHECKPOINTS,
                    "checkpoint_interval_seconds": INTERVAL_SECONDS,
                    "client_path": args.harness,
                    "gateway_path": "authenticated_loopback",
                    "baseline_commit": control["baseline"]["commit"],
                    **control["stable_hashes"],
                }
                append_event(args.evidence, header, create=True)
            write_private(control_path, control)
            append_event(args.evidence, checkpoint)
            last_checkpoint = checkpoint
        if last_checkpoint is None:
            last_checkpoint = next(
                event for event in reversed(events) if event.get("type") == "checkpoint"
            )
        final = final_event(args, state, header, last_checkpoint)
        append_event(args.evidence, final)
        failure_path.unlink(missing_ok=True)
    except Exception as error:
        write_private(
            failure_path,
            {
                "protocol": PROTOCOL,
                "harness": args.harness,
                "checkpoint": active_index,
                "failed_at_epoch": time.time(),
                "failure_type": type(error).__name__,
                "failure_class": str(error)
                if str(error)
                in {
                    "client_checkpoint_failed",
                    "client_checkpoint_timeout",
                    "client_nonzero_exit",
                    "client_session_missing",
                    "client_terminal_missing",
                    "dirty_checkpoint",
                    "implementation_checkpoint_unchanged",
                    "client_container_already_exists",
                    "client_session_changed",
                    "gateway_state_missing",
                    "invalid_gateway_state",
                    "premature_completion",
                }
                else "long_horizon_failure",
            },
        )
        raise
    summary = {
        "protocol": PROTOCOL,
        "harness": args.harness,
        "checkpoints": CHECKPOINTS,
        "task_outcome": final["task_outcome"],
        "evidence": str(args.evidence),
    }
    if final["task_outcome"] == "completed":
        shutil.rmtree(state)
    print(json.dumps(summary, sort_keys=True))
    return 0 if final["task_outcome"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
