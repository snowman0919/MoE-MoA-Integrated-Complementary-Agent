#!/usr/bin/env python3
# ruff: noqa: E501
"""Run one bounded, secret-free physical OpenCode completion diagnostic."""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any


def encoded(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


def remote_script(config: dict[str, Any], model: str, timeout: int) -> str:
    config64, model64 = encoded(json.dumps(config)), encoded(model)
    return f'''$ErrorActionPreference = "Stop"
$key = [Console]::In.ReadToEnd().Trim()
$decode = {{ param([string]$value) [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($value)) }}
$dir = Join-Path $env:TEMP ("opencode-completion-" + [guid]::NewGuid().ToString())
$config = & $decode "{config64}"
$model = & $decode "{model64}"
$exe = "C:\\Users\\dbsgu\\AppData\\Roaming\\npm\\node_modules\\opencode-ai\\bin\\opencode.exe"
$out = Join-Path $dir "stdout.jsonl"
$err = Join-Path $dir "stderr.log"
$exit = Join-Path $dir "exit.txt"
$runner = Join-Path $dir "run.cmd"
New-Item -ItemType Directory -Path $dir | Out-Null
Set-Content -LiteralPath (Join-Path $dir "README.md") -Value "fixture" -Encoding utf8
[IO.File]::WriteAllText((Join-Path $dir "opencode.json"), $config)
$env:DGX_MOA_API_KEY = $key
$command = "run --format json --auto --dir " + $dir + " --model " + $model + " `"Create COMPLETION.txt containing exactly DONE, then reply WORKER_DONE.`""
[IO.File]::WriteAllText($runner, "@echo off`r`n`"$exe`" $command 1>`"$out`" 2>`"$err`"`r`necho %ERRORLEVEL% > `"$exit`"")
$parent = $PID
$process = Start-Process -FilePath "cmd.exe" -ArgumentList ("/d /c " + $runner) -WorkingDirectory $dir -PassThru
$snapshots = @()
$deadline = [datetime]::UtcNow.AddSeconds({timeout})
while (-not $process.HasExited -and [datetime]::UtcNow -lt $deadline) {{
  $children = @(Get-CimInstance Win32_Process | Where-Object {{ $_.ParentProcessId -eq $process.Id }} | ForEach-Object {{ @{{ pid = $_.ProcessId; name = $_.Name }} }})
  $phase = if (Test-Path (Join-Path $dir "COMPLETION.txt")) {{ "after_edit" }} else {{ "before_final_sse" }}
  $snapshots += @{{ at = [datetime]::UtcNow.ToString("o"); phase = $phase; child_processes = $children }}
  Start-Sleep -Milliseconds 250
  $process.Refresh()
}}
$timedOut = -not $process.HasExited
if ($timedOut) {{ Stop-Process -Id $process.Id -Force; $process.WaitForExit() }}
$process.WaitForExit()
$exitCode = if ($timedOut -or -not (Test-Path $exit)) {{ $null }} else {{ [int]([IO.File]::ReadAllText($exit).Trim()) }}
$stdout = if (Test-Path $out) {{ [IO.File]::ReadAllText($out) }} else {{ "" }}
$stderr = if (Test-Path $err) {{ [IO.File]::ReadAllText($err) }} else {{ "" }}
if ($stdout -match '"reason":"stop"') {{
  $snapshots += @{{ at = [datetime]::UtcNow.ToString("o"); phase = "after_final_sse"; child_processes = @() }}
}}
$result = [ordered]@{{
  opencode_version = (& $exe --version).Trim()
  command_shape = "opencode.exe run --format json --auto --dir <isolated-fixture> --model " + $model
  powershell_parent_pid = $parent
  opencode_parent_pid = $process.Id
  process_snapshots = $snapshots
  final_process_state = if ($timedOut) {{ "killed_at_timeout" }} else {{ "exited" }}
  exit_code = $exitCode
  fixture_completion = if (Test-Path (Join-Path $dir "COMPLETION.txt")) {{ [IO.File]::ReadAllText((Join-Path $dir "COMPLETION.txt")) }} else {{ $null }}
  fixture_diff = if (Test-Path (Join-Path $dir "COMPLETION.txt")) {{ @{{ added = "COMPLETION.txt"; content = [IO.File]::ReadAllText((Join-Path $dir "COMPLETION.txt")) }} }} else {{ $null }}
  stdout_tail = $stdout.Substring([Math]::Max(0, $stdout.Length - 6000))
  stderr_tail = $stderr.Substring([Math]::Max(0, $stderr.Length - 2000))
}}
Remove-Item -LiteralPath $dir -Recurse -Force
[Console]::WriteLine("RESULT=" + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($result | ConvertTo-Json -Depth 8 -Compress))))'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="win")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", default="dgx-moa/dgx-moa-agent")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/diagnostics/opencode-completion")
    )
    args = parser.parse_args()
    token = os.getenv("DGX_MOA_API_KEY")
    if not token:
        raise SystemExit("DGX_MOA_API_KEY is required")
    provider, model_name = args.model.split("/", 1)
    base_url = args.base_url.rstrip("/")
    if not base_url.endswith("/v1"):
        base_url += "/v1"
    config = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            provider: {
                "npm": "@ai-sdk/openai-compatible",
                "name": "DGX MoA",
                "options": {
                    "baseURL": base_url,
                    "apiKey": "{env:DGX_MOA_API_KEY}",
                },
                "models": {model_name: {"name": "DGX MoA Agent"}},
            }
        },
        "permission": {
            "*": "deny",
            "edit": "allow",
            "write": "allow",
            "bash": "allow",
            "read": "allow",
            "glob": "allow",
            "grep": "allow",
        },
    }
    command = remote_script(config, args.model, args.timeout)
    encoded_command = base64.b64encode(command.encode("utf-16le")).decode()
    run = subprocess.run(
        ["ssh", args.host, "powershell", "-NoProfile", "-EncodedCommand", encoded_command],
        input=token,
        text=True,
        capture_output=True,
        timeout=args.timeout + 30,
    )
    if run.returncode:
        raise RuntimeError((run.stderr + run.stdout)[-4000:])
    result_line = next((line for line in run.stdout.splitlines() if line.startswith("RESULT=")), "")
    if not result_line:
        raise RuntimeError("remote diagnostic did not return a result")
    result = json.loads(base64.b64decode(result_line.removeprefix("RESULT=")))
    result["captured_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    result["fixture_removed"] = True
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / f"opencode-physical-{uuid.uuid4()}.json"
    output.write_text(json.dumps(result, indent=2) + "\n")
    if result["final_process_state"] != "exited" or result["exit_code"] != 0:
        raise SystemExit(f"physical OpenCode did not complete: {output}")
    print(output)


if __name__ == "__main__":
    main()
