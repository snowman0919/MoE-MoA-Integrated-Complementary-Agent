"""Administrative training, weekly-package, and replay routes."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status

from .replay import ReplayEngine, ReplayRequest
from .training import (
    CandidateReviewRequest,
    TrainingRepositoryExclusion,
    TrainingRequestExclusion,
    TrainingRetentionRequest,
    TrainingStore,
    TrainingUserExclusion,
)
from .weekly import (
    WeeklyPackageKeyRequest,
    WeeklyPackager,
    WeeklyPackageRevocationRequest,
    WeeklyRetentionRequest,
)


def build_training_router(admin_auth: Callable[..., Any]) -> APIRouter:
    router = APIRouter(dependencies=[Depends(admin_auth)])

    def training_store(request: Request) -> TrainingStore:
        store = request.app.state.training_store
        if store is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "training data workflow is disabled")
        return cast(TrainingStore, store)

    def weekly_packager(request: Request) -> WeeklyPackager:
        packager = request.app.state.weekly_packager
        if packager is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "weekly packaging is disabled")
        return cast(WeeklyPackager, packager)

    @router.get("/v1/admin/training/candidates/{candidate_id}")
    async def inspect_training_candidate(candidate_id: str, request: Request) -> dict[str, Any]:
        store = training_store(request)
        try:
            candidate = store.candidate(candidate_id)
        except KeyError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
        return {
            "candidate": candidate.model_dump(mode="json"),
            "review_history": store.review_history(candidate_id),
        }

    @router.post("/v1/admin/training/candidates/{candidate_id}/state")
    async def transition_training_candidate(
        candidate_id: str,
        body: CandidateReviewRequest,
        request: Request,
    ) -> dict[str, Any]:
        store = training_store(request)
        actor = str(getattr(request.state, "api_token_id", "loopback-admin"))
        try:
            candidate = store.transition_candidate(
                candidate_id,
                body.target_state,
                actor=actor,
                reason=body.reason,
            )
        except KeyError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
        except PermissionError as error:
            raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
        except ValueError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        return {
            "candidate_id": candidate.candidate_id,
            "review_state": candidate.review_state,
        }

    @router.post("/v1/admin/training/exclusions/requests")
    async def exclude_training_request(
        body: TrainingRequestExclusion,
        request: Request,
    ) -> dict[str, Any]:
        training_store(request).tombstone(body.request_id, body.reason)
        return {"request_id": body.request_id, "excluded": True}

    @router.post("/v1/admin/training/exclusions/repositories")
    async def exclude_training_repository(
        body: TrainingRepositoryExclusion,
        request: Request,
    ) -> dict[str, Any]:
        identity_hash = training_store(request).exclude_repository(
            body.repository_identity,
            body.reason,
        )
        return {"repository_identity_hash": identity_hash, "excluded": True}

    @router.post("/v1/admin/training/exclusions/users")
    async def exclude_training_user(
        body: TrainingUserExclusion,
        request: Request,
    ) -> dict[str, Any]:
        subject_hash = training_store(request).exclude_user(body.subject_id, body.reason)
        return {"training_subject_hash": subject_hash, "excluded": True}

    @router.post("/v1/admin/training/retention")
    async def apply_training_retention(
        body: TrainingRetentionRequest,
        request: Request,
    ) -> dict[str, Any]:
        return training_store(request).purge_retention(
            event_before=body.event_before,
            candidate_before=body.candidate_before,
            apply=body.apply,
        )

    @router.post("/v1/admin/weekly-packages/verify")
    async def verify_weekly_package(
        body: WeeklyPackageKeyRequest,
        request: Request,
    ) -> dict[str, Any]:
        try:
            return weekly_packager(request).verify(body.idempotency_key)
        except KeyError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/v1/admin/weekly-packages/revoke")
    async def revoke_weekly_package(
        body: WeeklyPackageRevocationRequest,
        request: Request,
    ) -> dict[str, Any]:
        try:
            return weekly_packager(request).registry.revoke(body.idempotency_key, body.reason)
        except KeyError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
        except ValueError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/v1/admin/weekly-packages/regenerate")
    async def regenerate_weekly_package(
        body: WeeklyPackageKeyRequest,
        request: Request,
    ) -> dict[str, Any]:
        try:
            packager = weekly_packager(request)
            window = packager.package_window(body.idempotency_key)
            candidates = training_store(request).packageable_candidates(
                created_from=window.utc_start.isoformat(),
                created_before=window.utc_end.isoformat(),
            )
            return packager.regenerate(body.idempotency_key, candidates)
        except KeyError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
        except (OSError, ValueError, PermissionError, subprocess.SubprocessError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/v1/admin/weekly-packages/retention")
    async def apply_weekly_retention(
        body: WeeklyRetentionRequest,
        request: Request,
    ) -> dict[str, Any]:
        try:
            return weekly_packager(request).purge_retention(body.before, apply=body.apply)
        except ValueError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/v1/admin/replay")
    async def replay_execution(body: ReplayRequest) -> dict[str, Any]:
        if not body.exact and body.mode != "audit":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "live comparative replay requires an internal provider callback",
            )
        try:
            result = await ReplayEngine().run(
                body.snapshot,
                mode=body.mode,
                exact=body.exact,
            )
        except ValueError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        return result.model_dump(mode="json")

    return router
