from __future__ import annotations

import asyncio
import hashlib
import secrets
import sqlite3
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field

from .security import redact

PUBLISHED_EVENTS = {
    "request_received",
    "reasoner_started",
    "reasoner_completed",
    "executor_started",
    "tool_call_requested",
    "tool_result_received",
    "executor_skills_selected",
    "knowledge_retrieved",
    "planner_invoked",
    "plan_created",
    "review_started",
    "review_completed",
    "frontier_collaboration_started",
    "frontier_collaboration_completed",
    "judge_requested",
    "judge_completed",
    "failure_classified",
    "policy_tool_blocked",
    "task_blocked",
    "frontier_candidate_awaiting_approval",
    "engineering_loop_iteration_started",
    "engineering_loop_iteration_completed",
    "engineering_loop_terminated",
    "policy_evaluated",
    "task_completed",
    "request_finalized",
    "stream_failed",
    "provider_failure",
    "weekly_package_completed",
    "weekly_package_failed",
    "weekly_skill_report_completed",
    "weekly_job_failed",
    "specialist_provider_selected",
    "specialist_provider_completed",
    "specialist_provider_failed",
    "specialist_warmup_started",
    "specialist_warmup_completed",
    "specialist_warmup_failed",
    "specialist_unused_warmup",
}
SAFE_PAYLOAD_KEYS = {
    "task_id",
    "phase",
    "step",
    "iteration",
    "loop_id",
    "loop_type",
    "reason",
    "status",
    "role",
    "provider",
    "model",
    "profile",
    "mode",
    "parallel",
    "latency_ms",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cost_usd",
    "count",
    "steps",
    "budget",
    "remaining",
    "verdict",
    "risk",
    "recheck_required",
    "confidence",
    "confidence_category",
    "matched_rules",
    "missing_approvals",
    "termination_reason",
    "package_id",
    "candidate_count",
    "storage_location_identifier",
    "checksum",
    "verification_status",
    "failure_class",
    "skill_count",
    "high_value_count",
    "low_value_count",
    "job",
    "selected_provider",
    "specialist_role",
    "routing_reason",
    "residency_state",
    "queue_state",
    "predicted_local_completion_seconds",
    "predicted_remote_completion_seconds",
    "actual_completion_latency_seconds",
    "latency_seconds",
    "remote_cost_usd",
    "warmup_decision",
    "load_generation",
    "fallback_reason",
    "provider_error",
}
PROMPT_PAYLOAD_KEYS = ("prompt",)
REASONER_PAYLOAD_KEYS = (
    "assumptions",
    "constraints",
    "conclusions",
    "hypotheses",
    "evidence_references",
    "recommended_actions",
)

EVENT_TITLES = {
    "request_received": "📥 Request received",
    "reasoner_started": "🧠 Reasoner started",
    "reasoner_completed": "🧠 Reasoner completed",
    "executor_started": "⚙️ Executor started",
    "tool_call_requested": "🛠 Executor step requested",
    "tool_result_received": "🛠 Tool completed",
    "executor_skills_selected": "🧩 Executor skills selected",
    "knowledge_retrieved": "📚 Knowledge retrieved",
    "planner_invoked": "🗺 Planner invoked",
    "plan_created": "🗺 Plan created",
    "review_started": "🔎 Review started",
    "review_completed": "🔎 Review completed",
    "frontier_collaboration_started": "🌐 Frontier collaboration started",
    "frontier_collaboration_completed": "🌐 Frontier collaboration completed",
    "judge_requested": "⚖️ Judge invoked",
    "judge_completed": "⚖️ Judge completed",
    "failure_classified": "⚠️ Failure classified",
    "task_blocked": "⛔ Task blocked",
    "task_completed": "✅ Task completed",
    "request_finalized": "✅ Request finalized",
    "stream_failed": "❌ Stream failed",
    "provider_failure": "❌ Provider failure",
    "specialist_provider_selected": "🔀 Specialist provider selected",
    "specialist_provider_completed": "🔀 Specialist completed",
    "specialist_provider_failed": "❌ Specialist provider failed",
    "specialist_warmup_started": "🔥 Specialist warm-up started",
    "specialist_warmup_completed": "🔥 Specialist warm-up completed",
    "specialist_warmup_failed": "❌ Specialist warm-up failed",
    "specialist_unused_warmup": "💤 Specialist warm-up unused",
}

DETAIL_LABELS = {
    "task_id": "Task",
    "phase": "Phase",
    "step": "Step",
    "status": "Status",
    "role": "Role",
    "mode": "Mode",
    "latency_ms": "Latency (ms)",
    "confidence": "Confidence",
    "confidence_category": "Confidence",
    "prompt": "Prompt",
    "assumptions": "Assumptions",
    "constraints": "Constraints",
    "conclusions": "Conclusions",
    "hypotheses": "Hypotheses",
    "evidence_references": "Evidence references",
    "recommended_actions": "Recommended actions",
}

TELEGRAM_EVENT_TITLES = {
    "request_received": "📥 요청 접수",
    "reasoner_started": "🧠 Reasoner 분석 시작",
    "reasoner_completed": "🧠 Reasoner 분석 완료",
    "executor_started": "⚙️ Executor 실행 시작",
    "tool_call_requested": "🛠️ 도구 실행 요청",
    "tool_result_received": "🛠️ 도구 실행 완료",
    "executor_skills_selected": "🧩 Runtime Skill 선택",
    "knowledge_retrieved": "📚 Runtime Knowledge 조회",
    "planner_invoked": "🗺️ Planner 호출",
    "plan_created": "🗺️ 계획 생성 완료",
    "review_started": "🔎 Reviewer 검토 시작",
    "review_completed": "🔎 Reviewer 검토 완료",
    "frontier_collaboration_started": "🌐 Frontier 협업 시작",
    "frontier_collaboration_completed": "🌐 Frontier 협업 완료",
    "judge_requested": "⚖️ Judge 판정 요청",
    "judge_completed": "⚖️ Judge 판정 완료",
    "failure_classified": "⚠️ 오류 분류",
    "policy_tool_blocked": "⛔ 정책에 따른 도구 차단",
    "task_blocked": "⛔ 작업 차단",
    "frontier_candidate_awaiting_approval": "⏳ Frontier 후보 승인 대기",
    "engineering_loop_iteration_started": "🔄 엔지니어링 반복 시작",
    "engineering_loop_iteration_completed": "🔄 엔지니어링 반복 완료",
    "engineering_loop_terminated": "🏁 엔지니어링 반복 종료",
    "policy_evaluated": "🛡️ 정책 평가",
    "task_completed": "✅ 작업 완료",
    "request_finalized": "✅ 요청 처리 종료",
    "stream_failed": "❌ 스트림 실패",
    "provider_failure": "❌ Provider 실패",
    "weekly_package_completed": "📦 주간 패키지 생성 완료",
    "weekly_package_failed": "❌ 주간 패키지 생성 실패",
    "weekly_skill_report_completed": "📊 주간 Skill 보고서 완료",
    "weekly_job_failed": "❌ 주간 작업 실패",
    "specialist_provider_selected": "🔀 Specialist 실행 경로 선택",
    "specialist_provider_completed": "🔀 Specialist 처리 완료",
    "specialist_provider_failed": "❌ Specialist 처리 실패",
    "specialist_warmup_started": "🔥 로컬 Specialist 준비 시작",
    "specialist_warmup_completed": "🔥 로컬 Specialist 준비 완료",
    "specialist_warmup_failed": "❌ 로컬 Specialist 준비 실패",
    "specialist_unused_warmup": "💤 준비된 Specialist 미사용",
}

TELEGRAM_DETAIL_LABELS = {
    "task_id": "작업 ID",
    "phase": "단계",
    "step": "세부 단계",
    "iteration": "반복",
    "loop_id": "Loop ID",
    "loop_type": "Loop 유형",
    "reason": "사유",
    "status": "상태",
    "role": "역할",
    "provider": "Provider",
    "model": "모델",
    "profile": "프로필",
    "mode": "모드",
    "parallel": "병렬 실행",
    "latency_ms": "지연 시간(ms)",
    "latency_seconds": "지연 시간(초)",
    "prompt_tokens": "입력 토큰",
    "completion_tokens": "출력 토큰",
    "total_tokens": "전체 토큰",
    "cost_usd": "비용(USD)",
    "count": "개수",
    "steps": "단계 수",
    "budget": "예산",
    "remaining": "남은 예산",
    "verdict": "판정",
    "risk": "위험도",
    "recheck_required": "재검토 필요",
    "confidence": "신뢰도",
    "confidence_category": "신뢰도 등급",
    "matched_rules": "적용 정책",
    "missing_approvals": "누락 승인",
    "termination_reason": "종료 사유",
    "failure_class": "오류 유형",
    "selected_provider": "선택 경로",
    "specialist_role": "Specialist 역할",
    "routing_reason": "라우팅 사유",
    "residency_state": "로컬 상태",
    "queue_state": "대기열",
    "predicted_local_completion_seconds": "예상 로컬 완료(초)",
    "predicted_remote_completion_seconds": "예상 원격 완료(초)",
    "actual_completion_latency_seconds": "실제 완료(초)",
    "remote_cost_usd": "원격 비용(USD)",
    "warmup_decision": "Warm-up 상태",
    "load_generation": "Load 세대",
    "fallback_reason": "Fallback 사유",
    "provider_error": "Provider 오류",
    "prompt": "요청 내용",
    "assumptions": "가정",
    "constraints": "제약",
    "conclusions": "결론",
    "hypotheses": "가설",
    "evidence_references": "근거",
    "recommended_actions": "권장 작업",
}

TELEGRAM_VALUES = {
    "local": "로컬",
    "remote": "원격(OpenCode Go)",
    "opencode_go": "OpenCode Go",
    "codex_oauth": "Codex OAuth",
    "planner": "Planner",
    "reviewer": "Reviewer",
    "reasoner": "Reasoner",
    "executor": "Executor",
    "judge": "Judge",
    "frontier": "Frontier",
    "local_ready": "로컬 모델 준비 완료",
    "local_not_ready": "로컬 모델 미준비",
    "local_readiness_race": "로컬 준비 상태 변경",
    "remote_predicted_faster": "원격 완료 시간이 더 빠름",
    "cold_miss": "로컬 cold miss",
    "started": "시작됨",
    "reused": "기존 작업 재사용",
    "not_needed": "불필요",
    "completed": "완료",
    "failed": "실패",
    "approved": "승인",
    "rejected": "거부",
    "ready": "준비 완료",
    "stopped": "중지",
    "READY": "준비 완료",
    "BUSY": "처리 중",
    "UNLOADED": "미적재",
    "LOAD_REQUESTED": "적재 요청됨",
    "LOADING": "적재 중",
    "DEGRADED": "성능 저하",
    "FAILED": "실패",
    "COOLDOWN": "대기",
    "EVICTING": "해제 중",
}


class ObservationEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str
    request_id: str = Field(max_length=128)
    created_at: str
    details: dict[str, Any] = Field(default_factory=dict)


class ObservationNonceRequest(BaseModel):
    provider: Literal["discord", "telegram"]
    user_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)


class ObservationCommandRequest(ObservationNonceRequest):
    command: Literal[
        "approve",
        "reject",
        "pause",
        "resume",
        "terminate",
        "show-status",
        "show-findings",
        "show-budget",
    ]
    nonce: str = Field(min_length=16, max_length=256)
    idempotency_key: str = Field(min_length=8, max_length=128)


class ObservationProvider(Protocol):
    name: str

    async def send(self, events: Sequence[ObservationEvent]) -> None: ...


def public_event(
    request_id: str,
    event_type: str,
    payload: dict[str, Any],
    created_at: str,
    *,
    include_prompt: bool = False,
    include_reasoner_artifact: bool = False,
    max_content_characters: int = 2_000,
) -> ObservationEvent | None:
    if event_type not in PUBLISHED_EVENTS:
        return None
    allowed = set(SAFE_PAYLOAD_KEYS)
    if include_prompt:
        allowed.update(PROMPT_PAYLOAD_KEYS)
    if include_reasoner_artifact:
        allowed.update(REASONER_PAYLOAD_KEYS)
    details = {key: value for key, value in payload.items() if key in allowed}
    content_budget = max_content_characters
    for key in (*PROMPT_PAYLOAD_KEYS, *REASONER_PAYLOAD_KEYS):
        if key not in details:
            continue
        value = details[key]
        if isinstance(value, str):
            details[key] = value[:content_budget]
            content_budget -= len(details[key])
        elif isinstance(value, list):
            retained: list[Any] = []
            for item in value:
                text = str(item)
                if content_budget <= 0:
                    break
                retained.append(text[:content_budget])
                content_budget -= len(retained[-1])
            details[key] = retained
    return ObservationEvent(
        event_type=event_type,
        request_id=request_id,
        created_at=created_at,
        details=redact(details),
    )


def _render_detail(label: str, value: Any) -> list[str]:
    if isinstance(value, list):
        if not value:
            return [f"{label}: none"]
        return [f"{label}:", *(f"  • {item}" for item in value)]
    if isinstance(value, dict):
        if not value:
            return [f"{label}: none"]
        return [f"{label}:", *(f"  • {key}: {item}" for key, item in value.items())]
    text = str(value)
    if "\n" in text or len(text) > 120:
        return [f"{label}:", *(f"  {line}" for line in text.splitlines())]
    return [f"{label}: {text}"]


def render_events(events: Sequence[ObservationEvent], max_characters: int = 4_000) -> str:
    blocks = []
    for event in events:
        lines = [EVENT_TITLES.get(event.event_type, event.event_type.replace("_", " ").title())]
        lines.append(f"Request: {event.request_id}")
        for key, value in event.details.items():
            label = DETAIL_LABELS.get(key, key.replace("_", " ").title())
            lines.extend(_render_detail(label, value))
        blocks.append("\n".join(lines))
    rendered = "\n\n──────────\n\n".join(blocks)
    if len(rendered) <= max_characters:
        return rendered
    return rendered[: max_characters - 16].rstrip() + "\n… (truncated)"


def render_telegram_events(events: Sequence[ObservationEvent], max_characters: int = 4_000) -> str:
    def localized(value: Any) -> Any:
        if isinstance(value, str):
            return TELEGRAM_VALUES.get(value, value)
        if isinstance(value, bool):
            return "예" if value else "아니요"
        if isinstance(value, list):
            return [localized(item) for item in value]
        if isinstance(value, dict):
            return {
                TELEGRAM_DETAIL_LABELS.get(str(key), str(key)): localized(item)
                for key, item in value.items()
            }
        return value

    blocks = ["🤖 MoA 처리 과정"]
    for event in events:
        lines = [TELEGRAM_EVENT_TITLES.get(event.event_type, event.event_type)]
        lines.append(f"요청: {event.request_id}")
        lines.append(f"시각: {event.created_at}")
        for key, value in event.details.items():
            label = TELEGRAM_DETAIL_LABELS.get(key, key)
            lines.extend(_render_detail(label, localized(value)))
        blocks.append("\n".join(lines))
    rendered = "\n\n──────────\n\n".join(blocks)
    if len(rendered) <= max_characters:
        return rendered
    return rendered[: max_characters - 20].rstrip() + "\n… (길이 제한으로 생략)"


class DiscordProvider:
    name = "discord"

    def __init__(
        self,
        webhook_url: str,
        *,
        thread_id: str | None = None,
        timeout: float = 10,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.webhook_url = webhook_url
        self.thread_id = thread_id
        self.timeout = timeout
        self.transport = transport

    async def send(self, events: Sequence[ObservationEvent]) -> None:
        params = {"thread_id": self.thread_id} if self.thread_id else None
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            response = await client.post(
                self.webhook_url, params=params, json={"content": render_events(events)}
            )
            response.raise_for_status()


class TelegramProvider:
    name = "telegram"

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        *,
        message_thread_id: int | None = None,
        timeout: float = 10,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self.chat_id = chat_id
        self.message_thread_id = message_thread_id
        self.timeout = timeout
        self.transport = transport

    async def send(self, events: Sequence[ObservationEvent]) -> None:
        payload: dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": render_telegram_events(events),
        }
        if self.message_thread_id is not None:
            payload["message_thread_id"] = self.message_thread_id
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            response = await client.post(self.url, json=payload)
            response.raise_for_status()


class ObservationBus:
    def __init__(
        self,
        providers: Sequence[ObservationProvider],
        *,
        queue_size: int = 256,
        batch_size: int = 10,
        batch_interval_seconds: float = 2,
        include_prompt: bool = False,
        include_reasoner_artifact: bool = False,
        max_content_characters: int = 2_000,
    ):
        self.providers = list(providers)
        self.queue: asyncio.Queue[ObservationEvent] = asyncio.Queue(maxsize=queue_size)
        self.batch_size = batch_size
        self.batch_interval_seconds = batch_interval_seconds
        self.include_prompt = include_prompt
        self.include_reasoner_artifact = include_reasoner_artifact
        self.max_content_characters = max_content_characters
        self.task: asyncio.Task[None] | None = None
        self.metrics = {"sent": 0, "dropped": 0, "discord_errors": 0, "telegram_errors": 0}

    def publish_store_event(
        self, request_id: str, event_type: str, payload: dict[str, Any], created_at: str
    ) -> None:
        event = public_event(
            request_id,
            event_type,
            payload,
            created_at,
            include_prompt=self.include_prompt,
            include_reasoner_artifact=self.include_reasoner_artifact,
            max_content_characters=self.max_content_characters,
        )
        if event is None:
            return
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            self.metrics["dropped"] += 1

    def start(self) -> None:
        if self.task is None:
            self.task = asyncio.create_task(self.run())

    async def close(self) -> None:
        if self.task is None:
            return
        await self.queue.join()
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)
        self.task = None

    async def run(self) -> None:
        while True:
            first = await self.queue.get()
            batch = [first]
            try:
                deadline = asyncio.get_running_loop().time() + self.batch_interval_seconds
                while len(batch) < self.batch_size:
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        break
                    try:
                        batch.append(await asyncio.wait_for(self.queue.get(), remaining))
                    except TimeoutError:
                        break
                for provider in self.providers:
                    try:
                        await provider.send(batch)
                        self.metrics["sent"] += len(batch)
                    except (httpx.HTTPError, OSError):
                        self.metrics[f"{provider.name}_errors"] += 1
            finally:
                for _ in batch:
                    self.queue.task_done()


COMMANDS = {
    "approve",
    "reject",
    "pause",
    "resume",
    "terminate",
    "show-status",
    "show-findings",
    "show-budget",
}


class ObservationCommandStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        with self._connect() as database:
            database.execute(
                "CREATE TABLE IF NOT EXISTS observation_nonces ("
                "nonce_hash TEXT PRIMARY KEY, provider TEXT NOT NULL, user_id TEXT NOT NULL, "
                "request_id TEXT NOT NULL, expires_at REAL NOT NULL, used_at REAL)"
            )
            database.execute(
                "CREATE TABLE IF NOT EXISTS observation_commands ("
                "idempotency_key TEXT PRIMARY KEY, provider TEXT NOT NULL, user_id TEXT NOT NULL, "
                "request_id TEXT NOT NULL, command TEXT NOT NULL, nonce_hash TEXT NOT NULL, "
                "created_at REAL NOT NULL)"
            )
            columns = {
                row[1]
                for row in database.execute("PRAGMA table_info(observation_commands)").fetchall()
            }
            if "nonce_hash" not in columns:
                database.execute(
                    "ALTER TABLE observation_commands ADD COLUMN nonce_hash "
                    "TEXT NOT NULL DEFAULT ''"
                )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def issue_nonce(self, provider: str, user_id: str, request_id: str, ttl_seconds: int) -> str:
        nonce = secrets.token_urlsafe(24)
        nonce_hash = hashlib.sha256(nonce.encode()).hexdigest()
        with self._connect() as database:
            database.execute(
                "INSERT INTO observation_nonces "
                "(nonce_hash, provider, user_id, request_id, expires_at) VALUES (?, ?, ?, ?, ?)",
                (nonce_hash, provider, user_id, request_id, time.time() + ttl_seconds),
            )
        return nonce

    def authorize(
        self,
        *,
        provider: str,
        user_id: str,
        request_id: str,
        command: str,
        nonce: str,
        idempotency_key: str,
        allowed_users: dict[str, str],
        role_permissions: dict[str, list[str]],
    ) -> bool:
        if command not in COMMANDS:
            raise ValueError("unsupported observation command")
        role = allowed_users.get(f"{provider}:{user_id}")
        if role is None or command not in role_permissions.get(role, []):
            raise PermissionError("observation command not authorized")
        nonce_hash = hashlib.sha256(nonce.encode()).hexdigest()
        with self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            existing = database.execute(
                "SELECT provider, user_id, request_id, command, nonce_hash "
                "FROM observation_commands "
                "WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            expected = (provider, user_id, request_id, command, nonce_hash)
            if existing is not None:
                if tuple(existing) != expected:
                    raise ValueError("idempotency key reused for different command")
                return True
            row = database.execute(
                "SELECT provider, user_id, request_id, expires_at, used_at "
                "FROM observation_nonces WHERE nonce_hash = ?",
                (nonce_hash,),
            ).fetchone()
            if row is None or tuple(row[:3]) != (provider, user_id, request_id):
                raise PermissionError("invalid request-scoped nonce")
            if row[4] is not None or float(row[3]) < time.time():
                raise PermissionError("expired or consumed nonce")
            database.execute(
                "UPDATE observation_nonces SET used_at = ? WHERE nonce_hash = ?",
                (time.time(), nonce_hash),
            )
            database.execute(
                "INSERT INTO observation_commands "
                "(idempotency_key, provider, user_id, request_id, command, nonce_hash, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (idempotency_key, *expected, time.time()),
            )
        return False

    def audit_log(self) -> list[dict[str, Any]]:
        with self._connect() as database:
            rows = database.execute(
                "SELECT idempotency_key, provider, user_id, request_id, command, created_at "
                "FROM observation_commands ORDER BY rowid"
            ).fetchall()
        keys = ("idempotency_key", "provider", "user_id", "request_id", "command", "created_at")
        return [dict(zip(keys, row, strict=True)) for row in rows]
