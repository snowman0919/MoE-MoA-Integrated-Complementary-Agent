from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response, StreamingResponse

from .controller import pending_goal_prerequisites
from .inference import (
    ChatExecutionContext,
    ChatExecutionHeaders,
    chat_response_payload,
    coerce_responses_input_messages,
    coerce_responses_tools,
    compaction_request_index,
    error_response,
    responses_payload,
    tool_result_call_ids,
)
from .lifecycle import continuation_correlation
from .review import has_review_evidence
from .routing import COMPATIBILITY_MODEL_ALIASES
from .schemas import ChatMessage, ChatRequest, ResponsesRequest, latest_user_content, text_content
from .state import SessionState
from .streaming import (
    ProgressOnlyResponse,
    completed_chat_sse,
    keepalive_sse,
    responses_error_sse,
    responses_sse,
)

ChatHandler = Callable[
    [ChatRequest, ChatExecutionContext, ChatExecutionHeaders], Coroutine[Any, Any, Response]
]


def register_responses_routes(
    router: APIRouter | FastAPI,
    auth: Callable[..., Any],
    chat_handler: ChatHandler,
    *,
    default_model: str,
    model_load_timeout_seconds: float,
) -> None:
    @router.post("/v1/responses", dependencies=[Depends(auth)])
    async def responses(
        body: ResponsesRequest,
        request: Request,
        x_session_id: str | None = Header(default=None),
        x_runtime_channel: str | None = Header(default=None),
        x_trace_origin: str | None = Header(default=None),
        x_task_id: str | None = Header(default=None),
        x_workspace_path: str | None = Header(default=None),
        x_workspace_id: str | None = Header(default=None),
        x_repository_branch: str | None = Header(default=None),
        x_repository_commit: str | None = Header(default=None),
        x_dirty_state: str | None = Header(default=None),
        x_validation_command: str | None = Header(default=None, max_length=512),
    ) -> Response:
        messages = coerce_responses_input_messages(body.input)
        if body.instructions:
            messages.insert(0, {"role": "developer", "content": body.instructions})
        tools = coerce_responses_tools(body.tools)
        function_tool_names = {
            str(tool["function"]["name"])
            for tool in tools or []
            if isinstance(tool.get("function"), dict) and tool["function"].get("name")
        }
        custom_tool_names = {
            str(tool.get("name"))
            for tool in body.tools or []
            if tool.get("type") == "custom" and tool.get("name")
        }
        progress_language = (
            "ko"
            if any(
                "\uac00" <= character <= "\ud7a3"
                for message in messages
                if message.get("role") == "user"
                for character in text_content(message.get("content"))
            )
            else "en"
        )
        response_model = COMPATIBILITY_MODEL_ALIASES.get(body.model, body.model)
        compaction_index = compaction_request_index(messages)

        tool_choice = body.tool_choice
        if isinstance(tool_choice, dict) and tool_choice.get("type") in {"function", "custom"}:
            tool_choice = {
                "type": "function",
                "function": {"name": tool_choice.get("name")},
            }
        chat_body = ChatRequest(
            model=response_model,
            messages=[ChatMessage.model_validate(message) for message in messages],
            stream=body.stream,
            stream_options={"include_usage": True} if body.stream else None,
            tools=tools,
            tool_choice=tool_choice if tools else None,
            parallel_tool_calls=body.parallel_tool_calls if tools else None,
            metadata=body.metadata,
            max_tokens=body.max_output_tokens,
            temperature=body.temperature,
            top_p=body.top_p,
            stop=body.stop,
        )

        def execution_headers(session_id: str | None) -> ChatExecutionHeaders:
            return ChatExecutionHeaders(
                session_id=session_id,
                runtime_channel=x_runtime_channel,
                trace_origin=x_trace_origin,
                task_id=x_task_id,
                workspace_path=x_workspace_path,
                workspace_id=x_workspace_id,
                repository_branch=x_repository_branch,
                repository_commit=x_repository_commit,
                dirty_state=x_dirty_state,
                validation_command=x_validation_command,
            )

        def execution_context() -> ChatExecutionContext:
            return ChatExecutionContext(
                runtime=request.app.state,
                api_token_id=getattr(request.state, "api_token_id", "legacy"),
                tool_owner_recovered=bool(
                    getattr(request.state, "responses_tool_owner_recovered", False)
                ),
                user_agent=(
                    request.headers.get("user-agent") if "headers" in request.scope else None
                ),
            )

        if body.stream:
            response_session_id = x_session_id or str(body.metadata.get("session_id") or "")
            if not response_session_id:
                owner, _ = request.app.state.store.recover_tool_owner(
                    tool_result_call_ids(messages),
                    getattr(request.state, "api_token_id", "legacy"),
                    latest_user_content(messages),
                )
                if owner is not None:
                    response_session_id = owner.session_id
                    request.state.responses_tool_owner_recovered = True
                    request.app.state.lifecycle_store.release_continuation(
                        "executor", continuation_correlation(owner.session_id)
                    )
                    request.app.state.store.event(
                        owner.session_id,
                        "responses_session_recovered",
                        {"reason": "tool_result_owner"},
                    )
                else:
                    response_session_id = str(uuid.uuid4())
            if compaction_index is not None and not response_session_id.endswith(":compact"):
                response_session_id = f"{response_session_id}:compact"

            async def response_stream() -> AsyncIterator[bytes]:
                chat_task: asyncio.Task[Response] | None = None
                loading_deadline = time.monotonic() + model_load_timeout_seconds
                initial_heartbeat_sent = False
                progress_only_retries = 0
                judge_non_stream_retried = False
                current_body = chat_body

                def goal_requires_tool_action(state: SessionState | None) -> bool:
                    return bool(
                        state
                        and (
                            (
                                state.resolved_objective
                                and not has_review_evidence(state, current_body.metadata)
                            )
                            or (
                                state.engineering_loop is not None
                                and state.plan
                                and "reviewer" in state.roles_required
                                and state.review_deferred
                                and state.review_status != "approved"
                            )
                            or request.app.state.controller.requires_implementation_tool_action(
                                state, current_body.metadata
                            )
                        )
                    )

                try:
                    while True:
                        chat_task = asyncio.create_task(
                            chat_handler(
                                current_body,
                                execution_context(),
                                execution_headers(response_session_id),
                            )
                        )
                        if not initial_heartbeat_sent:
                            initial_heartbeat_sent = True
                            yield b": keep-alive\n\n"
                        while not chat_task.done():
                            await asyncio.wait((chat_task,), timeout=15)
                            if not chat_task.done():
                                yield b": keep-alive\n\n"
                        try:
                            chat_result = chat_task.result()
                        except HTTPException as error:
                            error_type = (
                                "invalid_request_error"
                                if error.status_code
                                in {
                                    status.HTTP_503_SERVICE_UNAVAILABLE,
                                    status.HTTP_404_NOT_FOUND,
                                }
                                else "backend_error"
                            )
                            async for chunk in responses_error_sse(
                                response_model,
                                session_id=response_session_id,
                                error_type=error_type,
                                code=(
                                    "invalid_request"
                                    if error_type == "invalid_request_error"
                                    else "backend_error"
                                ),
                                source="chat_http_exception",
                                status_code=error.status_code,
                            ):
                                yield chunk
                            return
                        except Exception as error:
                            async for chunk in responses_error_sse(
                                response_model,
                                session_id=response_session_id,
                                error_type="backend_error",
                                code="backend_error",
                                source="chat_unhandled_exception",
                                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                failure_class=type(error).__name__,
                            ):
                                yield chunk
                            return
                        if isinstance(chat_result, StreamingResponse):
                            translated: list[bytes] = []
                            response_state = request.app.state.store.get(response_session_id)
                            try:
                                async for chunk in keepalive_sse(
                                    responses_sse(
                                        chat_result.body_iterator,
                                        response_model,
                                        custom_tool_names=custom_tool_names,
                                        function_tool_names=function_tool_names,
                                        session_id=response_session_id,
                                        progress_language=progress_language,
                                        goal_already_loaded=bool(
                                            response_state and response_state.resolved_objective
                                        ),
                                        goal_prerequisites=(
                                            pending_goal_prerequisites(response_state)
                                            if response_state
                                            else ()
                                        ),
                                        require_tool_action=goal_requires_tool_action(
                                            response_state
                                        ),
                                    )
                                ):
                                    if chunk.startswith(b":"):
                                        yield chunk
                                    else:
                                        translated.append(chunk)
                            except ProgressOnlyResponse:
                                if progress_only_retries >= 3:
                                    async for chunk in responses_error_sse(
                                        response_model,
                                        session_id=response_session_id,
                                        error_type="incomplete_response",
                                        code="incomplete_response",
                                        source="progress_only_response",
                                        status_code=status.HTTP_502_BAD_GATEWAY,
                                    ):
                                        yield chunk
                                    return
                                progress_only_retries += 1
                                request.app.state.store.event(
                                    response_session_id,
                                    "progress_only_response_retried",
                                    {"attempt": progress_only_retries},
                                )
                                current_body = current_body.model_copy(
                                    update={
                                        "messages": [
                                            *current_body.messages,
                                            ChatMessage(
                                                role="developer",
                                                content=(
                                                    "The previous answer did not prove completion. "
                                                    "A code block in the answer "
                                                    "does not modify the workspace. "
                                                    "Call the required tool "
                                                    "to implement and validate. "
                                                    "Return a final result only "
                                                    "after recorded change, "
                                                    "test, and required review evidence exists."
                                                ),
                                            ),
                                        ],
                                        "metadata": {
                                            **current_body.metadata,
                                            "responses_progress_retry": True,
                                        },
                                    }
                                )
                                continue
                            for chunk in translated:
                                yield chunk
                            return
                        chat_payload = chat_response_payload(chat_result)
                        upstream_error = chat_payload.get("error") if chat_payload else None
                        if (
                            chat_result.status_code == status.HTTP_409_CONFLICT
                            and isinstance(upstream_error, dict)
                            and upstream_error.get("type") == "judge_non_stream_required"
                            and not judge_non_stream_retried
                        ):
                            judge_non_stream_retried = True
                            request.app.state.store.event(
                                response_session_id,
                                "responses_judge_non_stream_retried",
                                {},
                            )
                            current_body = current_body.model_copy(
                                update={"stream": False, "stream_options": None}
                            )
                            continue
                        if (
                            chat_result.status_code == status.HTTP_200_OK
                            and chat_payload
                            and not upstream_error
                        ):
                            response_state = request.app.state.store.get(response_session_id)
                            async for chunk in responses_sse(
                                completed_chat_sse(chat_payload),
                                response_model,
                                custom_tool_names=custom_tool_names,
                                function_tool_names=function_tool_names,
                                session_id=response_session_id,
                                progress_language=progress_language,
                                goal_already_loaded=bool(
                                    response_state and response_state.resolved_objective
                                ),
                                goal_prerequisites=(
                                    pending_goal_prerequisites(response_state)
                                    if response_state
                                    else ()
                                ),
                                require_tool_action=goal_requires_tool_action(response_state),
                            ):
                                yield chunk
                            return
                        if (
                            chat_result.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
                            and isinstance(upstream_error, dict)
                            and upstream_error.get("code") == "model_loading"
                            and time.monotonic() < loading_deadline
                        ):
                            retry_after = min(
                                float(chat_result.headers.get("Retry-After", "30")),
                                max(0.0, loading_deadline - time.monotonic()),
                            )
                            while retry_after > 0:
                                delay = min(15.0, retry_after)
                                await asyncio.sleep(delay)
                                retry_after -= delay
                                yield b": keep-alive\n\n"
                            continue
                        async for chunk in responses_error_sse(
                            response_model,
                            session_id=response_session_id,
                            error_type=(
                                str(upstream_error.get("type", "backend_error"))
                                if isinstance(upstream_error, dict)
                                else "backend_error"
                            ),
                            code=(
                                str(upstream_error.get("code", "backend_error"))
                                if isinstance(upstream_error, dict)
                                else "backend_error"
                            ),
                            source="chat_non_stream_response",
                            status_code=chat_result.status_code,
                        ):
                            yield chunk
                        return
                finally:
                    if chat_task is not None and not chat_task.done():
                        chat_task.cancel()
                        await asyncio.gather(chat_task, return_exceptions=True)

            return StreamingResponse(
                response_stream(),
                media_type="text/event-stream",
                headers={"X-Session-ID": response_session_id, "Cache-Control": "no-cache"},
            )
        try:
            chat_session_id = x_session_id
            if compaction_index is not None and chat_session_id:
                chat_session_id = (
                    chat_session_id
                    if chat_session_id.endswith(":compact")
                    else f"{chat_session_id}:compact"
                )
            chat_response = await chat_handler(
                chat_body,
                execution_context(),
                execution_headers(chat_session_id),
            )
        except HTTPException as error:
            if error.status_code in {
                status.HTTP_503_SERVICE_UNAVAILABLE,
                status.HTTP_404_NOT_FOUND,
            }:
                return error_response(
                    error.status_code, str(error.detail), "invalid_request_error", "invalid_request"
                )
            return JSONResponse(
                responses_payload(
                    response_model,
                    {
                        "error": {
                            "message": str(error.detail),
                            "type": "backend_error",
                            "code": "backend_error",
                        }
                    },
                    status="failed",
                ),
                status_code=200,
            )
        chat_payload = chat_response_payload(chat_response)
        if chat_payload is None:
            return error_response(
                status.HTTP_502_BAD_GATEWAY,
                "upstream response could not be parsed",
                "backend_error",
                "backend_error",
            )
        if chat_response.status_code == status.HTTP_502_BAD_GATEWAY:
            return JSONResponse(
                responses_payload(response_model, chat_payload, status="failed"),
                status_code=status.HTTP_200_OK,
            )
        return JSONResponse(
            responses_payload(
                response_model,
                chat_payload,
                custom_tool_names=custom_tool_names,
            )
        )

    @router.get("/v1/responses", dependencies=[Depends(auth)])
    async def responses_get(
        request: Request,
        input: str | None = None,
        model: str | None = None,
        x_session_id: str | None = Header(default=None),
        x_runtime_channel: str | None = Header(default=None),
        x_trace_origin: str | None = Header(default=None),
        x_task_id: str | None = Header(default=None),
        x_workspace_path: str | None = Header(default=None),
        x_workspace_id: str | None = Header(default=None),
        x_repository_branch: str | None = Header(default=None),
        x_repository_commit: str | None = Header(default=None),
        x_dirty_state: str | None = Header(default=None),
        x_validation_command: str | None = Header(default=None, max_length=512),
    ) -> Response:
        if input is None:
            raise HTTPException(status.HTTP_405_METHOD_NOT_ALLOWED, "Method Not Allowed")
        return await responses(
            body=ResponsesRequest(model=model or default_model, input=input),
            request=request,
            x_session_id=x_session_id,
            x_runtime_channel=x_runtime_channel,
            x_trace_origin=x_trace_origin,
            x_task_id=x_task_id,
            x_workspace_path=x_workspace_path,
            x_workspace_id=x_workspace_id,
            x_repository_branch=x_repository_branch,
            x_repository_commit=x_repository_commit,
            x_dirty_state=x_dirty_state,
            x_validation_command=x_validation_command,
        )
