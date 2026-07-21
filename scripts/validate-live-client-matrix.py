#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import secrets
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

import httpx
import uvicorn
from dgx_moa.api import create_app
from dgx_moa.config import load_settings

PROJECT = Path(__file__).resolve().parents[1]
PRODUCTION = Path("/home/kotori9/dgx-moa-agent")


def run(
    command: list[str], *, cwd: Path, env: dict[str, str], timeout: int = 600
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def git_fingerprint(path: Path) -> dict[str, str]:
    return {
        "commit": subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
        ).strip(),
        "branch": subprocess.check_output(
            ["git", "-C", str(path), "branch", "--show-current"], text=True
        ).strip(),
        "porcelain": subprocess.check_output(
            ["git", "-C", str(path), "status", "--porcelain"], text=True
        ).strip(),
    }


def port_available(port: int) -> bool:
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def client_env(root: Path, secret: str) -> dict[str, str]:
    locations = {
        "HOME": root / "home",
        "XDG_CACHE_HOME": root / "cache",
        "XDG_CONFIG_HOME": root / "config",
        "XDG_DATA_HOME": root / "data",
        "XDG_STATE_HOME": root / "state",
        "TMPDIR": root / "tmp",
    }
    for path in locations.values():
        path.mkdir(parents=True, exist_ok=True)
    return {
        "PATH": os.environ["PATH"],
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "NO_COLOR": "1",
        "DGX_MOA_API_KEY": secret,
        **{key: str(value) for key, value in locations.items()},
    }


def start_gateway(root: Path, port: int, secret: str) -> tuple[uvicorn.Server, threading.Thread]:
    original_auth = os.environ.get("DGX_MOA_AUTH_ENABLED")
    os.environ["DGX_MOA_AUTH_ENABLED"] = "false"
    try:
        base = load_settings(PROJECT / "config/models.yaml")
    finally:
        if original_auth is None:
            os.environ.pop("DGX_MOA_AUTH_ENABLED", None)
        else:
            os.environ["DGX_MOA_AUTH_ENABLED"] = original_auth
    settings = base.model_copy(
        update={
            "bind_host": "127.0.0.1",
            "bind_port": port,
            "auth_enabled": True,
            "api_key": None,
            "api_keys": {"physical": secret},
            "admin_api_enabled": False,
            "state_db": root / "runtime/state.db",
            "run_dir": root / "runtime",
            "runtime_channel": "dev",
            "trace_origin": "validation",
            "controller_commit": "dirty-predeployment-validation",
            "frontier_enabled": False,
            "lifecycle_mode": "disabled",
            "lifecycle_unit_map": {},
        }
    )
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings),
            host="127.0.0.1",
            port=port,
            log_level="warning",
            access_log=False,
        )
    )
    thread = threading.Thread(target=server.run, name="live-client-gateway", daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=1).status_code == 200:
                return server, thread
        except httpx.HTTPError:
            pass
        if not thread.is_alive():
            break
        time.sleep(0.1)
    raise RuntimeError("isolated gateway failed to start")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--port", type=int, default=19300)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    if not port_available(args.port):
        raise SystemExit(f"port {args.port} is already bound")
    before = git_fingerprint(PRODUCTION)
    secret = secrets.token_urlsafe(32)
    base_url = f"http://127.0.0.1:{args.port}"
    headers = {"Authorization": f"Bearer {secret}"}
    server, thread = start_gateway(root, args.port, secret)
    results: dict[str, object] = {}
    try:
        generic = httpx.post(
            f"{base_url}/v1/chat/completions",
            headers=headers,
            json={
                "model": "dgx-moa-fast",
                "messages": [{"role": "user", "content": "Reply exactly GENERIC_OK"}],
                "stream": False,
                "max_tokens": 32,
            },
            timeout=300,
        )
        results["generic"] = {"status_code": generic.status_code, "valid_json": False}
        if generic.status_code == 200:
            payload = generic.json()
            results["generic"]["valid_json"] = bool(payload.get("choices"))  # type: ignore[index]

        primary = httpx.post(
            f"{base_url}/v1/chat/completions",
            headers=headers,
            json={
                "model": "dgx-moa",
                "messages": [{"role": "user", "content": "Reply exactly PRIMARY_OK"}],
                "stream": False,
                "max_tokens": 32,
            },
            timeout=300,
        )
        results["primary"] = {"status_code": primary.status_code, "valid_json": False}
        if primary.status_code == 200:
            results["primary"]["valid_json"] = bool(primary.json().get("choices"))  # type: ignore[index]

        codex_home = root / "codex/home/.codex"
        codex_work = root / "codex/work"
        codex_home.mkdir(parents=True)
        codex_work.mkdir(parents=True)
        (codex_home / "config.toml").write_text(
            'model = "dgx-moa-fast"\n'
            'model_provider = "dgx_moa"\n'
            'model_reasoning_effort = "high"\n'
            'approval_policy = "never"\n'
            'sandbox_mode = "read-only"\n\n'
            "[model_providers.dgx_moa]\n"
            'name = "DGX MoA isolated validation"\n'
            f'base_url = "{base_url}/v1"\n'
            'env_key = "DGX_MOA_API_KEY"\n'
            'wire_api = "responses"\n'
        )
        codex_env = client_env(root / "codex/environment", secret)
        codex_env["CODEX_HOME"] = str(codex_home)
        codex = run(
            [
                "codex",
                "exec",
                "--ephemeral",
                "--skip-git-repo-check",
                "--json",
                "Reply exactly CODEX_CLIENT_OK and do not call tools.",
            ],
            cwd=codex_work,
            env=codex_env,
        )
        results["codex"] = {
            "exit_code": codex.returncode,
            "completed": '"type":"turn.completed"' in codex.stdout.replace(" ", ""),
            "marker_seen": "CODEX_CLIENT_OK" in codex.stdout,
        }

        opencode_work = root / "opencode/work"
        opencode_work.mkdir(parents=True)
        (opencode_work / "opencode.json").write_text(
            json.dumps(
                {
                    "$schema": "https://opencode.ai/config.json",
                    "provider": {
                        "dgx-moa": {
                            "npm": "@ai-sdk/openai-compatible",
                            "name": "DGX MoA isolated validation",
                            "options": {
                                "baseURL": f"{base_url}/v1",
                                "apiKey": "{env:DGX_MOA_API_KEY}",
                            },
                            "models": {
                                "dgx-moa-fast": {
                                    "name": "DGX MoA fast",
                                    "limit": {"context": 65_536, "output": 16_384},
                                }
                            },
                        }
                    },
                    "model": "dgx-moa/dgx-moa-fast",
                    "permission": {"*": "allow"},
                },
                indent=2,
            )
            + "\n"
        )
        opencode = run(
            [
                "opencode",
                "run",
                "--pure",
                "--auto",
                "--format",
                "json",
                "--model",
                "dgx-moa/dgx-moa-fast",
                "Reply exactly OPENCODE_CLIENT_OK and do not call tools.",
            ],
            cwd=opencode_work,
            env=client_env(root / "opencode/environment", secret),
        )
        results["opencode"] = {
            "exit_code": opencode.returncode,
            "marker_seen": "OPENCODE_CLIENT_OK" in opencode.stdout,
        }

        hermes_home = root / "hermes/home"
        hermes_work = root / "hermes/work"
        hermes_home.mkdir(parents=True)
        hermes_work.mkdir(parents=True)
        (hermes_home / "config.yaml").write_text(
            "model:\n"
            "  default: dgx-moa-fast\n"
            "  provider: custom\n"
            f"  base_url: {base_url}/v1\n"
            "  api_key: ${DGX_MOA_API_KEY}\n"
            "  context_length: 65536\n"
            "  max_tokens: 128\n"
        )
        hermes_env = client_env(root / "hermes/environment", secret)
        hermes_env["HERMES_HOME"] = str(hermes_home)
        hermes = run(
            [
                "hermes",
                "--ignore-rules",
                "-z",
                "Reply exactly HERMES_CLIENT_OK and do not call tools.",
                "--usage-file",
                str(root / "hermes/usage.json"),
            ],
            cwd=hermes_work,
            env=hermes_env,
        )
        results["hermes"] = {
            "exit_code": hermes.returncode,
            "marker_seen": hermes.stdout.strip() == "HERMES_CLIENT_OK",
        }
    finally:
        server.should_exit = True
        thread.join(timeout=30)

    report = root / "runtime/model-invocation-rates.csv"
    rate_rows = list(csv.DictReader(report.open())) if report.is_file() else []
    after = git_fingerprint(PRODUCTION)
    passed = (
        before == after
        and not thread.is_alive()
        and all(
            isinstance(row, dict) and row.get("exit_code") == 0 and row.get("marker_seen") is True
            for row in (results.get("codex"), results.get("opencode"), results.get("hermes"))
        )
        and results.get("generic") == {"status_code": 200, "valid_json": True}
        and results.get("primary") == {"status_code": 200, "valid_json": True}
        and any(
            row["role"] == "executor" and int(row["invocation_count"]) >= 6 for row in rate_rows
        )
        and any(
            row["role"] == "reasoner"
            and row["model"] == "Qwythos-v2-9B:Q4"
            and int(row["invocation_count"]) >= 1
            for row in rate_rows
        )
    )
    for client in ("codex", "opencode", "hermes"):
        shutil.rmtree(root / client)
    summary = {
        "schema": "live-client-matrix-v1",
        "passed": passed,
        "clients": results,
        "model_invocation_rate_rows": len(rate_rows),
        "executor_invocations_recorded": max(
            (int(row["invocation_count"]) for row in rate_rows if row["role"] == "executor"),
            default=0,
        ),
        "reasoner_invocations_recorded": max(
            (int(row["invocation_count"]) for row in rate_rows if row["role"] == "reasoner"),
            default=0,
        ),
        "production_git_unchanged": before == after,
        "gateway_stopped": not thread.is_alive(),
        "raw_client_artifacts_removed": all(
            not (root / client).exists() for client in ("codex", "opencode", "hermes")
        ),
    }
    (root / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, sort_keys=True))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
