#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
[[ -f .env ]] && { set -a; source .env; set +a; }
[[ -f .env.local ]] && { set -a; source .env.local; set +a; }
base=${DGX_MOA_BASE_URL:-http://${DGX_MOA_BIND_HOST:-127.0.0.1}:${DGX_MOA_BIND_PORT:-9000}}
auth=(-H "Authorization: Bearer ${DGX_MOA_API_KEY:?}")
session="opencode-loop-$(date +%s)"
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
curl -fsS "$base/healthz" >/dev/null
curl -fsS "${auth[@]}" "$base/v1/models" >/dev/null
cat >"$temporary/request.json" <<'JSON'
{"model":"dgx-moa-agent","messages":[{"role":"user","content":"Call read_file once for /tmp/dgx-moa-validation.txt."}],"tools":[{"type":"function","function":{"name":"read_file","description":"Read a file","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"],"additionalProperties":false}}}],"tool_choice":"required","metadata":{"target_clear":true,"expected_files":1,"validation_command":"true"}}
JSON
curl -fsS "${auth[@]}" -H "X-Session-ID: $session" -H 'Content-Type: application/json' \
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
  curl -fsS "${auth[@]}" -H "X-Session-ID: $session" -H 'Content-Type: application/json' \
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
curl -fsS -N "${auth[@]}" -H 'Content-Type: application/json' \
  -d '{"model":"dgx-moa-agent","stream":true,"messages":[{"role":"user","content":"Reply READY."}],"metadata":{"target_clear":true,"expected_files":1,"validation_command":"true"}}' \
  "$base/v1/chat/completions" | grep -q 'data: \[DONE\]'
printf 'session=%s tool_result_continuation=passed streaming=passed\n' "$session"
