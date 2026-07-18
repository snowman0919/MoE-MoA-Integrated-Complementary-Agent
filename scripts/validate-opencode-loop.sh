#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
[[ -f .env ]] && { set -a; source .env; set +a; }
[[ -f .env.local ]] && { set -a; source .env.local; set +a; }
base=${DGX_MOA_BASE_URL:-http://${DGX_MOA_BIND_HOST:-127.0.0.1}:${DGX_MOA_BIND_PORT:-9000}}
auth=(-H "Authorization: Bearer ${DGX_MOA_API_KEY:?}")
session="opencode-loop-$(date +%s)"
stream_session="$session-stream"
branch=$(git branch --show-current)
commit=$(git rev-parse HEAD)
dirty=$(test -n "$(git status --porcelain)" && echo dirty || echo clean)
identity=(
  -H 'X-Runtime-Channel: dev'
  -H 'X-Trace-Origin: validation'
  -H "X-Workspace-Path: $PWD"
  -H "X-Workspace-ID: $session"
  -H "X-Repository-Branch: $branch"
  -H "X-Repository-Commit: $commit"
  -H "X-Dirty-State: $dirty"
)
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
curl -fsS "$base/healthz" >/dev/null
curl -fsS "${auth[@]}" "$base/v1/models" >/dev/null
cat >"$temporary/request.json" <<'JSON'
{"model":"dgx-moa-agent","messages":[{"role":"user","content":"Call read_file once for /tmp/dgx-moa-validation.txt."}],"tools":[{"type":"function","function":{"name":"read_file","description":"Read a file","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"],"additionalProperties":false}}}],"tool_choice":"required"}
JSON
curl -fsS "${auth[@]}" "${identity[@]}" -H "X-Session-ID: $session" \
  -H 'X-Task-ID: live-loop-continuation' -H 'Content-Type: application/json' \
  --data-binary @"$temporary/request.json" "$base/v1/chat/completions" >"$temporary/tool.json"
SESSION="$session" TOOL="$temporary/tool.json" REQUEST="$temporary/request.json" uv run python - <<'PY'
import json, os
body=json.load(open(os.environ['TOOL']))
message=body['choices'][0]['message']
call=message['tool_calls'][0]
assert call['id'] and call['function']['name'] == 'read_file'
request=json.load(open(os.environ['REQUEST']))
request['messages'] += [message, {'role':'tool','tool_call_id':call['id'],'content':json.dumps({'tool_name':'read_file','arguments':json.loads(call['function']['arguments']),'stdout':'validation fixture','stderr':'','exit_code':0,'duration_ms':1,'truncated':False})}]
request.pop('tools', None)
request.pop('tool_choice', None)
open(os.environ['REQUEST'], 'w').write(json.dumps(request))
PY
for attempt in 1 2; do
  curl -fsS "${auth[@]}" "${identity[@]}" -H "X-Session-ID: $session" \
    -H 'X-Task-ID: live-loop-continuation' -H 'Content-Type: application/json' \
    --data-binary @"$temporary/request.json" "$base/v1/chat/completions" >"$temporary/final.json"
  if FINAL="$temporary/final.json" uv run python - <<'PY'
import json, os
message=json.load(open(os.environ['FINAL']))['choices'][0]['message']
assert not message.get('tool_calls')
assert message.get('content')
PY
  then break; fi
  [[ $attempt == 2 ]] && exit 1
done
curl -fsS -N "${auth[@]}" "${identity[@]}" -H "X-Session-ID: $stream_session" \
  -H 'X-Task-ID: live-loop-stream' -H 'Content-Type: application/json' \
  -d '{"model":"dgx-moa-agent","stream":true,"messages":[{"role":"user","content":"Reply READY."}]}' \
  "$base/v1/chat/completions" >"$temporary/stream.out"
grep -q 'data: \[DONE\]' "$temporary/stream.out"
sleep 1
for completed in "$session" "$stream_session"; do
  uv run python scripts/finalize-validation-session.py "$completed" --status completed \
    --workspace "$PWD" --evidence 'live_loop=tool continuation or streaming passed' \
    --state-db "${DGX_MOA_STATE_DB:-data/state/gateway.db}" --trace-dir data/traces \
    --config "${DGX_MOA_CONFIG:-config/models.yaml}" >/dev/null
done
printf 'session=%s tool_result_continuation=passed streaming=passed\n' "$session"
