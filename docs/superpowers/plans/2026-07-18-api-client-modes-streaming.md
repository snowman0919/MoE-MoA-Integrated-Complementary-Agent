# API Client Modes and Real Streaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make chat, external-agent, and explicit orchestration modes reliably OpenAI-compatible, immediately streaming, native-tool preserving, and stage-observable.

**Architecture:** Keep one FastAPI gateway and existing controller/provider/state stack. Resolve a fixed public model alias to a deterministic request policy, reuse the controller only for state and explicit orchestration, and forward bounded SSE events as they arrive without reviewer gating. Keep planner/reviewer/Judge structured; make executor output normal OpenAI assistant content or native tool calls.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic 2, HTTPX, SQLite, vLLM 0.22.1, pytest, Ruff, MyPy, systemd user units.

## Global Constraints

- Work only in `/home/kotori9/code/MoE-MoA-Integrated-Complementary-Agent` on `dev`.
- Treat `/home/kotori9/dgx-moa-agent` on `main` as read-only.
- Do not start, stop, restart, replace, or deploy production services.
- Public executor context remains exactly 65,536 tokens; do not advertise a false limit.
- Preserve native tool-call IDs, names, JSON arguments, deltas, finish reasons, usage, completion IDs, timestamps, and upstream model fields.
- Standard clients require only OpenAI fields; project metadata remains optional.
- Do not add dependencies, Redis, Kafka, Celery, Kubernetes, Rust, Frontier, recursive improvement, Tailscale Serve/Funnel, or AppArmor changes.
- Default executor output budget is 4,096 tokens; configurable server maximum is 16,384 tokens.
- Streaming capture is bounded to 1,000,000 bytes and one SSE event is bounded to 1,000,000 bytes.
- Low-risk reviewer failure preserves valid executor output; high-risk explicit orchestration may fail closed.
- Test-first for each behavioral change; commit each independently reviewable task.

---

## File Map

- `gateway/src/dgx_moa/routing.py`: public alias resolution, deterministic request classification, required-role and review-failure policy.
- `gateway/src/dgx_moa/schemas.py`: supported OpenAI request fields and semantic combination validation.
- `gateway/src/dgx_moa/config.py`: output, capture, and stage-timeout configuration.
- `gateway/src/dgx_moa/controller.py`: role-aware preparation, executor contract, bounded reviewer evidence, review policy state.
- `gateway/src/dgx_moa/providers.py`: stage-specific HTTP timeout inputs and upstream OpenAI error preservation.
- `gateway/src/dgx_moa/streaming.py`: focused SSE event framing, bounded observation, duplicate-DONE filtering, and cancellation-safe upstream close.
- `gateway/src/dgx_moa/api.py`: policy dispatch, OpenAI error handlers, direct executor path, immediate stream forwarding, timing/truncation events.
- `gateway/src/dgx_moa/state.py`: request mode/class/roles, timing, truncation, and deferred-review fields.
- `gateway/src/dgx_moa/trace.py`: expose new content-free runtime evidence in trace metrics.
- `gateway/src/dgx_moa/prompts/executor.md`: normal assistant/native-tool executor contract.
- `gateway/src/dgx_moa/serve.py`: honor explicit context override without changing configured production defaults.
- `config/models.yaml`: phase-one limits and stage timeouts.
- `tests/test_state_routing.py`, `tests/test_api.py`, `tests/test_controller.py`, `tests/test_providers.py`, `tests/test_streaming.py`, `tests/test_serve.py`, `tests/conftest.py`: focused TDD coverage.
- `README.md`, `docs/API_CLIENT_MODES.md`, `docs/HERMES_AGENT.md`, `docs/STATE.md`, `docs/VALIDATION.md`, `docs/OPERATIONS.md`, `docs/ARCHITECTURE.md`, `docs/TRACE_SCHEMA.md`, `docs/DECISIONS.md`: verified contracts and evidence.
- `scripts/validate-opencode-loop.sh`: select `dgx-moa-agent` explicitly while retaining standard request shape.

---

### Task 0: Preserve the Physical Starting Failure

**Files:**
- Modify: `docs/VALIDATION.md`

**Interfaces:**
- Consumes: clean `dev@0b83e18`, real vLLM role endpoints on controlled foreground processes.
- Produces: immutable baseline showing downstream first-byte delay behind reviewer.

- [x] **Step 1: Verify isolation before startup**

Run:

```bash
systemctl --user is-active dgx-moa-gateway.service dgx-moa-executor.service \
  dgx-moa-planner.service dgx-moa-reviewer.service
ss -ltn '( sport = :8101 or sport = :8102 or sport = :8103 or sport = :19000 )'
git -C /home/kotori9/dgx-moa-agent status --short --branch
```

Expected: four `inactive` lines, no matching listeners, production `main` clean.

- [x] **Step 2: Run isolated real models and timed gateway**

Use foreground dev processes, gateway `127.0.0.1:19000`, state
`/tmp/dgx-moa-phase1.6roKBd/state/gateway.db`, trace root
`/tmp/dgx-moa-phase1.6roKBd/traces`, and run root
`/tmp/dgx-moa-phase1.6roKBd/data/run`. Use a fresh environment-only validation
credential. Do not source production credentials.

Expected: planner, executor, reviewer all serve 65,536 context; production units remain inactive.

- [x] **Step 3: Record measured result**

Recorded evidence:

```text
planner_seconds=24.472949071
executor_first_byte_seconds=1.589025047
executor_total_seconds=8.621550954
reviewer_seconds=34.358891291
downstream_first_byte_seconds=67.505579598
executor_to_downstream_first_byte_seconds=41.402552329
http_status=200
sse_bytes=62174
done_count=1
```

Expected: `docs/VALIDATION.md` states that downstream first byte arrived 4.29 ms after reviewer completion, proving buffering.

- [x] **Step 4: Stop only controlled foreground processes**

Expected: ports `8101`, `8102`, `8103`, and `19000` unbound;
`MemAvailable=122509758464`; production units still inactive; production worktree clean.

---

### Task 1: Add Public Model Modes and Deterministic Policy

**Files:**
- Modify: `gateway/src/dgx_moa/routing.py`
- Modify: `gateway/src/dgx_moa/state.py`
- Test: `tests/test_state_routing.py`

**Interfaces:**
- Consumes: requested model string, configured backward-compatible model name, messages, tools, metadata.
- Produces: `RuntimeMode`, `RequestClass`, `resolve_runtime_mode()`, `classify_request()`, `required_roles()`, `review_fails_closed()`.

- [ ] **Step 1: Write failing policy tests**

Append to `tests/test_state_routing.py`:

```python
import pytest
from dgx_moa.routing import (
    classify_request,
    required_roles,
    resolve_runtime_mode,
    review_fails_closed,
)


@pytest.mark.parametrize(
    ("model", "mode"),
    [
        ("dgx-moa-chat", "chat"),
        ("dgx-moa-agent", "agent"),
        ("dgx-moa-orchestrated", "orchestrated"),
    ],
)
def test_public_model_aliases(model: str, mode: str) -> None:
    assert resolve_runtime_mode(model, "dgx-moa-agent") == mode


def test_unknown_model_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown model"):
        resolve_runtime_mode("missing", "dgx-moa-agent")


def test_request_classes_and_roles() -> None:
    assert classify_request(
        "chat", [{"role": "user", "content": "Hello"}], None, {}
    ) == "plain_chat"
    assert classify_request(
        "chat", [{"role": "user", "content": "What changed?"}], None, {}
    ) == "read_only_question"
    assert classify_request(
        "agent", [{"role": "tool", "content": "ok"}], None, {}
    ) == "native_agent_turn"
    assert classify_request(
        "orchestrated", [], None, {"target_clear": True, "expected_files": 1}
    ) == "small_clear_edit"
    assert classify_request(
        "orchestrated", [], None, {"expected_files": 4}
    ) == "multi_file_task"
    assert classify_request(
        "orchestrated", [], None, {"recovery_task": True}
    ) == "recovery_task"
    assert classify_request(
        "orchestrated", [], None, {"authentication": True}
    ) == "high_risk_task"
    assert classify_request("orchestrated", [], None, {}) == "explicit_orchestrated"
    assert required_roles("chat", "plain_chat") == ("executor",)
    assert required_roles("agent", "high_risk_task") == ("executor",)
    assert required_roles("orchestrated", "multi_file_task") == ("planner", "executor")
    assert required_roles("orchestrated", "high_risk_task") == (
        "planner", "executor", "reviewer"
    )
    assert review_fails_closed("high_risk_task") is True
    assert review_fails_closed("explicit_orchestrated") is False
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
uv run pytest tests/test_state_routing.py -q
```

Expected: import failures for the four new policy functions.

- [ ] **Step 3: Implement minimal deterministic policy**

Add to `gateway/src/dgx_moa/routing.py`:

```python
from typing import Literal

RuntimeMode = Literal["chat", "agent", "orchestrated"]
RequestClass = Literal[
    "plain_chat",
    "read_only_question",
    "native_agent_turn",
    "small_clear_edit",
    "multi_file_task",
    "recovery_task",
    "high_risk_task",
    "explicit_orchestrated",
]

MODEL_MODES: dict[str, RuntimeMode] = {
    "dgx-moa-chat": "chat",
    "dgx-moa-agent": "agent",
    "dgx-moa-orchestrated": "orchestrated",
}
HIGH_RISK_FIELDS = (
    "authentication",
    "cryptography",
    "database_schema",
    "deployment_security",
    "public_api",
    "heavy_review",
)


def resolve_runtime_mode(model: str, configured_name: str) -> RuntimeMode:
    aliases = MODEL_MODES | {configured_name: "agent"}
    try:
        return aliases[model]
    except KeyError as error:
        raise ValueError("unknown model") from error


def classify_request(
    mode: RuntimeMode,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    metadata: dict[str, Any],
) -> RequestClass:
    if any(bool(metadata.get(field)) for field in HIGH_RISK_FIELDS):
        return "high_risk_task"
    if bool(metadata.get("recovery_task") or metadata.get("no_progress")):
        return "recovery_task"
    if mode == "agent" or any(message.get("role") == "tool" for message in messages):
        return "native_agent_turn"
    files = int(metadata.get("expected_files", metadata.get("files_changed", 0)) or 0)
    if files > 2 or bool(metadata.get("scope_uncertain")):
        return "multi_file_task"
    if mode == "orchestrated" and bool(metadata.get("target_clear")) and files in {1, 2}:
        return "small_clear_edit"
    if mode == "orchestrated":
        return "explicit_orchestrated"
    latest = next(
        (str(message.get("content", "")).strip() for message in reversed(messages)
         if message.get("role") == "user"),
        "",
    )
    return "read_only_question" if latest.endswith("?") else "plain_chat"


def required_roles(mode: RuntimeMode, request_class: RequestClass) -> tuple[str, ...]:
    if mode != "orchestrated":
        return ("executor",)
    if request_class in {"multi_file_task", "recovery_task"}:
        return ("planner", "executor")
    if request_class in {"high_risk_task", "explicit_orchestrated"}:
        return ("planner", "executor", "reviewer")
    return ("executor",)


def review_fails_closed(request_class: RequestClass) -> bool:
    return request_class == "high_risk_task"
```

Add fields to `SessionState` in `gateway/src/dgx_moa/state.py`:

```python
runtime_mode: Literal["chat", "agent", "orchestrated"] = "agent"
request_class: str = "native_agent_turn"
roles_required: list[str] = Field(default_factory=lambda: ["executor"])
review_fail_closed: bool = False
review_deferred: bool = False
finish_reasons: list[str] = Field(default_factory=list)
truncated: bool = False
timings_ms: dict[str, float] = Field(default_factory=dict)
```

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
uv run pytest tests/test_state_routing.py -q
uv run mypy
```

Expected: both exit 0.

- [ ] **Step 5: Commit**

```bash
git add gateway/src/dgx_moa/routing.py gateway/src/dgx_moa/state.py tests/test_state_routing.py
git commit -m "feat(routing): add explicit client modes"
```

---

### Task 2: Restore Executor Contract and Executor-Only Direct Paths

**Files:**
- Modify: `gateway/src/dgx_moa/prompts/executor.md`
- Modify: `gateway/src/dgx_moa/controller.py`
- Modify: `gateway/src/dgx_moa/api.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_controller.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: Task 1 policy functions and `roles_required`.
- Produces: `Controller.prepare_executor(state, request, roles)` that invokes only listed roles and never forces executor JSON.

- [ ] **Step 1: Write failing direct-mode and prompt tests**

Update `tests/test_api.py` model test to require all aliases and executor-only calls:

```python
assert [model["id"] for model in models["data"]] == [
    "dgx-moa-chat",
    "dgx-moa-agent",
    "dgx-moa-orchestrated",
]
assert all(model["context_length"] == 65536 for model in models["data"])
assert stub_provider.calls == ["executor"]
```

Add:

```python
@pytest.mark.parametrize("model", ["dgx-moa-chat", "dgx-moa-agent"])
def test_direct_modes_are_executor_only(settings, stub_provider: StubProvider, model: str) -> None:
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={"model": model, "messages": [{"role": "user", "content": "hello"}]},
        )
    assert response.status_code == 200
    assert stub_provider.calls == ["executor"]


def test_chat_returns_normal_assistant_content(settings, stub_provider: StubProvider) -> None:
    async def natural(role, model, request):  # type: ignore[no-untyped-def]
        stub_provider.calls.append(role)
        return {
            "id": "chatcmpl-natural",
            "model": "dgx-moa-executor",
            "created": 123,
            "choices": [{
                "message": {"role": "assistant", "content": "Hello from executor."},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 2, "completion_tokens": 4, "total_tokens": 6},
        }

    stub_provider.complete = natural  # type: ignore[method-assign]
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={"model": "dgx-moa-chat", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert response.json()["choices"][0]["message"] == {
        "role": "assistant", "content": "Hello from executor."
    }
    assert response.json()["id"] == "chatcmpl-natural"
    assert response.json()["created"] == 123
    assert response.json()["model"] == "dgx-moa-executor"
    assert response.json()["usage"]["total_tokens"] == 6


def test_orchestrated_mode_uses_policy_roles(settings, stub_provider: StubProvider) -> None:
    with client_with_stub(settings, stub_provider) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-secret"},
            json={
                "model": "dgx-moa-orchestrated",
                "messages": [{"role": "user", "content": "change four files"}],
                "metadata": {"expected_files": 4},
            },
        )
    assert response.status_code == 200
    assert stub_provider.calls == ["planner", "executor"]
```

Add to `tests/test_controller.py`:

```python
def test_executor_prompt_does_not_force_json(settings, stub_provider: StubProvider) -> None:
    controller = Controller(settings, StateStore(settings.state_db), stub_provider)  # type: ignore[arg-type]
    prompt = controller.prompt_sandwich(
        "executor", SessionState(session_id="executor", objective="answer"), "", "Answer"
    )
    assert "Return one JSON object only" not in prompt
    assert "Use native OpenAI tool calls" in prompt
```

- [ ] **Step 2: Run focused tests and verify RED**

```bash
uv run pytest tests/test_api.py tests/test_controller.py -q
```

Expected: alias discovery, executor-only calls, and prompt contract fail.

- [ ] **Step 3: Implement role-aware executor preparation**

Replace `gateway/src/dgx_moa/prompts/executor.md` with:

```text
You are the executor. Use native OpenAI tool calls when an action is required.
Otherwise return normal assistant content. Do not encode tool calls as JSON text.
Do not wrap native tool calls in prose or Markdown fences.
```

In `Controller.prompt_sandwich()`, choose the final line by role:

```python
final_output = (
    f"Return one JSON object only: {schema}"
    if role in {"planner", "reviewer", "judge"}
    else (
        "Use native OpenAI tool calls when an action is required. Otherwise return normal "
        "assistant content. Do not encode tool calls as JSON text or wrap native tool calls "
        "in prose or Markdown fences."
    )
)
```

Use `f"FINAL REQUIRED OUTPUT\n{final_output}"` in the prompt tuple.

Change preparation signature and guards:

```python
async def prepare_executor(
    self, state: SessionState, request: dict[str, Any], roles: tuple[str, ...]
) -> dict[str, Any]:
    if state.phase == Phase.BLOCKED:
        raise ValueError("session blocked after no progress")
    reasoner = self.settings.models.get("reasoner") if "reasoner" in roles else None
```

Replace the existing planner condition with this exact condition while leaving
its tested structured request/retry body unchanged:

```python
if "planner" in roles and needs_planner(state) and "planner" in self.settings.models:
```

Keep the existing executor body construction after optional roles. Do not add an internal tool loop.

In `api.py`, resolve and persist policy before preparation:

```python
mode = resolve_runtime_mode(body.model, configured.model_name)
request_class = classify_request(mode, raw["messages"], raw.get("tools"), raw["metadata"])
roles = required_roles(mode, request_class)
state.runtime_mode = mode
state.request_class = request_class
state.roles_required = list(roles)
state.review_fail_closed = review_fails_closed(request_class)
prepared = await request.app.state.controller.prepare_executor(state, raw, roles)
```

Update `/v1/models` to emit the three fixed aliases in table order and use executor context `65536` for each.

- [ ] **Step 4: Run focused and regression tests**

```bash
uv run pytest tests/test_api.py tests/test_controller.py tests/test_state_routing.py -q
```

Expected: direct modes call only executor; orchestrated multi-file calls planner then executor; all pass.

- [ ] **Step 5: Commit**

```bash
git add gateway/src/dgx_moa/api.py gateway/src/dgx_moa/controller.py \
  gateway/src/dgx_moa/prompts/executor.md tests/conftest.py tests/test_api.py \
  tests/test_controller.py
git commit -m "fix(gateway): restore executor output contract"
```

---

### Task 3: Preserve Supported Fields, Token Budgets, and Typed Errors

**Files:**
- Modify: `gateway/src/dgx_moa/config.py`
- Modify: `gateway/src/dgx_moa/schemas.py`
- Modify: `gateway/src/dgx_moa/providers.py`
- Modify: `gateway/src/dgx_moa/api.py`
- Modify: `config/models.yaml`
- Test: `tests/test_api.py`
- Test: `tests/test_providers.py`

**Interfaces:**
- Consumes: validated `ChatRequest` and configured `Limits`.
- Produces: preserved executor request body, OpenAI error envelope, 4,096 default, 16,384 maximum.

- [ ] **Step 1: Write failing field and error tests**

Add an executor request capture to `StubProvider` and assert this exact set survives:

```python
expected = {
    "temperature": 0.2,
    "top_p": 0.8,
    "max_tokens": 4096,
    "stop": ["END"],
    "parallel_tool_calls": False,
    "stream_options": {"include_usage": True},
    "response_format": {"type": "text"},
}
assert expected.items() <= stub_provider.requests[-1].items()
```

Add API assertions:

```python
assert invalid_model.json() == {
    "error": {
        "message": "unknown model",
        "type": "invalid_request_error",
        "code": "model_not_found",
        "param": "model",
    }
}
assert too_large.status_code == 400
assert too_large.json()["error"]["param"] == "max_tokens"
assert missing_tools.status_code == 422
assert missing_tools.json()["error"]["code"] == "invalid_request"
```

Add provider test for an upstream 400 body and require status/body preservation rather than 502.

- [ ] **Step 2: Run focused tests and verify RED**

```bash
uv run pytest tests/test_api.py tests/test_providers.py -q
```

- [ ] **Step 3: Add explicit request fields and semantic validators**

Add fields to `ChatRequest`:

```python
tool_choice: str | dict[str, Any] | None = None
parallel_tool_calls: bool | None = None
temperature: float | None = Field(default=None, ge=0, le=2)
top_p: float | None = Field(default=None, ge=0, le=1)
stop: str | list[str] | None = None
stream_options: dict[str, Any] | None = None
response_format: dict[str, Any] | None = None
```

Extend the existing validator:

```python
if self.tool_choice is not None and not self.tools:
    raise ValueError("tool_choice requires tools")
if self.parallel_tool_calls is not None and not self.tools:
    raise ValueError("parallel_tool_calls requires tools")
if self.stream_options is not None and not self.stream:
    raise ValueError("stream_options requires stream=true")
```

Keep `extra="allow"` so newer standard fields pass to vLLM and receive its typed validation when unsupported.

- [ ] **Step 4: Add configurable token bounds**

Set in `Limits` and `config/models.yaml`:

```python
executor_tokens: int = 4_096
executor_max_tokens: int = 16_384
max_stream_capture_bytes: int = 1_000_000
max_sse_event_bytes: int = 1_000_000
```

In controller preparation:

```python
requested_tokens = int(body.get("max_tokens") or self.settings.limits.executor_tokens)
if requested_tokens > self.settings.limits.executor_max_tokens:
    raise ValueError("max_tokens exceeds server maximum 16384")
body["max_tokens"] = requested_tokens
```

Do not silently clip the request.

- [ ] **Step 5: Return OpenAI-compatible errors**

Add to `api.py`:

```python
def error_response(
    status_code: int,
    message: str,
    error_type: str,
    code: str,
    param: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        {"error": {"message": message, "type": error_type, "code": code, "param": param}},
        status_code=status_code,
        headers=headers,
    )
```

Register `HTTPException` and `RequestValidationError` handlers. For
`httpx.HTTPStatusError`, return the upstream
`{"error":{"message":str,"type":str,"code":str,"param":str|null}}` body and status
when present; otherwise map 4xx to `invalid_request_error` and 5xx to
`backend_error`. Map `httpx.TimeoutException` to status 504, type
`timeout_error`, code naming the recorded stage.

- [ ] **Step 6: Run focused and regression tests**

```bash
uv run pytest tests/test_api.py tests/test_providers.py tests/test_config_auth.py -q
uv run mypy
```

Expected: all pass; no silent 1,000-token cap remains.

- [ ] **Step 7: Commit**

```bash
git add gateway/src/dgx_moa/api.py gateway/src/dgx_moa/config.py \
  gateway/src/dgx_moa/providers.py gateway/src/dgx_moa/schemas.py config/models.yaml \
  tests/conftest.py tests/test_api.py tests/test_providers.py
git commit -m "fix(api): preserve OpenAI request semantics"
```

---

### Task 4: Forward SSE Immediately with Bounded Observation

**Files:**
- Create: `gateway/src/dgx_moa/streaming.py`
- Create: `tests/test_streaming.py`
- Modify: `gateway/src/dgx_moa/api.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Consumes: upstream `AsyncIterator[bytes]`, event/capture bounds.
- Produces: `StreamObservation`, `forward_sse()` async iterator; exactly one successful `[DONE]`; `aclose()` cleanup.

- [ ] **Step 1: Write failing streaming unit tests**

Create `tests/test_streaming.py` with an upstream generator controlled by
`asyncio.Event`. Prove the first forwarded event arrives before allowing the
second upstream event:

```python
@pytest.mark.asyncio
async def test_first_event_is_forwarded_before_upstream_completion() -> None:
    release = asyncio.Event()

    async def upstream() -> AsyncIterator[bytes]:
        yield b'data: {"choices":[{"delta":{"content":"one"},"finish_reason":null}]}\n\n'
        await release.wait()
        yield b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        yield b"data: [DONE]\n\n"

    observation = StreamObservation(max_capture_bytes=1000)
    stream = forward_sse(upstream(), observation, max_event_bytes=1000)
    first = await anext(stream)
    assert b'"content":"one"' in first
    release.set()
    remaining = b"".join([chunk async for chunk in stream])
    assert remaining.count(b"data: [DONE]") == 1
```

Also test split delimiters, CRLF, duplicate DONE filtering, missing DONE synthesis
on clean EOF, exact native `tool_calls` delta bytes, capture truncation at the
configured bound, oversized event rejection, and `aclose()` triggering upstream
`finally` cleanup.

- [ ] **Step 2: Run test and verify RED**

```bash
uv run pytest tests/test_streaming.py -q
```

Expected: module import failure.

- [ ] **Step 3: Implement focused SSE forwarding**

Create `gateway/src/dgx_moa/streaming.py` with:

```python
@dataclass
class StreamObservation:
    max_capture_bytes: int
    captured: bytearray = field(default_factory=bytearray)
    assistant_content: list[str] = field(default_factory=list)
    finish_reasons: list[str] = field(default_factory=list)
    tool_delta_seen: bool = False
    done_seen: bool = False

    def observe(self, event: bytes) -> None:
        remaining = self.max_capture_bytes - len(self.captured)
        if remaining > 0:
            self.captured.extend(event[:remaining])
        for line in event.decode(errors="replace").splitlines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            try:
                payload = json.loads(line[6:])
            except ValueError:
                continue
            choice = (payload.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
            if isinstance(delta.get("content"), str):
                self.assistant_content.append(delta["content"])
            self.tool_delta_seen |= bool(delta.get("tool_calls"))
            if choice.get("finish_reason"):
                self.finish_reasons.append(str(choice["finish_reason"]))
```

Implement a bytearray event framer that extracts the earliest `\n\n` or
`\r\n\r\n` delimiter, rejects an event over `max_event_bytes`, observes each event,
filters every DONE after the first, and synthesizes one DONE only after clean EOF.
In `finally`, call `aclose()` on the upstream object when available.

- [ ] **Step 4: Replace buffered API generator**

Delete `chunks: list[bytes]` and full-response replay from `api.py`. Use:

```python
observation = StreamObservation(configured.limits.max_stream_capture_bytes)

async def stream_response() -> AsyncIterator[bytes]:
    completed = False
    try:
        async for chunk in forward_sse(
            upstream, observation, max_event_bytes=configured.limits.max_sse_event_bytes
        ):
            if "first_downstream_byte" not in state.timings_ms:
                state.timings_ms["first_downstream_byte"] = elapsed_ms(accepted)
            yield chunk
        completed = True
        state.finish_reasons = observation.finish_reasons
        state.truncated = "length" in observation.finish_reasons
        if "reviewer" in state.roles_required:
            state.review_deferred = True
            state.review_status = "deferred"
    except asyncio.CancelledError:
        state.final_status = "cancelled"
        raise
    finally:
        if state.decisions:
            state.decisions[-1]["outcome"] = {
                "status": "success" if completed else "failure",
                "progress_made": bool(observation.finish_reasons),
                "state_changed": False,
                "scope_changed": False,
                "validation_triggered": False,
                "next_phase": state.phase,
            }
        request.app.state.store.event(
            state_session_id,
            "assistant_stream_finished",
            {"finish_reasons": observation.finish_reasons},
        )
        request.app.state.store.event(
            state_session_id,
            "stream_completed" if completed else "stream_aborted",
            {},
        )
        request.app.state.store.save(state)
        record_trace_safely(request, state, task_id)
```

Do not call reviewer inside this streaming generator. Deferred state satisfies the
documented later-correction policy and lets HTTP close immediately after DONE.

- [ ] **Step 5: Run streaming tests and regression tests**

```bash
uv run pytest tests/test_streaming.py tests/test_api.py -q
```

Expected: delayed upstream test proves first event is available before completion;
reviewer absent from streaming provider calls; DONE count exactly one.

- [ ] **Step 6: Commit**

```bash
git add gateway/src/dgx_moa/api.py gateway/src/dgx_moa/streaming.py \
  tests/test_api.py tests/test_streaming.py
git commit -m "fix(stream): forward executor SSE immediately"
```

---

### Task 5: Make Review Evidence-Based and Failure Policy Consistent

**Files:**
- Modify: `gateway/src/dgx_moa/controller.py`
- Modify: `gateway/src/dgx_moa/api.py`
- Modify: `tests/test_controller.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Consumes: Task 1 request class/policy, executor response, session tool and completion evidence.
- Produces: `review_observation()`, `has_review_evidence()`, fail-open low risk, fail-closed high risk, explicit truncation.

- [ ] **Step 1: Write failing reviewer and truncation tests**

Add tests proving:

```python
assert controller.has_review_evidence(SessionState(session_id="chat"), {}) is False
assert controller.has_review_evidence(
    SessionState(session_id="edit", tool_results=[{"changed_paths": ["a.py"]}]), {}
) is True
```

For low-risk orchestrated non-streaming reviewer failure, assert HTTP 200,
executor content preserved, `review_status == "failed"`, and
`observability_degraded is True`. For `authentication=True`, assert a typed 502
with review failure recorded. For `finish_reason="length"`, assert response stays
valid, finish reason remains `length`, state `truncated is True`, and state is not
completed.

- [ ] **Step 2: Run focused tests and verify RED**

```bash
uv run pytest tests/test_controller.py tests/test_api.py -q
```

- [ ] **Step 3: Build bounded evidence object**

Add to `Controller`:

```python
def has_review_evidence(self, state: SessionState, metadata: dict[str, Any]) -> bool:
    return bool(
        state.tool_results
        or state.completion_evidence
        or metadata.get("changed_paths")
        or metadata.get("diff_summary")
        or metadata.get("validation_results")
    )


def review_observation(
    self, state: SessionState, response: dict[str, Any], metadata: dict[str, Any]
) -> str:
    choice = (response.get("choices") or [{}])[0]
    evidence = {
        "original_objective": state.objective,
        "acceptance_criteria": state.acceptance_criteria,
        "changed_paths": metadata.get("changed_paths", []),
        "diff_summary": metadata.get("diff_summary", ""),
        "tool_results": state.tool_results[-4:],
        "validation_results": metadata.get("validation_results", []),
        "scope_evidence": state.approved_scope,
        "completion_evidence": state.completion_evidence,
        "known_failures": state.failures[-4:],
        "assistant_message": choice.get("message", {}),
        "finish_reason": choice.get("finish_reason"),
    }
    return json.dumps(redact(evidence), ensure_ascii=False, sort_keys=True)[
        : self.settings.limits.max_review_evidence_characters
    ]
```

Add `max_review_evidence_characters: int = 16_000` to `Limits` and YAML.

- [ ] **Step 4: Apply consistent review failure policy**

Run review only when `"reviewer" in state.roles_required` and
`has_review_evidence(state, body.metadata)`. Catch reviewer-only `httpx.HTTPError`, `ValueError`,
and timeout. Always record `review_failed`. Re-raise only when
`state.review_fail_closed`; otherwise preserve executor response and set:

```python
state.review_status = "failed"
state.observability_degraded = True
state.observability_status = "degraded"
```

Record `finish_reason=length` before review and never mark that response completed.
Do not implement automatic continuation in phase one.

- [ ] **Step 5: Run focused and regression tests**

```bash
uv run pytest tests/test_api.py tests/test_controller.py -q
uv run mypy
```

- [ ] **Step 6: Commit**

```bash
git add gateway/src/dgx_moa/api.py gateway/src/dgx_moa/config.py \
  gateway/src/dgx_moa/controller.py config/models.yaml tests/test_api.py \
  tests/test_controller.py
git commit -m "fix(review): use evidence and explicit risk policy"
```

---

### Task 6: Add Stage Timing, Timeout Attribution, and Trace Evidence

**Files:**
- Modify: `gateway/src/dgx_moa/config.py`
- Modify: `gateway/src/dgx_moa/providers.py`
- Modify: `gateway/src/dgx_moa/controller.py`
- Modify: `gateway/src/dgx_moa/api.py`
- Modify: `gateway/src/dgx_moa/trace.py`
- Modify: `config/models.yaml`
- Test: `tests/test_providers.py`
- Test: `tests/test_api.py`
- Test: `tests/test_trace_v2.py`

**Interfaces:**
- Consumes: role calls and request lifecycle.
- Produces: bounded timeout values, `StageTimeout(stage)`, request timing events and trace metrics.

- [ ] **Step 1: Write failing timeout and trace tests**

Assert timeout mapping names exact stages: `planner`, `executor_first_byte`,
`executor_total`, and `reviewer`. Assert trace metrics contain accepted,
upstream-start, first-upstream-byte, first-downstream-byte, and completion
durations without prompt or response content.

- [ ] **Step 2: Run focused tests and verify RED**

```bash
uv run pytest tests/test_providers.py tests/test_api.py tests/test_trace_v2.py -q
```

- [ ] **Step 3: Add stage timeout configuration**

Add to `Limits` and YAML:

```python
planner_timeout_seconds: float = 120
executor_first_byte_timeout_seconds: float = 120
executor_total_timeout_seconds: float = 900
reviewer_timeout_seconds: float = 120
model_load_timeout_seconds: float = 1_200
tool_continuation_timeout_seconds: float = 600
```

Add to `providers.py`:

```python
class StageTimeout(TimeoutError):
    def __init__(self, stage: str):
        super().__init__(f"{stage} timed out")
        self.stage = stage
```

Let `complete()` accept `timeout_seconds` and `stage`; wrap the HTTP call in
`asyncio.timeout(timeout_seconds)` and raise `StageTimeout(stage)` on timeout.
Let stream setup use `executor_first_byte_timeout_seconds`; enforce total stream
deadline in the API generator. Never retry after any yielded byte.

- [ ] **Step 4: Record content-free monotonic timing**

Use one request `accepted = time.monotonic()` and helper:

```python
def elapsed_ms(started: float) -> float:
    return round((time.monotonic() - started) * 1000, 3)
```

Populate `state.timings_ms` keys `accepted`, `upstream_start`,
`first_upstream_byte`, `first_downstream_byte`, and `completed`; role durations
use `planner`, `executor_total`, and `reviewer`. Emit one `request_timing` event
containing only these numbers and stage status.

In `trace_record()`, merge:

```python
"metrics": (metrics or {}) | {
    "request_timing_ms": state.timings_ms,
    "runtime_mode": state.runtime_mode,
    "request_class": state.request_class,
    "roles_required": state.roles_required,
    "truncated": state.truncated,
},
```

- [ ] **Step 5: Run focused and regression tests**

```bash
uv run pytest tests/test_providers.py tests/test_api.py tests/test_trace_v2.py -q
uv run mypy
```

- [ ] **Step 6: Commit**

```bash
git add gateway/src/dgx_moa/api.py gateway/src/dgx_moa/config.py \
  gateway/src/dgx_moa/controller.py gateway/src/dgx_moa/providers.py \
  gateway/src/dgx_moa/trace.py config/models.yaml tests/test_api.py \
  tests/test_providers.py tests/test_trace_v2.py
git commit -m "feat(trace): record stage-specific request timing"
```

---

### Task 7: Honor Explicit Context Overrides Without Reducing Production 64K

**Files:**
- Modify: `gateway/src/dgx_moa/serve.py`
- Modify: `tests/test_serve.py`

**Interfaces:**
- Consumes: configured context and optional role-specific environment override.
- Produces: explicit override value; configured 65,536 remains default with no environment variable.

- [ ] **Step 1: Replace the contradictory test**

Replace `test_context_environment_cannot_lower_configured_minimum` with:

```python
def test_explicit_context_environment_overrides_configured_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DGX_MOA_EXECUTOR_MAX_MODEL_LEN", "16384")
    assert role_context_length("executor", 65536) == "16384"


def test_configured_context_is_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DGX_MOA_EXECUTOR_MAX_MODEL_LEN", raising=False)
    assert role_context_length("executor", 65536) == "65536"
```

- [ ] **Step 2: Run test and verify RED**

```bash
uv run pytest tests/test_serve.py -q
```

- [ ] **Step 3: Implement the explicit override**

```python
def role_context_length(role: str, configured: int) -> str:
    return role_environment(role, "MAX_MODEL_LEN", configured)
```

Do not add any lower environment value to production systemd units or production config.

- [ ] **Step 4: Run test and commit**

```bash
uv run pytest tests/test_serve.py tests/test_models_profiles.py -q
git add gateway/src/dgx_moa/serve.py tests/test_serve.py
git commit -m "fix(serve): honor explicit context overrides"
```

---

### Task 8: Document Client Contracts and Update Validation Harness

**Files:**
- Create: `docs/API_CLIENT_MODES.md`
- Create: `docs/HERMES_AGENT.md`
- Modify: `README.md`
- Modify: `docs/STATE.md`
- Modify: `docs/OPERATIONS.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/TRACE_SCHEMA.md`
- Modify: `docs/DECISIONS.md`
- Modify: `scripts/validate-opencode-loop.sh`
- Test: `tests/test_goal_tooling.py`

**Interfaces:**
- Consumes: implemented alias/error/streaming contracts.
- Produces: copyable curl, OpenAI SDK, OpenCode, and Hermes configuration with environment-only secrets.

- [ ] **Step 1: Add failing documentation assertions**

In `tests/test_goal_tooling.py`, assert:

```python
api_modes = Path("docs/API_CLIENT_MODES.md").read_text()
hermes = Path("docs/HERMES_AGENT.md").read_text()
for alias in ("dgx-moa-chat", "dgx-moa-agent", "dgx-moa-orchestrated"):
    assert alias in api_modes
assert "http://100.125.239.72:9000/v1" in hermes
assert "DGX_MOA_API_KEY" in hermes
assert "127.0.0.1:9000" not in hermes
assert "Tailscale Serve" not in hermes
```

- [ ] **Step 2: Run test and verify RED**

```bash
uv run pytest tests/test_goal_tooling.py -q
```

- [ ] **Step 3: Write exact client documentation**

`docs/API_CLIENT_MODES.md` must include alias table, direct agent tool-loop
ownership, request-field list, typed error example, immediate streaming contract,
`finish_reason=length`, default 4,096 and maximum 16,384, and `/v1/models` discovery.

`docs/HERMES_AGENT.md` must use only:

```yaml
provider: custom_openai
base_url: http://100.125.239.72:9000/v1
api_key: ${DGX_MOA_API_KEY}
model: dgx-moa-agent
```

State explicitly that Hermes owns the native tool loop, secrets stay in the
environment, and model-loading 503 is retryable using `Retry-After`. Do not claim
physical Hermes completion until measured later.

Update current-state docs only with verified phase-one behavior. Keep the failed
baseline in `VALIDATION.md`; do not erase it when post-fix evidence is added.

- [ ] **Step 4: Update OpenCode harness model selection**

Keep standard request shape and ensure both JSON payloads select
`"model":"dgx-moa-agent"`. Do not add mandatory metadata beyond existing
validation provenance headers.

- [ ] **Step 5: Run docs/tool tests and commit**

```bash
uv run pytest tests/test_goal_tooling.py tests/test_opencode_synthetic.py -q
bash -n scripts/validate-opencode-loop.sh
git add README.md docs/API_CLIENT_MODES.md docs/HERMES_AGENT.md docs/STATE.md \
  docs/OPERATIONS.md docs/ARCHITECTURE.md docs/TRACE_SCHEMA.md docs/DECISIONS.md \
  scripts/validate-opencode-loop.sh tests/test_goal_tooling.py
git commit -m "docs: publish API client mode contracts"
```

---

### Task 9: Verify Phase One and Re-run Physical Clients

**Files:**
- Modify: `docs/VALIDATION.md`

**Interfaces:**
- Consumes: Tasks 1–8.
- Produces: automated gates and real-client evidence comparing post-fix timing to Task 0.

- [ ] **Step 1: Run complete automated gates**

```bash
uv run pytest -q
uv run ruff format --check .
uv run ruff check .
uv run mypy
systemd-analyze --user verify systemd/*
for file in scripts/*.sh; do bash -n "$file"; done
scripts/audit-trace-completeness.sh data/traces
git diff --check
```

Expected: every command exits 0; no current test is removed.

- [ ] **Step 2: Start isolated post-fix runtime**

Repeat Task 0 isolation checks. Use a new `mktemp -d` runtime, foreground dev
models, gateway port different from 9000, separate SQLite/trace/run paths, and a
new environment-only credential. Production units and worktree remain untouched.

- [ ] **Step 3: Validate generic API clients**

Run authenticated `/v1/models`, curl non-streaming, curl streaming, official
OpenAI Python client non-streaming, and a minimal HTTPX streaming consumer.
Verify all aliases, executor-only chat/agent role records, natural content,
native tool call, tool-result continuation, invalid model, invalid request,
authentication failure, backend timeout, and one DONE.

Expected: direct modes never record planner/reviewer; standard clients send no
project metadata.

- [ ] **Step 4: Re-measure streaming timing**

Use the same twenty-line prompt and monotonic instrumentation as Task 0.

Expected:

```text
first_downstream_byte_ns <= executor_first_byte_ns + one_event_transport_overhead
first_downstream_byte_ns < executor_complete_ns
reviewer_not_in_critical_path=true
done_count=1
http_status=200
```

Record actual nanoseconds and derived durations; never invent values.

- [ ] **Step 5: Validate one real OpenCode and one real Hermes flow**

Use explicit working directory for OpenCode and the documented direct tailnet URL
for Hermes. Run normal conversation, streaming conversation, one native tool-call
round trip, and one tool-result continuation. Record OpenCode `1.17.18` and Hermes
Agent `0.18.2`. Do not use undocumented Hermes internals.

- [ ] **Step 6: Preserve evidence and stop isolated processes**

Append successful and failed attempts, ports, paths, exact timings, client
versions, response status, tool-call IDs/arguments, and trace audit result to
`docs/VALIDATION.md`. Stop only controlled foreground processes. Verify all dev
ports unbound, memory returned, production units inactive, and production tree clean.

- [ ] **Step 7: Re-run final automated gates**

Run every command from Step 1 again after documentation changes.

Expected: all exit 0.

- [ ] **Step 8: Commit phase-one validation**

```bash
git add docs/VALIDATION.md docs/STATE.md
git commit -m "docs(validation): record real streaming fix"
```

- [ ] **Step 9: Phase-one completion audit**

Compare every requirement in
`docs/superpowers/specs/2026-07-18-api-client-modes-streaming-design.md` to direct
file, test, trace, and physical-runtime evidence. Keep the overall Goal active:
usage statistics, lifecycle state machine, adaptive unloading, loading progress,
memory mechanism study, 64K near-limit request, full client matrices, soak,
remaining docs, push, and PR still require later sub-projects.
